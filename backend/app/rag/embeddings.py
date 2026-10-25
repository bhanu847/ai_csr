from functools import lru_cache

import httpx

from app.config import settings

# nomic-embed-text is trained with task-instruction prefixes, and its model
# card documents materially worse retrieval without them: indexed passages
# get "search_document: ", the caller's question gets "search_query: " —
# different prefixes are intentional, not a mismatch, since the model was
# trained to embed a query and its matching passage differently for
# asymmetric retrieval. Harmless no-op if EMBEDDING_MODEL is swapped for one
# that doesn't use this convention — it just becomes ordinary leading text.
_QUERY_PREFIX = "search_query: "
_DOCUMENT_PREFIX = "search_document: "

# Ollama's OpenAI-compatibility endpoint (settings.llm_base_url, used for
# chat historically) silently drops the keep_alive field -- measured live
# 2026-08-22, it kept unloading the model on its default 5-minute idle timer
# regardless. Its *native* API honors keep_alive, so embeddings call that
# directly instead. base_url is llm_base_url with the OpenAI-compat "/v1"
# suffix stripped, e.g. "http://localhost:11434/v1" -> "http://localhost:11434".
_OLLAMA_NATIVE_BASE = settings.llm_base_url.removesuffix("/v1")


def embed_texts(texts: list[str], is_query: bool = False) -> list[list[float]]:
    if not texts:
        return []
    prefix = _QUERY_PREFIX if is_query else _DOCUMENT_PREFIX
    # keep_alive=-1 tells Ollama to hold the model in RAM indefinitely instead
    # of its default 5-minute idle unload -- without this, the first
    # embedding call after any gap between calls pays a 2-5s cold-start
    # reload, which was the single biggest contributor to reply latency
    # (measured live 2026-08-22: 2676ms cold vs. ~90ms once warm).
    response = httpx.post(
        f"{_OLLAMA_NATIVE_BASE}/api/embed",
        json={
            "model": settings.embedding_model,
            "input": [prefix + t for t in texts],
            "keep_alive": -1,
        },
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()["embeddings"]


@lru_cache(maxsize=2048)
def _embed_query_cached(text: str) -> tuple[float, ...]:
    return tuple(embed_texts([text], is_query=True)[0])


def embed_query(text: str) -> list[float]:
    """embed_texts for one search query, memoized: callers repeat the same
    questions constantly, and the same utterance is embedded both for the
    learned-answer lookup and again if feedback re-answers it from source.
    A cache hit is ~0ms vs ~90ms for a warm Ollama round-trip."""
    return list(_embed_query_cached(text.strip()))
