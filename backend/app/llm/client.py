import json

from openai import OpenAI
from openai.types.chat import ChatCompletionMessage

from app.config import settings

# One self-hosted LLM, served through an OpenAI-compatible API (Ollama by
# default), for everything: embeddings (app/rag/embeddings.py), conversational
# replies with tool-calling, and structured JSON extraction below. `model` is
# a real model name here (not an Azure-style deployment name) -- Ollama
# routes by model directly.
client = OpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key)

# Qwen3 (the documented default model) "thinks" before answering by default,
# which on CPU-only inference adds many seconds of otherwise-invisible
# reasoning time per call on top of the actual reply -- measured ~29s vs
# ~15-19s for the same prompt on this project's own dev hardware (no GPU).
# `think` is Ollama's own (non-OpenAI-standard) field, passed through via
# extra_body; harmless to send to a backend that ignores it.
_EXTRA_BODY = {"think": False} if settings.llm_disable_thinking else {}


def chat_completion(messages: list[dict], tools: list[dict] | None = None) -> ChatCompletionMessage:
    response = client.chat.completions.create(
        model=settings.llm_model,
        messages=messages,
        tools=tools,
        temperature=0.4,
        max_tokens=300,
        extra_body=_EXTRA_BODY,
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
        extra_body=_EXTRA_BODY,
    )
    content = response.choices[0].message.content or "{}"
    return json.loads(content)
