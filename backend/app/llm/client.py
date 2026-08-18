import json

from openai import OpenAI
from openai.types.chat import ChatCompletionMessage

from app.config import settings

client = OpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key)

# qwen3 (the default LLM_MODEL) "thinks" by default — it emits a long
# chain-of-thought block before the actual reply, which on a live phone call
# is pure added latency the caller sits through in silence. Measured on this
# stack: ~57s with thinking vs ~3s without, for the same short reply.
# reasoning_effort is an Ollama/vLLM extension the openai SDK passes through
# unrecognized; harmless no-op on a backend that doesn't support it.
_NO_THINKING = {"reasoning_effort": "none"}


def chat_completion(messages: list[dict], tools: list[dict] | None = None) -> ChatCompletionMessage:
    response = client.chat.completions.create(
        model=settings.llm_model,
        messages=messages,
        tools=tools,
        temperature=0.4,
        max_tokens=300,
        extra_body=_NO_THINKING,
    )
    return response.choices[0].message


def json_completion(messages: list[dict], max_tokens: int = 500) -> dict:
    """Chat completion constrained to a single JSON object reply, for
    structured extraction tasks (call summarization, confidence scoring)
    rather than conversational replies."""
    response = client.chat.completions.create(
        model=settings.llm_model,
        messages=messages,
        temperature=0.2,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
        extra_body=_NO_THINKING,
    )
    content = response.choices[0].message.content or "{}"
    return json.loads(content)
