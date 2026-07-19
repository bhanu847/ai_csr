import uuid
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_db
from app.models.agent import Agent
from app.models.call import Call, CallStatus

router = APIRouter(prefix="/api/calls", tags=["calls"])


class CallResponse(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID | None
    agent_name: str | None
    twilio_call_sid: str
    from_number: str
    to_number: str
    status: CallStatus
    started_at: datetime
    ended_at: datetime | None

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
            "started_at": row.Call.started_at,
            "ended_at": row.Call.ended_at,
        }
        for row in rows
    ]
