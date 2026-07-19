import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CustomerProfile(Base):
    """One caller, identified by phone number within a tenant (there's no
    login/identity system on the voice channel — the number is what we
    have). previous_calls/previous_issues/customer_sentiment from the
    product spec are deliberately NOT stored here: they're derived by
    joining `calls` on phone_number (see app.api.customers), so they can
    never go stale relative to the calls that are the source of truth."""

    __tablename__ = "customer_profiles"
    __table_args__ = (UniqueConstraint("tenant_id", "phone_number", name="uq_customer_profiles_tenant_phone"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    phone_number: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    language: Mapped[str | None] = mapped_column(String(20), nullable=True)
    preferences: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), default=dict)
    last_interaction: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
