from openai import AzureOpenAI
from openai.types.chat import ChatCompletionMessage

from app.config import settings

client = AzureOpenAI(
    azure_endpoint=settings.azure_openai_endpoint,
    api_key=settings.azure_openai_api_key,
    api_version=settings.azure_openai_api_version,
)


def chat_completion(messages: list[dict], tools: list[dict] | None = None) -> ChatCompletionMessage:
    response = client.chat.completions.create(
        model=settings.azure_openai_deployment,
        messages=messages,
        tools=tools,
        temperature=0.4,
        max_tokens=300,
    )
    return response.choices[0].message
