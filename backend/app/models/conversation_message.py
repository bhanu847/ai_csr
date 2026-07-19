import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Enum, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MessageRole(str, enum.Enum):
    CUSTOMER = "customer"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ConversationMessage(Base):
    """One turn of a call's transcript. Append-only (see migration grants) —
    a call recording shouldn't be editable after the fact, same reasoning
    as AuditLog."""

    __tablename__ = "conversation_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    call_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("calls.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[MessageRole] = mapped_column(Enum(MessageRole, name="message_role"), nullable=False)
    content: Mapped[str] = mapped_column(String, nullable=False)
    message_type: Mapped[str] = mapped_column(String(50), nullable=False, default="text")
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    # [{"filename": ..., "page": ..., "confidence": ...}, ...] — the RAG
    # chunks this reply was grounded in, for the trust/audit trail. Kept
    # separate from `content` since the spoken reply never reads these out.
    citations: Mapped[list | None] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
