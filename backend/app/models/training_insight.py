import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class InsightCategory(str, enum.Enum):
    MISSING_KNOWLEDGE = "missing_knowledge"
    PROMPT_IMPROVEMENT = "prompt_improvement"
    WORKFLOW_IMPROVEMENT = "workflow_improvement"


class InsightStatus(str, enum.Enum):
    NEW = "new"
    ACKNOWLEDGED = "acknowledged"
    DISMISSED = "dismissed"


class TrainingInsight(Base):
    """One recurring pattern surfaced by app.conversation.training across
    many calls (low-confidence answers, escalations, low QA scores) — a
    synthesized recommendation, not raw derivable data, so unlike most
    Call-derived fields it's worth persisting: regenerating it costs an
    LLM call, and a supervisor needs to track whether it's been acted on."""

    __tablename__ = "training_insights"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[InsightCategory] = mapped_column(Enum(InsightCategory, name="insight_category"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(2000), nullable=False)
    supporting_call_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[InsightStatus] = mapped_column(
        Enum(InsightStatus, name="insight_status"), nullable=False, default=InsightStatus.NEW
    )
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
