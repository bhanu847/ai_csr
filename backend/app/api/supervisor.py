import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.calls import CallResponse
from app.audit import logger as audit
from app.auth.dependencies import CurrentUser, get_db, require_role
from app.models.agent import Agent
from app.models.call import Call, CallStatus
from app.models.conversation_message import ConversationMessage
from app.models.customer_profile import CustomerProfile
from app.models.user import Role

router = APIRouter(prefix="/api/supervisor", tags=["supervisor"])


class LiveCallResponse(CallResponse):
    customer_name: str | None
    department: str | None
    ai_paused: bool
    latest_message_role: str | None
    latest_message_preview: str | None
    latest_confidence: float | None


class SuggestionRequest(BaseModel):
    suggestion: str = Field(min_length=1, max_length=1000)


@router.get("/live-calls", response_model=list[LiveCallResponse])
def list_live_calls(db: Session = Depends(get_db)) -> list[dict]:
    # DISTINCT ON (Postgres) picks each call's single most recent message —
    # this is "what is the AI doing right now" for the live-ops view.
    latest_message = (
        select(
            ConversationMessage.call_id,
            ConversationMessage.role,
            ConversationMessage.content,
            ConversationMessage.confidence_score,
        )
        .distinct(ConversationMessage.call_id)
        .order_by(ConversationMessage.call_id, ConversationMessage.timestamp.desc())
        .subquery()
    )

    rows = db.execute(
        select(Call, Agent.name.label("agent_name"), Agent.department, CustomerProfile.name, latest_message)
        .join(Agent, Agent.id == Call.agent_id, isouter=True)
        .join(CustomerProfile, CustomerProfile.id == Call.customer_id, isouter=True)
        .join(latest_message, latest_message.c.call_id == Call.id, isouter=True)
        .where(Call.status == CallStatus.IN_PROGRESS)
        .order_by(Call.started_at.desc())
    ).all()

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
            "customer_name": row.name,
            "department": row.department,
            "ai_paused": row.Call.ai_paused,
            "latest_message_role": row.role,
            "latest_message_preview": row.content,
            "latest_confidence": row.confidence_score,
        }
        for row in rows
    ]


def _get_call(db: Session, call_id: uuid.UUID) -> Call:
    call = db.execute(select(Call).where(Call.id == call_id, Call.status == CallStatus.IN_PROGRESS)).scalar_one_or_none()
    if call is None:
        raise HTTPException(status_code=404, detail="Live call not found")
    return call


@router.post("/calls/{call_id}/pause", status_code=204)
def pause_ai(
    call_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(Role.ADMIN, Role.SUPERVISOR)),
) -> None:
    call = _get_call(db, call_id)
    call.ai_paused = True
    audit.record(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="call.ai_paused",
        resource_type="call",
        resource_id=str(call_id),
    )


@router.post("/calls/{call_id}/resume", status_code=204)
def resume_ai(
    call_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(Role.ADMIN, Role.SUPERVISOR)),
) -> None:
    call = _get_call(db, call_id)
    call.ai_paused = False
    audit.record(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="call.ai_resumed",
        resource_type="call",
        resource_id=str(call_id),
    )


@router.post("/calls/{call_id}/suggest", status_code=204)
def send_suggestion(
    call_id: uuid.UUID,
    body: SuggestionRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(Role.ADMIN, Role.SUPERVISOR)),
) -> None:
    call = _get_call(db, call_id)
    call.pending_suggestion = body.suggestion
    audit.record(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="call.suggestion_sent",
        resource_type="call",
        resource_id=str(call_id),
        metadata={"suggestion": body.suggestion},
    )
