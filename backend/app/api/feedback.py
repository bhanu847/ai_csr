import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser, get_db, require_role
from app.fastpath.service import get_instant_answer_model
from app.models.conversation_message import ConversationMessage
from app.models.learned_answer import LearnedAnswer
from app.models.user import Role
from app.rag import learning

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


class FeedbackRequest(BaseModel):
    message_id: uuid.UUID
    helpful: bool
    # The right answer, written by the reviewer. Leave empty on a thumbs-
    # down to have the agent re-answer from its own documents instead.
    correction: str | None = Field(default=None, max_length=2000)
    # Override for the caller question this reply answered -- defaults to
    # the customer message right before it in the transcript.
    question: str | None = Field(default=None, max_length=1000)


class LearnedAnswerResponse(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    question: str
    answer: str | None
    origin: str
    positive: int
    negative: int
    uses: int
    active: bool
    updated_at: datetime

    model_config = {"from_attributes": True}


class FeedbackResponse(BaseModel):
    feedback_id: uuid.UUID
    outcome: str
    message: str
    learned_answer: LearnedAnswerResponse | None


class UpdateLearnedRequest(BaseModel):
    active: bool


@router.post("", response_model=FeedbackResponse)
def submit_feedback(
    body: FeedbackRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(Role.ADMIN, Role.SUPERVISOR)),
) -> FeedbackResponse:
    message = db.execute(
        select(ConversationMessage).where(ConversationMessage.id == body.message_id)
    ).scalar_one_or_none()
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found")

    try:
        outcome = learning.apply_feedback(
            db,
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            message=message,
            helpful=body.helpful,
            correction=body.correction,
            question=body.question,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        # Re-answering from source needs the LLM; nothing is saved if it's down.
        raise HTTPException(
            status_code=502, detail="Could not re-answer from your documents — the AI service may be unavailable."
        ) from exc

    return FeedbackResponse(
        feedback_id=outcome.feedback_id,
        outcome=outcome.outcome,
        message=outcome.message,
        learned_answer=LearnedAnswerResponse.model_validate(outcome.learned) if outcome.learned else None,
    )


@router.get("/learned", response_model=list[LearnedAnswerResponse])
def list_learned(agent_id: uuid.UUID | None = None, db: Session = Depends(get_db)) -> list[LearnedAnswer]:
    query = select(LearnedAnswer).order_by(LearnedAnswer.updated_at.desc())
    if agent_id is not None:
        query = query.where(LearnedAnswer.agent_id == agent_id)
    return list(db.execute(query).scalars())


@router.patch("/learned/{learned_id}", response_model=LearnedAnswerResponse)
def update_learned(
    learned_id: uuid.UUID,
    body: UpdateLearnedRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(Role.ADMIN, Role.SUPERVISOR)),
) -> LearnedAnswer:
    row = db.execute(select(LearnedAnswer).where(LearnedAnswer.id == learned_id)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Learned answer not found")
    row.active = body.active
    db.flush()
    learning.invalidate(row.agent_id)
    return row


@router.get("/fastpath-export")
def export_fastpath_feedback(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(Role.ADMIN)),
) -> dict:
    """Instant-answer ratings as a file for `train_instant_answer_model.py
    --feedback`. These are real caller utterances: review the file before
    training on it, since it gets saved inside the model file."""
    model = get_instant_answer_model()
    answers = {intent_id: intent.answer for intent_id, intent in model.intents.items()} if model else {}
    return learning.fastpath_feedback_export(db, answers)
