import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.rag.chunker import chunk_pages
from app.rag.embeddings import embed_texts
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


def search(db: Session, agent_id: uuid.UUID, query: str, k: int = 4) -> list[dict]:
    [query_vector] = embed_texts([query])
    rows = db.execute(
        select(KnowledgeChunk, KnowledgeDocument.filename)
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
        .where(KnowledgeChunk.agent_id == agent_id)
        .order_by(KnowledgeChunk.embedding.cosine_distance(query_vector))
        .limit(k)
    ).all()
    return [{"text": chunk.text, "page": chunk.page, "filename": filename} for chunk, filename in rows]
