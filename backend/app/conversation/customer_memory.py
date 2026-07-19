import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.call import Call, CallStatus
from app.models.customer_profile import CustomerProfile

RECENT_CALLS_FOR_CONTEXT = 3


def get_or_create_profile(db: Session, tenant_id: uuid.UUID, phone_number: str) -> CustomerProfile:
    profile = db.execute(
        select(CustomerProfile).where(
            CustomerProfile.tenant_id == tenant_id, CustomerProfile.phone_number == phone_number
        )
    ).scalar_one_or_none()
    if profile is None:
        profile = CustomerProfile(tenant_id=tenant_id, phone_number=phone_number)
        db.add(profile)
        db.flush()
    profile.last_interaction = datetime.now(timezone.utc)
    return profile


def build_memory_context(db: Session, profile: CustomerProfile) -> str | None:
    """A short internal-use-only briefing for the LLM's system prompt —
    never read aloud, and never containing anything the caller hasn't
    already told this platform on a prior call. Returns None for a
    first-time caller, so the prompt template omits the section entirely."""
    past_calls = (
        db.execute(
            select(Call)
            .where(
                Call.tenant_id == profile.tenant_id,
                Call.customer_id == profile.id,
                Call.status == CallStatus.COMPLETED,
            )
            .order_by(Call.started_at.desc())
            .limit(RECENT_CALLS_FOR_CONTEXT)
        )
        .scalars()
        .all()
    )
    if not past_calls:
        return None

    lines = [f"Returning caller, {len(past_calls)} prior call(s) on record."]
    if profile.name:
        lines.append(f"Name on file: {profile.name}.")
    for call in past_calls:
        when = call.started_at.strftime("%Y-%m-%d")
        issue = call.intent or "not recorded"
        resolution = call.resolution_status.value if call.resolution_status else "unknown"
        lines.append(f"- {when}: issue was '{issue}', resolution: {resolution}.")
    return "\n".join(lines)
