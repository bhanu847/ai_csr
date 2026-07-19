import uuid
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_db
from app.models.agent import Agent
from app.models.appointment import Appointment

router = APIRouter(prefix="/api/appointments", tags=["appointments"])


class AppointmentResponse(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    agent_name: str | None
    caller_name: str
    caller_phone: str
    preferred_time: str
    reason: str
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("", response_model=list[AppointmentResponse])
def list_appointments(
    agent_id: uuid.UUID | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    db: Session = Depends(get_db),
) -> list[dict]:
    """`from_date`/`to_date` filter on `created_at` (when the appointment was
    logged) rather than `preferred_time`, since the latter is free-text
    captured verbatim from the caller (e.g. "next Tuesday afternoon") and
    isn't a parseable date to range-filter against."""
    query = select(Appointment, Agent.name.label("agent_name")).join(Agent, Agent.id == Appointment.agent_id)

    if agent_id is not None:
        query = query.where(Appointment.agent_id == agent_id)
    if from_date is not None:
        query = query.where(Appointment.created_at >= from_date)
    if to_date is not None:
        query = query.where(Appointment.created_at < to_date + timedelta(days=1))

    query = query.order_by(Appointment.created_at.desc())

    rows = db.execute(query).all()
    return [
        {
            "id": row.Appointment.id,
            "agent_id": row.Appointment.agent_id,
            "agent_name": row.agent_name,
            "caller_name": row.Appointment.caller_name,
            "caller_phone": row.Appointment.caller_phone,
            "preferred_time": row.Appointment.preferred_time,
            "reason": row.Appointment.reason,
            "created_at": row.Appointment.created_at,
        }
        for row in rows
    ]
