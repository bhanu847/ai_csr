import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_db
from app.models.agent import Agent
from app.models.appointment import Appointment
from app.models.call import Call, CallStatus, ResolutionStatus

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# Contact-center benchmark for a human-handled support call — used only to
# turn "calls the AI resolved without escalation" into a dollar estimate.
# This is a stated assumption, not a measured cost; the frontend labels it
# as such rather than presenting it as precise accounting.
ASSUMED_COST_PER_HUMAN_CALL = 12.0


class CallVolumePoint(BaseModel):
    date: date
    count: int


class RecentConversation(BaseModel):
    id: uuid.UUID
    from_number: str
    agent_name: str | None
    intent: str | None
    sentiment: str | None
    resolution_status: str | None
    started_at: datetime


class DashboardSummary(BaseModel):
    total_agents: int
    agents_on_active_calls: int
    total_calls: int
    appointments_booked: int
    calls_in_progress: int
    resolution_rate: float
    escalation_rate: float
    avg_handle_time_seconds: float | None
    cost_saved_estimate: float
    cost_saved_assumption_per_call: float
    call_volume: list[CallVolumePoint]
    recent_conversations: list[RecentConversation]


class IntentCount(BaseModel):
    intent: str
    count: int


class SentimentCount(BaseModel):
    sentiment: str
    count: int


class ResolutionTrendPoint(BaseModel):
    date: date
    resolved: int
    escalated: int
    abandoned: int


class AnalyticsSummary(BaseModel):
    top_intents: list[IntentCount]
    sentiment_mix: list[SentimentCount]
    resolution_trend: list[ResolutionTrendPoint]


@router.get("/summary", response_model=DashboardSummary)
def get_summary(days: int = 14, db: Session = Depends(get_db)) -> DashboardSummary:
    total_agents = db.execute(select(func.count()).select_from(Agent)).scalar_one()
    total_calls = db.execute(select(func.count()).select_from(Call)).scalar_one()
    appointments_booked = db.execute(select(func.count()).select_from(Appointment)).scalar_one()
    calls_in_progress = db.execute(
        select(func.count()).select_from(Call).where(Call.status == CallStatus.IN_PROGRESS)
    ).scalar_one()
    agents_on_active_calls = db.execute(
        select(func.count(func.distinct(Call.agent_id))).where(Call.status == CallStatus.IN_PROGRESS)
    ).scalar_one()

    completed_calls = db.execute(
        select(func.count()).select_from(Call).where(Call.status == CallStatus.COMPLETED)
    ).scalar_one()
    resolved_calls = db.execute(
        select(func.count()).select_from(Call).where(Call.resolution_status == ResolutionStatus.RESOLVED)
    ).scalar_one()
    escalated_calls = db.execute(
        select(func.count()).select_from(Call).where(Call.resolution_status == ResolutionStatus.ESCALATED)
    ).scalar_one()
    resolution_rate = round(resolved_calls / completed_calls * 100, 1) if completed_calls else 0.0
    escalation_rate = round(escalated_calls / completed_calls * 100, 1) if completed_calls else 0.0
    cost_saved_estimate = round(resolved_calls * ASSUMED_COST_PER_HUMAN_CALL, 2)

    avg_handle_time = db.execute(
        select(func.avg(func.extract("epoch", Call.ended_at - Call.started_at))).where(
            Call.status == CallStatus.COMPLETED, Call.ended_at.is_not(None)
        )
    ).scalar_one()
    avg_handle_time_seconds = float(avg_handle_time) if avg_handle_time is not None else None

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

    recent_rows = db.execute(
        select(Call, Agent.name.label("agent_name"))
        .join(Agent, Agent.id == Call.agent_id, isouter=True)
        .order_by(Call.started_at.desc())
        .limit(8)
    ).all()
    recent_conversations = [
        RecentConversation(
            id=row.Call.id,
            from_number=row.Call.from_number,
            agent_name=row.agent_name,
            intent=row.Call.intent,
            sentiment=row.Call.sentiment,
            resolution_status=row.Call.resolution_status.value if row.Call.resolution_status else None,
            started_at=row.Call.started_at,
        )
        for row in recent_rows
    ]

    return DashboardSummary(
        total_agents=total_agents,
        agents_on_active_calls=agents_on_active_calls,
        total_calls=total_calls,
        appointments_booked=appointments_booked,
        calls_in_progress=calls_in_progress,
        resolution_rate=resolution_rate,
        escalation_rate=escalation_rate,
        avg_handle_time_seconds=avg_handle_time_seconds,
        cost_saved_estimate=cost_saved_estimate,
        cost_saved_assumption_per_call=ASSUMED_COST_PER_HUMAN_CALL,
        call_volume=call_volume,
        recent_conversations=recent_conversations,
    )


@router.get("/analytics", response_model=AnalyticsSummary)
def get_analytics(days: int = 14, db: Session = Depends(get_db)) -> AnalyticsSummary:
    today = datetime.now(timezone.utc).date()
    range_start = today - timedelta(days=days - 1)
    in_range = func.date(Call.started_at) >= range_start

    intent_rows = db.execute(
        select(Call.intent, func.count().label("count"))
        .where(Call.intent.is_not(None), in_range)
        .group_by(Call.intent)
        .order_by(func.count().desc())
        .limit(8)
    ).all()
    top_intents = [IntentCount(intent=row.intent, count=row.count) for row in intent_rows]

    sentiment_rows = db.execute(
        select(Call.sentiment, func.count().label("count"))
        .where(Call.sentiment.is_not(None), in_range)
        .group_by(Call.sentiment)
        .order_by(func.count().desc())
    ).all()
    sentiment_mix = [SentimentCount(sentiment=row.sentiment, count=row.count) for row in sentiment_rows]

    day_column = func.date(Call.started_at)
    resolution_rows = db.execute(
        select(day_column.label("day"), Call.resolution_status, func.count().label("count"))
        .where(Call.resolution_status.is_not(None), in_range)
        .group_by(day_column, Call.resolution_status)
    ).all()
    counts_by_day: dict[date, dict[str, int]] = {}
    for row in resolution_rows:
        counts_by_day.setdefault(row.day, {})[row.resolution_status.value] = row.count

    resolution_trend = [
        ResolutionTrendPoint(
            date=(day := range_start + timedelta(days=offset)),
            resolved=counts_by_day.get(day, {}).get("resolved", 0),
            escalated=counts_by_day.get(day, {}).get("escalated", 0),
            abandoned=counts_by_day.get(day, {}).get("abandoned", 0),
        )
        for offset in range(days)
    ]

    return AnalyticsSummary(top_intents=top_intents, sentiment_mix=sentiment_mix, resolution_trend=resolution_trend)
