import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_db
from app.models.call import Call, CallStatus

router = APIRouter(prefix="/api/calls", tags=["calls"])


class CallResponse(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID | None
    twilio_call_sid: str
    from_number: str
    to_number: str
    status: CallStatus
    started_at: datetime
    ended_at: datetime | None

    model_config = {"from_attributes": True}


@router.get("", response_model=list[CallResponse])
def list_calls(db: Session = Depends(get_db)) -> list[Call]:
    return list(db.execute(select(Call).order_by(Call.started_at.desc())).scalars())
