import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Member(Base):
    """A PBM plan member. Verification (verify_member tool) matches on
    member_id + date_of_birth + zip_code — the same three factors named in
    the product spec — before any claim/benefit tool will reveal PHI."""

    __tablename__ = "members"
    __table_args__ = (UniqueConstraint("tenant_id", "member_id", name="uq_members_tenant_member_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customer_profiles.id", ondelete="SET NULL"), nullable=True
    )
    member_id: Mapped[str] = mapped_column(String(32), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    zip_code: Mapped[str] = mapped_column(String(10), nullable=False)

    plan_name: Mapped[str] = mapped_column(String(255), nullable=False)
    group_number: Mapped[str] = mapped_column(String(32), nullable=False)
    copay_primary_care: Mapped[float] = mapped_column(Float, nullable=False)
    copay_specialist: Mapped[float] = mapped_column(Float, nullable=False)
    copay_er: Mapped[float] = mapped_column(Float, nullable=False)
    deductible: Mapped[float] = mapped_column(Float, nullable=False)
    deductible_met: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
