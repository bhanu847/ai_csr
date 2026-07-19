import json
import logging

from app.conversation.orchestrator import ConversationSession
from app.llm.client import chat_completion
from app.tools.context import CallContext
from app.tools.handlers import build_tool_handlers
from app.tools.schemas import TOOL_SCHEMAS

logger = logging.getLogger("agent")

MAX_TOOL_ROUNDS = 5


def run_turn(session: ConversationSession, ctx: CallContext) -> str:
    """Run one assistant turn, resolving any tool calls, and return the final reply text."""
    handlers = build_tool_handlers(ctx)

    for _ in range(MAX_TOOL_ROUNDS):
        message = chat_completion(session.history, tools=TOOL_SCHEMAS)

        if not message.tool_calls:
            reply = message.content or ""
            session.add_assistant_message(reply)
            return reply

        session.history.append(message.model_dump(exclude_none=True))

        for tool_call in message.tool_calls:
            handler = handlers.get(tool_call.function.name)
            if handler is None:
                result = f"Unknown tool: {tool_call.function.name}"
            else:
                try:
                    args = json.loads(tool_call.function.arguments)
                    result = handler(args)
                except Exception:
                    logger.exception("Tool %s failed", tool_call.function.name)
                    result = "The tool failed to run."

            session.history.append(
                {"role": "tool", "tool_call_id": tool_call.id, "content": result}
            )

    fallback = "I'm having trouble finding that. Let me connect you to a human."
    session.add_assistant_message(fallback)
    return fallback
