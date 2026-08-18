import json

import anthropic
from openai import OpenAI

from app.config import settings

# Only embeddings still go through this client (see app/rag/embeddings.py) —
# chat completions moved to the hosted Claude API below.
client = OpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key)

anthropic_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

FALLBACK_REPLY = "I'm sorry, I'm not able to help with that. Let me connect you with a member of our team."


# --- OpenAI-shaped history <-> Anthropic Messages API -----------------
#
# The rest of the app (app.conversation.agent, orchestrator, handlers) was
# built against an OpenAI-style chat history: role in {system, user,
# assistant, tool}, tool calls as an assistant `tool_calls` list, tool
# results as separate `role: "tool"` messages. Rather than rewrite that
# history/tool-calling machinery for Anthropic's content-block format, this
# module converts at the boundary in both directions — the rest of the app
# is unaware the underlying provider changed at all.

def _to_anthropic_request(messages: list[dict]) -> tuple[str | None, list[dict]]:
    system_text: str | None = None
    anthropic_messages: list[dict] = []
    pending_tool_results: list[dict] = []

    def flush_tool_results() -> None:
        if pending_tool_results:
            anthropic_messages.append({"role": "user", "content": list(pending_tool_results)})
            pending_tool_results.clear()

    for i, msg in enumerate(messages):
        role = msg.get("role")

        if role == "system":
            flush_tool_results()
            if i == 0:
                system_text = msg["content"]
            else:
                # Mid-conversation system message (supervisor suggestions in
                # app.conversation.agent) -- Claude Opus 5 accepts a role:
                # "system" entry in `messages` itself, no beta header, as
                # long as it isn't the first entry.
                anthropic_messages.append({"role": "system", "content": [{"type": "text", "text": msg["content"]}]})
            continue

        if role == "tool":
            pending_tool_results.append(
                {"type": "tool_result", "tool_use_id": msg["tool_call_id"], "content": msg["content"]}
            )
            continue

        flush_tool_results()

        if role == "user":
            anthropic_messages.append({"role": "user", "content": msg["content"]})
        elif role == "assistant":
            blocks: list[dict] = []
            if msg.get("content"):
                blocks.append({"type": "text", "text": msg["content"]})
            for tool_call in msg.get("tool_calls") or []:
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": tool_call["id"],
                        "name": tool_call["function"]["name"],
                        "input": json.loads(tool_call["function"]["arguments"] or "{}"),
                    }
                )
            anthropic_messages.append({"role": "assistant", "content": blocks})

    flush_tool_results()
    return system_text, anthropic_messages


def _to_anthropic_tools(tools: list[dict] | None) -> list[dict] | None:
    if not tools:
        return None
    return [
        {
            "name": t["function"]["name"],
            "description": t["function"].get("description", ""),
            "input_schema": t["function"].get("parameters", {"type": "object", "properties": {}}),
        }
        for t in tools
    ]


class _ToolCallFunction:
    def __init__(self, name: str, arguments: str) -> None:
        self.name = name
        self.arguments = arguments


class _ToolCall:
    def __init__(self, call_id: str, name: str, arguments: str) -> None:
        self.id = call_id
        self.function = _ToolCallFunction(name, arguments)


class _Message:
    """Mimics just enough of openai's ChatCompletionMessage for
    app.conversation.agent (which reads .content/.tool_calls and calls
    .model_dump() to persist the turn back into session history)."""

    def __init__(self, content: str | None, tool_calls: list[_ToolCall]) -> None:
        self.content = content
        self.tool_calls = tool_calls

    def model_dump(self, exclude_none: bool = False) -> dict:
        data = {
            "role": "assistant",
            "content": self.content,
            "tool_calls": [
                {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in self.tool_calls
            ]
            or None,
        }
        return {k: v for k, v in data.items() if v is not None} if exclude_none else data


def chat_completion(messages: list[dict], tools: list[dict] | None = None) -> _Message:
    system_text, anthropic_messages = _to_anthropic_request(messages)
    kwargs: dict = {
        "model": settings.anthropic_model,
        "max_tokens": 1024,
        "messages": anthropic_messages,
        "output_config": {"effort": settings.anthropic_effort},
        "betas": ["server-side-fallback-2026-06-01"],
        "fallbacks": [{"model": "claude-opus-4-8"}],
    }
    if system_text:
        kwargs["system"] = system_text
    anthropic_tools = _to_anthropic_tools(tools)
    if anthropic_tools:
        kwargs["tools"] = anthropic_tools

    response = anthropic_client.beta.messages.create(**kwargs)

    if response.stop_reason == "refusal":
        return _Message(content=FALLBACK_REPLY, tool_calls=[])

    text = "".join(block.text for block in response.content if block.type == "text")
    tool_calls = [
        _ToolCall(block.id, block.name, json.dumps(block.input))
        for block in response.content
        if block.type == "tool_use"
    ]
    return _Message(content=text or None, tool_calls=tool_calls)


def json_completion(messages: list[dict], max_tokens: int = 500) -> dict:
    """Chat completion for structured extraction tasks (call summarization,
    confidence scoring, intent routing) rather than conversational replies.
    Relies on the caller's prompt explicitly asking for a JSON-only reply
    (every current caller already does) rather than a hard-enforced
    response format."""
    system_text, anthropic_messages = _to_anthropic_request(messages)
    kwargs: dict = {"model": settings.anthropic_model, "max_tokens": max_tokens, "messages": anthropic_messages}
    if system_text:
        kwargs["system"] = system_text

    response = anthropic_client.messages.create(**kwargs)

    if response.stop_reason == "refusal":
        return {}

    text = "".join(block.text for block in response.content if block.type == "text")
    return json.loads(text or "{}")
