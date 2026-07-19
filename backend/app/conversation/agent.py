import json
import logging
import time

from app.conversation.orchestrator import ConversationSession
from app.conversation.persistence import persist_message, persist_tool_execution
from app.llm.client import chat_completion
from app.models.conversation_message import MessageRole
from app.tools.context import CallContext
from app.tools.department_tools import tools_for_department
from app.tools.handlers import build_tool_handlers

logger = logging.getLogger("agent")

MAX_TOOL_ROUNDS = 5


def _persist_assistant_reply(ctx: CallContext, reply: str) -> None:
    if ctx.call_id is not None:
        persist_message(
            ctx.db,
            ctx.tenant_id,
            ctx.call_id,
            MessageRole.ASSISTANT,
            reply,
            confidence_score=ctx.last_confidence,
            citations=ctx.last_citations,
        )


def run_turn(session: ConversationSession, ctx: CallContext) -> str:
    """Run one assistant turn, resolving any tool calls, and return the final reply text."""
    # Don't leak a prior turn's search confidence/citations into this one.
    ctx.last_confidence = None
    ctx.last_citations = None
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
