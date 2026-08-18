import json

from openai import AzureOpenAI, OpenAI
from openai.types.chat import ChatCompletionMessage

from app.config import settings

# Only embeddings still go through this client (see app/rag/embeddings.py) --
# chat completions moved to Azure OpenAI below.
client = OpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key)

# Azure OpenAI speaks the native OpenAI chat-completions API -- unlike the
# earlier Claude client, no message-format adapter is needed here, just a
# different endpoint. `model` on each call below is Azure's *deployment
# name*, not a model name -- Azure routes by deployment.
azure_client = AzureOpenAI(
    api_key=settings.azure_openai_api_key,
    api_version=settings.azure_openai_api_version,
    azure_endpoint=settings.azure_openai_endpoint,
)


def chat_completion(messages: list[dict], tools: list[dict] | None = None) -> ChatCompletionMessage:
    response = azure_client.chat.completions.create(
        model=settings.azure_openai_deployment,
        messages=messages,
        tools=tools,
        temperature=0.4,
        max_tokens=300,
    )
    return response.choices[0].message


def json_completion(messages: list[dict], max_tokens: int = 500) -> dict:
    """Chat completion constrained to a single JSON object reply, for
    structured extraction tasks (call summarization, confidence scoring)
    rather than conversational replies."""
    response = azure_client.chat.completions.create(
        model=settings.azure_openai_deployment,
        messages=messages,
        temperature=0.2,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content or "{}"
    return json.loads(content)
