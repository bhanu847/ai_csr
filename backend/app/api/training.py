import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser, get_db, require_role
from app.conversation.training import analyze_and_store_insights
from app.models.training_insight import InsightCategory, InsightStatus, TrainingInsight
from app.models.user import Role

router = APIRouter(prefix="/api/training", tags=["training"])


class InsightResponse(BaseModel):
    id: uuid.UUID
    category: InsightCategory
    title: str
    description: str
    supporting_call_count: int
    status: InsightStatus
    created_at: datetime

    model_config = {"from_attributes": True}


class UpdateInsightRequest(BaseModel):
    status: InsightStatus


class AnalyzeResponse(BaseModel):
    insights: list[InsightResponse]
    message: str = Field(description="Human-readable summary, e.g. why nothing was found")


@router.get("/insights", response_model=list[InsightResponse])
def list_insights(db: Session = Depends(get_db)) -> list[TrainingInsight]:
    return list(db.execute(select(TrainingInsight).order_by(TrainingInsight.created_at.desc())).scalars())


@router.post("/analyze", response_model=AnalyzeResponse)
def run_analysis(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(Role.ADMIN, Role.SUPERVISOR)),
) -> AnalyzeResponse:
    try:
        insights = analyze_and_store_insights(db, current_user.tenant_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Analysis failed — the AI service may be unavailable.") from exc

    if not insights:
        return AnalyzeResponse(
            insights=[],
            message="No new patterns found. This needs low-confidence answers, escalations, or "
            "low QA scores to analyze — check back after more calls come in.",
        )
    return AnalyzeResponse(insights=insights, message=f"Found {len(insights)} new insight(s).")


@router.patch("/insights/{insight_id}", response_model=InsightResponse)
def update_insight(
    insight_id: uuid.UUID,
    body: UpdateInsightRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(Role.ADMIN, Role.SUPERVISOR)),
) -> TrainingInsight:
    insight = db.execute(select(TrainingInsight).where(TrainingInsight.id == insight_id)).scalar_one_or_none()
    if insight is None:
        raise HTTPException(status_code=404, detail="Insight not found")
    insight.status = body.status
    db.flush()
    return insight
