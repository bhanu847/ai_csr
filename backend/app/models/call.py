import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Enum, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CallStatus(str, enum.Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class ResolutionStatus(str, enum.Enum):
    """Set by the tool layer (escalated, the moment escalate_to_human runs)
    or defaulted at call end (resolved/abandoned) — see
    app.tools.handlers._escalate_to_human and app.api.twilio_webhooks."""

    RESOLVED = "resolved"
    ESCALATED = "escalated"
    ABANDONED = "abandoned"


class Call(Base):
    __tablename__ = "calls"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    twilio_call_sid: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    from_number: Mapped[str] = mapped_column(String(32), nullable=False)
    to_number: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[CallStatus] = mapped_column(
        Enum(CallStatus, name="call_status"), nullable=False, default=CallStatus.IN_PROGRESS
    )
    started_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    ended_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Populated by later phases (call-summary generation, confidence engine)
    # — left null by Phase 1, which only wires up transcript storage.
    intent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sentiment: Mapped[str | None] = mapped_column(String(50), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    summary: Mapped[str | None] = mapped_column(String, nullable=True)
    resolution_status: Mapped[ResolutionStatus | None] = mapped_column(
        Enum(ResolutionStatus, name="resolution_status"), nullable=True
    )
