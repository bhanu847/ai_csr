import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_db
from app.models.call import Call, CallStatus
from app.models.customer_profile import CustomerProfile

router = APIRouter(prefix="/api/customers", tags=["customers"])


class CustomerResponse(BaseModel):
    id: uuid.UUID
    phone_number: str
    name: str | None
    language: str | None
    last_interaction: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PreviousCall(BaseModel):
    id: uuid.UUID
    started_at: datetime
    intent: str | None
    sentiment: str | None
    resolution_status: str | None
    summary: str | None


class CustomerDetailResponse(CustomerResponse):
    call_count: int
    latest_sentiment: str | None
    previous_calls: list[PreviousCall]


@router.get("", response_model=list[CustomerResponse])
def list_customers(db: Session = Depends(get_db)) -> list[CustomerProfile]:
    return (
        db.execute(select(CustomerProfile).order_by(CustomerProfile.last_interaction.desc()))
        .scalars()
        .all()
    )


@router.get("/{customer_id}", response_model=CustomerDetailResponse)
def get_customer(customer_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    profile = db.execute(select(CustomerProfile).where(CustomerProfile.id == customer_id)).scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="Customer not found")

    calls = (
        db.execute(
            select(Call)
            .where(Call.customer_id == customer_id, Call.status == CallStatus.COMPLETED)
            .order_by(Call.started_at.desc())
        )
        .scalars()
        .all()
    )

    return {
        "id": profile.id,
        "phone_number": profile.phone_number,
        "name": profile.name,
        "language": profile.language,
        "last_interaction": profile.last_interaction,
        "created_at": profile.created_at,
        "call_count": len(calls),
        "latest_sentiment": calls[0].sentiment if calls else None,
        "previous_calls": [
            {
                "id": c.id,
                "started_at": c.started_at,
                "intent": c.intent,
                "sentiment": c.sentiment,
                "resolution_status": c.resolution_status.value if c.resolution_status else None,
                "summary": c.summary,
            }
            for c in calls
        ],
    }
