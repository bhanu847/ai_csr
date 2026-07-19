from dataclasses import dataclass

from app.rag.parser import PageText

# Chunk size is approximated in words rather than exact tokens (~0.75
# words per token is a standard English approximation) — this avoids a
# runtime dependency (e.g. tiktoken) that needs to download its encoding
# file on first use, which isn't reliably reachable on every network.
CHUNK_SIZE_WORDS = 450  # ~600 tokens
CHUNK_OVERLAP_WORDS = 75  # ~100 tokens


@dataclass
class Chunk:
    text: str
    page: int | None


def chunk_pages(pages: list[PageText]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for page in pages:
        words = page.text.split()
        start = 0
        while start < len(words):
            end = min(start + CHUNK_SIZE_WORDS, len(words))
            chunk_text = " ".join(words[start:end])
            if chunk_text.strip():
                chunks.append(Chunk(text=chunk_text, page=page.page))
            if end == len(words):
                break
            start = end - CHUNK_OVERLAP_WORDS
    return chunks
