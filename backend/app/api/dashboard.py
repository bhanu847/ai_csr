from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_db
from app.models.agent import Agent
from app.models.appointment import Appointment
from app.models.call import Call, CallStatus

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


class CallVolumePoint(BaseModel):
    date: date
    count: int


class DashboardSummary(BaseModel):
    total_agents: int
    total_calls: int
    appointments_booked: int
    calls_in_progress: int
    call_volume: list[CallVolumePoint]


@router.get("/summary", response_model=DashboardSummary)
def get_summary(days: int = 14, db: Session = Depends(get_db)) -> DashboardSummary:
    total_agents = db.execute(select(func.count()).select_from(Agent)).scalar_one()
    total_calls = db.execute(select(func.count()).select_from(Call)).scalar_one()
    appointments_booked = db.execute(select(func.count()).select_from(Appointment)).scalar_one()
    calls_in_progress = db.execute(
        select(func.count()).select_from(Call).where(Call.status == CallStatus.IN_PROGRESS)
    ).scalar_one()

    today = datetime.now(timezone.utc).date()
    range_start = today - timedelta(days=days - 1)

    day_column = func.date(Call.started_at)
    rows = db.execute(
        select(day_column.label("day"), func.count().label("count"))
        .where(func.date(Call.started_at) >= range_start)
        .group_by(day_column)
    ).all()
    counts_by_day = {row.day: row.count for row in rows}

    call_volume = [
        CallVolumePoint(date=range_start + timedelta(days=offset), count=counts_by_day.get(range_start + timedelta(days=offset), 0))
        for offset in range(days)
    ]

    return DashboardSummary(
        total_agents=total_agents,
        total_calls=total_calls,
        appointments_booked=appointments_booked,
        calls_in_progress=calls_in_progress,
        call_volume=call_volume,
    )
