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


def _split_oversized_paragraph(paragraph: str) -> list[str]:
    """Plain word-count windowing, used only as a fallback for a single
    paragraph too large to fit in one chunk on its own."""
    words = paragraph.split()
    pieces: list[str] = []
    start = 0
    while start < len(words):
        end = min(start + CHUNK_SIZE_WORDS, len(words))
        pieces.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start = end - CHUNK_OVERLAP_WORDS
    return pieces


def chunk_pages(pages: list[PageText]) -> list[Chunk]:
    """Packs whole paragraphs into each chunk (splitting only a paragraph
    too large to fit alone) rather than a blind word-count window — a flat
    window can cut a sentence in half, which embeds worse and hurts
    retrieval precision for anything near that seam."""
    chunks: list[Chunk] = []
    for page in pages:
        paragraphs = [p.strip() for p in page.text.split("\n") if p.strip()]
        current: list[str] = []
        current_words = 0

        for paragraph in paragraphs:
            para_words = len(paragraph.split())

            if para_words > CHUNK_SIZE_WORDS:
                if current:
                    chunks.append(Chunk(text=" ".join(current), page=page.page))
                    current, current_words = [], 0
                chunks.extend(Chunk(text=piece, page=page.page) for piece in _split_oversized_paragraph(paragraph))
                continue

            if current and current_words + para_words > CHUNK_SIZE_WORDS:
                chunks.append(Chunk(text=" ".join(current), page=page.page))
                # Carry the last paragraph forward so consecutive chunks
                # overlap by one paragraph of shared context, same idea as
                # the old fixed-word overlap but at a semantic boundary.
                current = [current[-1]]
                current_words = len(current[0].split())

            current.append(paragraph)
            current_words += para_words

        if current:
            chunks.append(Chunk(text=" ".join(current), page=page.page))

    return chunks
