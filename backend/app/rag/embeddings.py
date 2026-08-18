from app.config import settings
from app.llm.client import client

# nomic-embed-text is trained with task-instruction prefixes, and its model
# card documents materially worse retrieval without them: indexed passages
# get "search_document: ", the caller's question gets "search_query: " —
# different prefixes are intentional, not a mismatch, since the model was
# trained to embed a query and its matching passage differently for
# asymmetric retrieval. Harmless no-op if EMBEDDING_MODEL is swapped for one
# that doesn't use this convention — it just becomes ordinary leading text.
_QUERY_PREFIX = "search_query: "
_DOCUMENT_PREFIX = "search_document: "


def embed_texts(texts: list[str], is_query: bool = False) -> list[list[float]]:
    if not texts:
        return []
    prefix = _QUERY_PREFIX if is_query else _DOCUMENT_PREFIX
    response = client.embeddings.create(model=settings.embedding_model, input=[prefix + t for t in texts])
    return [item.embedding for item in response.data]
