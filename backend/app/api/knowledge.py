import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_db
from app.models.agent import Agent
from app.models.knowledge import KnowledgeChunk
from app.rag import service as rag_service

router = APIRouter(prefix="/api/agents/{agent_id}/knowledge", tags=["knowledge"])

ALLOWED_EXTENSIONS = (".pdf", ".docx")


class DocumentResponse(BaseModel):
    id: uuid.UUID
    filename: str
    chunk_count: int


def _require_agent(db: Session, agent_id: uuid.UUID) -> Agent:
    agent = db.execute(select(Agent).where(Agent.id == agent_id)).scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.post("/upload", response_model=DocumentResponse, status_code=201)
async def upload_document(agent_id: uuid.UUID, file: UploadFile, db: Session = Depends(get_db)) -> dict:
    agent = _require_agent(db, agent_id)
    if not file.filename or not file.filename.lower().endswith(ALLOWED_EXTENSIONS):
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files are supported")

    data = await file.read()
    try:
        document = await asyncio.to_thread(
            rag_service.ingest_document, db, agent.tenant_id, agent.id, file.filename, data
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    db.flush()
    chunk_count = db.execute(
        select(func.count()).select_from(KnowledgeChunk).where(KnowledgeChunk.document_id == document.id)
    ).scalar_one()
    return {"id": document.id, "filename": document.filename, "chunk_count": chunk_count}


@router.get("", response_model=list[DocumentResponse])
def list_documents(agent_id: uuid.UUID, db: Session = Depends(get_db)) -> list[dict]:
    _require_agent(db, agent_id)
    return rag_service.list_documents(db, agent_id)


@router.delete("/{document_id}")
def delete_document(agent_id: uuid.UUID, document_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    _require_agent(db, agent_id)
    try:
        rag_service.delete_document(db, agent_id, document_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"deleted": str(document_id)}
