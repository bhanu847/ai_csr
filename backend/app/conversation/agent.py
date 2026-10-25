import json
import logging
import time

from sqlalchemy import select

from app.conversation.orchestrator import ConversationSession
from app.conversation.persistence import persist_message, persist_tool_execution
from app.fastpath.service import get_instant_answer_model
from app.llm.client import chat_completion
from app.models.call import Call
from app.models.conversation_message import MessageRole
from app.rag import learning
from app.tools.context import CallContext
from app.tools.department_tools import tools_for_department
from app.tools.handlers import build_tool_handlers

logger = logging.getLogger("agent")

MAX_TOOL_ROUNDS = 5

HOLD_MESSAGE = "One moment — I'm connecting you with a member of our team."


def _persist_assistant_reply(ctx: CallContext, reply: str, message_type: str = "text") -> None:
    # message_type records which path produced the reply ("instant",
    # "learned" or "text" for the LLM) -- app.rag.learning reads it back
    # when a reviewer rates the reply, to know what to reward or fix.
    if ctx.call_id is not None:
        persist_message(
            ctx.db,
            ctx.tenant_id,
            ctx.call_id,
            MessageRole.ASSISTANT,
            reply,
            message_type=message_type,
            confidence_score=ctx.last_confidence,
            citations=ctx.last_citations,
        )


def _reply_from_learned(session: ConversationSession, ctx: CallContext, hit: learning.LearnedHit) -> str:
    learning.record_use(ctx.db, hit)
    ctx.last_citations = hit.citations
    session.add_assistant_message(hit.answer)
    _persist_assistant_reply(ctx, hit.answer, message_type="learned")
    return hit.answer


def run_turn(session: ConversationSession, ctx: CallContext) -> str:
    """Run one assistant turn, resolving any tool calls, and return the final reply text."""
    # Don't leak a prior turn's search confidence/citations into this one.
    ctx.last_confidence = None
    ctx.last_citations = None

    if ctx.call_id is not None:
        call = ctx.db.execute(select(Call).where(Call.id == ctx.call_id)).scalar_one_or_none()
        if call is not None:
            # A supervisor hit "Stop AI" (Feature 10) — skip the LLM
            # entirely rather than let it keep talking over a handoff.
            if call.ai_paused:
                session.add_assistant_message(HOLD_MESSAGE)
                _persist_assistant_reply(ctx, HOLD_MESSAGE)
                return HOLD_MESSAGE

            # A supervisor sent live guidance — fold it in as a one-time
            # steer, then consume it so it doesn't repeat every turn.
            if call.pending_suggestion:
                session.history.append(
                    {
                        "role": "system",
                        "content": f"SUPERVISOR SUGGESTION (apply this to your next reply): {call.pending_suggestion}",
                    }
                )
                call.pending_suggestion = None

    # Instant-answer fast path: a confident match skips the LLM/tool loop
    # entirely (~1ms, no model call). Only ever answers static, non-
    # personalized FAQ facts and generic conversational turns -- its
    # training data (app/fastpath/data/faq_intents.json) explicitly lists
    # every claims/benefits/formulary/pharmacy-lookup/verification-shaped
    # question as out-of-scope, so those always fall through below
    # unchanged. Never active during an in-progress tool exchange (awaiting
    # a pending_suggestion/hold check above, or mid-verification) because
    # it only ever looks at this turn's own utterance, same as the
    # existing routing check in media_stream_handler.
    #
    # Learned answers (app.rag.learning) go first: answers a reviewer
    # corrected or confirmed are more specific than the generic canned FAQ
    # answers, so they win -- on an exact match (a dict lookup) or a near-
    # identical rewording (one embedding call, ~90ms, cached for repeats,
    # and skipped for agents with nothing learned). All far cheaper than an
    # LLM round-trip. A vetoed question (fast answer marked wrong, documents
    # had nothing better) skips every fast path and goes straight to the LLM.
    if session.history and session.history[-1].get("role") == "user":
        utterance = session.history[-1].get("content", "")
        learned = learning.lookup_exact(ctx.db, ctx.agent_id, utterance)
        vetoed = learned is not None and not learned.answer
        if learned is None:
            learned = learning.lookup_similar(ctx.db, ctx.agent_id, utterance)
        if learned is not None and learned.answer:
            return _reply_from_learned(session, ctx, learned)

        instant_model = get_instant_answer_model()
        if instant_model is not None and not vetoed:
            prediction = instant_model.predict(utterance)
            if prediction.accepted:
                reply = instant_model.intents[prediction.intent].answer
                session.add_assistant_message(reply)
                _persist_assistant_reply(ctx, reply, message_type="instant")
                return reply

    handlers = build_tool_handlers(ctx)
    # Scoped to the active department (see app.tools.department_tools) — a
    # specialist agent literally can't be offered tools outside its remit,
    # not just discouraged from using them via prompt wording.
    schemas = tools_for_department(ctx.department)
    allowed_tool_names = {schema["function"]["name"] for schema in schemas}

    for _ in range(MAX_TOOL_ROUNDS):
        message = chat_completion(session.history, tools=schemas)

        if not message.tool_calls:
            reply = message.content or ""
            session.add_assistant_message(reply)
            _persist_assistant_reply(ctx, reply)
            return reply

        session.history.append(message.model_dump(exclude_none=True))

        for tool_call in message.tool_calls:
            handler = handlers.get(tool_call.function.name) if tool_call.function.name in allowed_tool_names else None
            args: dict = {}
            started = time.perf_counter()
            if handler is None:
                result = f"Unknown tool: {tool_call.function.name}"
            else:
                try:
                    args = json.loads(tool_call.function.arguments)
                    result = handler(args)
                except Exception:
                    logger.exception("Tool %s failed", tool_call.function.name)
                    result = "The tool failed to run."
            elapsed_ms = (time.perf_counter() - started) * 1000

            if ctx.call_id is not None:
                persist_tool_execution(
                    ctx.db, ctx.tenant_id, ctx.call_id, tool_call.function.name, args, result, elapsed_ms
                )

            session.history.append(
                {"role": "tool", "tool_call_id": tool_call.id, "content": result}
            )

    fallback = "I'm having trouble finding that. Let me connect you to a human."
    session.add_assistant_message(fallback)
    _persist_assistant_reply(ctx, fallback)
    return fallback
