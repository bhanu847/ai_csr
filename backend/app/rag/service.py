import math
import uuid

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.confidence_service import score_from_distance
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.rag.chunker import chunk_pages
from app.rag.embeddings import embed_query, embed_texts
from app.rag.parser import parse_document


def ingest_document(
    db: Session, tenant_id: uuid.UUID, agent_id: uuid.UUID, filename: str, data: bytes
) -> KnowledgeDocument:
    pages = parse_document(filename, data)
    chunks = chunk_pages(pages)
    if not chunks:
        raise ValueError(f"No extractable text found in {filename}")

    vectors = embed_texts([c.text for c in chunks])

    document = KnowledgeDocument(tenant_id=tenant_id, agent_id=agent_id, filename=filename)
    db.add(document)
    db.flush()

    for chunk, vector in zip(chunks, vectors):
        db.add(
            KnowledgeChunk(
                tenant_id=tenant_id,
                agent_id=agent_id,
                document_id=document.id,
                page=chunk.page,
                text=chunk.text,
                embedding=vector,
            )
        )
    return document


def delete_document(db: Session, agent_id: uuid.UUID, document_id: uuid.UUID) -> None:
    document = db.execute(
        select(KnowledgeDocument).where(
            KnowledgeDocument.id == document_id, KnowledgeDocument.agent_id == agent_id
        )
    ).scalar_one_or_none()
    if document is None:
        raise KeyError(document_id)
    db.delete(document)  # KnowledgeChunk rows cascade via the FK's ON DELETE CASCADE


def list_documents(db: Session, agent_id: uuid.UUID) -> list[dict]:
    chunk_counts = (
        select(KnowledgeChunk.document_id, func.count().label("chunk_count"))
        .group_by(KnowledgeChunk.document_id)
        .subquery()
    )
    rows = db.execute(
        select(KnowledgeDocument, chunk_counts.c.chunk_count)
        .outerjoin(chunk_counts, chunk_counts.c.document_id == KnowledgeDocument.id)
        .where(KnowledgeDocument.agent_id == agent_id)
        .order_by(KnowledgeDocument.uploaded_at.desc())
    ).all()
    return [
        {
            "id": doc.id,
            "filename": doc.filename,
            "chunk_count": chunk_count or 0,
            "uploaded_at": doc.uploaded_at,
        }
        for doc, chunk_count in rows
    ]


# Reviewer feedback (KnowledgeChunk.feedback_score) can move a chunk by at
# most this much cosine similarity when ranking -- enough to swap two
# near-tied candidates (a chunk repeatedly behind wrong answers sinks below
# its runner-up), never enough to promote an unrelated chunk past a real
# match. Ranking only: confidence is still scored from the raw distance, so
# feedback can't talk a weak match into a HIGH-confidence answer.
FEEDBACK_RANK_WEIGHT = 0.05
FEEDBACK_SCALE = 3.0  # feedback_score at which the nudge reaches ~76% of its max
CANDIDATE_MULTIPLIER = 3


def search(db: Session, agent_id: uuid.UUID, query: str, k: int = 4) -> list[dict]:
    query_vector = embed_query(query)
    distance = KnowledgeChunk.embedding.cosine_distance(query_vector)
    rows = db.execute(
        select(KnowledgeChunk, KnowledgeDocument.filename, distance.label("distance"))
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
        .where(KnowledgeChunk.agent_id == agent_id)
        .order_by(distance)
        .limit(k * CANDIDATE_MULTIPLIER)
    ).all()
    results = [
        {
            "chunk_id": chunk.id,
            "text": chunk.text,
            "page": chunk.page,
            "filename": filename,
            "distance": dist,
            "feedback_score": chunk.feedback_score or 0.0,
        }
        for chunk, filename, dist in rows
    ]
    results.sort(key=_ranking_score, reverse=True)
    return results[:k]


def _ranking_score(result: dict) -> float:
    return (1 - result["distance"]) + FEEDBACK_RANK_WEIGHT * math.tanh(result["feedback_score"] / FEEDBACK_SCALE)


def build_citations(results: list[dict]) -> list[dict]:
    """Per-chunk citations for ConversationMessage.citations. chunk_id is what
    lets feedback on the reply later be credited back to these exact chunks."""
    return [
        {
            "filename": r["filename"],
            "page": r["page"],
            "confidence": score_from_distance(r["distance"]),
            "chunk_id": str(r["chunk_id"]),
        }
        for r in results
    ]


def reward_chunks(db: Session, citations: list[dict] | None, reward: float) -> int:
    """Apply a feedback reward to every chunk a reply cited. Returns how many
    chunks were updated (older replies' citations predate chunk_id)."""
    chunk_ids = []
    for c in citations or []:
        try:
            chunk_ids.append(uuid.UUID(str(c["chunk_id"])))
        except (KeyError, ValueError):
            continue
    if not chunk_ids:
        return 0
    db.execute(
        update(KnowledgeChunk)
        .where(KnowledgeChunk.id.in_(chunk_ids))
        .values(feedback_score=KnowledgeChunk.feedback_score + reward)
    )
    return len(chunk_ids)
