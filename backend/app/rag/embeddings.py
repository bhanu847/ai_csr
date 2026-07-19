from app.config import settings
from app.llm.client import client


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    response = client.embeddings.create(model=settings.azure_openai_embedding_deployment, input=texts)
    return [item.embedding for item in response.data]
