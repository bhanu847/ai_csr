import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_db
from app.models.appointment import Appointment

router = APIRouter(prefix="/api/appointments", tags=["appointments"])


class AppointmentResponse(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    caller_name: str
    caller_phone: str
    preferred_time: str
    reason: str
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("", response_model=list[AppointmentResponse])
def list_appointments(db: Session = Depends(get_db)) -> list[Appointment]:
    return list(db.execute(select(Appointment).order_by(Appointment.created_at.desc())).scalars())
