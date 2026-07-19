import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Agent(Base):
    """An AI employee: persona + voice + its own knowledge base (Phase 1
    Agent Studio). `is_default` picks which agent answers calls to a
    tenant's number until routing rules exist (Phase 2+)."""

    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    persona: Mapped[str] = mapped_column(String(2000), nullable=False, default="")
    voice: Mapped[str] = mapped_column(String(100), nullable=False, default="en-IN-NeerjaNeural")
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # "general" (the default/router agent) or a specialist bucket — see
    # app.tools.department_tools and app.conversation.router. Free-text
    # rather than an enum so a tenant can name their own departments.
    department: Mapped[str] = mapped_column(String(50), nullable=False, default="general")
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
