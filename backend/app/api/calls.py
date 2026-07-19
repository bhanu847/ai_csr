import uuid
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_db
from app.models.agent import Agent
from app.models.call import Call, CallStatus, ResolutionStatus
from app.models.conversation_message import ConversationMessage, MessageRole
from app.models.tool_execution_log import ToolExecutionLog

router = APIRouter(prefix="/api/calls", tags=["calls"])


class CallResponse(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID | None
    agent_name: str | None
    twilio_call_sid: str
    from_number: str
    to_number: str
    status: CallStatus
    intent: str | None
    sentiment: str | None
    started_at: datetime
    ended_at: datetime | None

    model_config = {"from_attributes": True}


class CallDetailResponse(CallResponse):
    confidence_score: float | None
    summary: str | None
    resolution_status: ResolutionStatus | None
    accuracy_score: float | None
    compliance_score: float | None
    empathy_score: float | None
    resolution_score: float | None
    qa_notes: str | None


class Citation(BaseModel):
    filename: str
    page: int | None
    confidence: float


class TranscriptMessage(BaseModel):
    kind: str = "message"
    timestamp: datetime
    role: MessageRole
    content: str
    message_type: str
    confidence_score: float | None
    citations: list[Citation] | None

    model_config = {"from_attributes": True}


class TranscriptToolCall(BaseModel):
    kind: str = "tool_call"
    timestamp: datetime
    tool_name: str
    input: dict
    output: str
    execution_time_ms: float

    model_config = {"from_attributes": True}


@router.get("", response_model=list[CallResponse])
def list_calls(
    status: CallStatus | None = None,
    agent_id: uuid.UUID | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    db: Session = Depends(get_db),
) -> list[dict]:
    query = select(Call, Agent.name.label("agent_name")).join(Agent, Agent.id == Call.agent_id, isouter=True)

    if status is not None:
        query = query.where(Call.status == status)
    if agent_id is not None:
        query = query.where(Call.agent_id == agent_id)
    if from_date is not None:
        query = query.where(Call.started_at >= from_date)
    if to_date is not None:
        query = query.where(Call.started_at < to_date + timedelta(days=1))

    query = query.order_by(Call.started_at.desc())

    rows = db.execute(query).all()
    return [
        {
            "id": row.Call.id,
            "agent_id": row.Call.agent_id,
            "agent_name": row.agent_name,
            "twilio_call_sid": row.Call.twilio_call_sid,
            "from_number": row.Call.from_number,
            "to_number": row.Call.to_number,
            "status": row.Call.status,
            "intent": row.Call.intent,
            "sentiment": row.Call.sentiment,
            "started_at": row.Call.started_at,
            "ended_at": row.Call.ended_at,
        }
        for row in rows
    ]


@router.get("/{call_id}", response_model=CallDetailResponse)
def get_call(call_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    row = db.execute(
        select(Call, Agent.name.label("agent_name"))
        .join(Agent, Agent.id == Call.agent_id, isouter=True)
        .where(Call.id == call_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Call not found")

    return {
        "id": row.Call.id,
        "agent_id": row.Call.agent_id,
        "agent_name": row.agent_name,
        "twilio_call_sid": row.Call.twilio_call_sid,
        "from_number": row.Call.from_number,
        "to_number": row.Call.to_number,
        "status": row.Call.status,
        "started_at": row.Call.started_at,
        "ended_at": row.Call.ended_at,
        "intent": row.Call.intent,
        "sentiment": row.Call.sentiment,
        "confidence_score": row.Call.confidence_score,
        "summary": row.Call.summary,
        "resolution_status": row.Call.resolution_status,
        "accuracy_score": row.Call.accuracy_score,
        "compliance_score": row.Call.compliance_score,
        "empathy_score": row.Call.empathy_score,
        "resolution_score": row.Call.resolution_score,
        "qa_notes": row.Call.qa_notes,
    }


@router.get("/{call_id}/transcript", response_model=list[TranscriptMessage | TranscriptToolCall])
def get_call_transcript(call_id: uuid.UUID, db: Session = Depends(get_db)) -> list[BaseModel]:
    if db.execute(select(Call.id).where(Call.id == call_id)).scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Call not found")

    messages = db.execute(
        select(ConversationMessage).where(ConversationMessage.call_id == call_id)
    ).scalars().all()
    tool_calls = db.execute(
        select(ToolExecutionLog).where(ToolExecutionLog.call_id == call_id)
    ).scalars().all()

    entries: list[BaseModel] = [TranscriptMessage.model_validate(m) for m in messages]
    entries += [TranscriptToolCall.model_validate(t) for t in tool_calls]
    entries.sort(key=lambda e: e.timestamp)
    return entries
