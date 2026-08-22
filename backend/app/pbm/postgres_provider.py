"""The seeded-Postgres PBM adapter -- this is the ONLY backend this project
has today. It is a development/test fixture, not a real PBM integration;
see backend/scripts/seed_pbm_data.py for what data it actually contains.
Do not describe this adapter as connected to a real healthcare system
anywhere in product-facing material."""

import uuid
from datetime import date

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.claim import Claim
from app.models.drug import Drug
from app.models.member import Member
from app.models.pharmacy import Pharmacy
from app.pbm.provider import (
    ClaimRecord,
    FormularyEntry,
    MemberRecord,
    PBMProvider,
    PharmacyRecord,
    normalize_claim_number,
)


def _to_member_record(member: Member) -> MemberRecord:
    return MemberRecord(
        member_id=member.member_id,
        first_name=member.first_name,
        last_name=member.last_name,
        plan_name=member.plan_name,
        group_number=member.group_number,
        copay_primary_care=member.copay_primary_care,
        copay_specialist=member.copay_specialist,
        copay_er=member.copay_er,
        deductible=member.deductible,
        deductible_met=member.deductible_met,
    )


class PostgresPBMProvider(PBMProvider):
    def __init__(self, db: Session, tenant_id: uuid.UUID) -> None:
        self._db = db
        self._tenant_id = tenant_id

    def verify_member(
        self, member_id: str, date_of_birth: date, zip_code: str, link_customer_id: str | None = None
    ) -> MemberRecord | None:
        member = self._db.execute(
            select(Member).where(
                Member.tenant_id == self._tenant_id,
                Member.member_id == member_id,
                Member.date_of_birth == date_of_birth,
                Member.zip_code == zip_code,
            )
        ).scalar_one_or_none()
        if member is None:
            return None

        # Opportunistic enrichment specific to this dev adapter: link the
        # seeded member row to the caller's customer profile so a repeat
        # caller resolves to the same member next time. A real external
        # PBM provider has no equivalent operation and would ignore
        # link_customer_id entirely.
        if link_customer_id is not None and member.customer_id is None:
            self._db.execute(
                update(Member).where(Member.id == member.id).values(customer_id=uuid.UUID(link_customer_id))
            )

        return _to_member_record(member)

    def get_claims(self, member_id: str, claim_number: str | None = None, limit: int = 1) -> list[ClaimRecord]:
        member = self._db.execute(
            select(Member).where(Member.tenant_id == self._tenant_id, Member.member_id == member_id)
        ).scalar_one_or_none()
        if member is None:
            return []

        query = select(Claim).where(Claim.tenant_id == self._tenant_id, Claim.member_id == member.id)
        if claim_number:
            normalized = normalize_claim_number(claim_number)
            db_normalized = func.replace(func.replace(func.upper(Claim.claim_number), "-", ""), " ", "")
            query = query.where(db_normalized == normalized)
        query = query.order_by(Claim.service_date.desc()).limit(limit)

        claims = self._db.execute(query).scalars().all()
        return [
            ClaimRecord(
                claim_number=c.claim_number,
                service_date=c.service_date,
                provider_name=c.provider_name,
                amount=c.amount,
                status=c.status.value,
                rejection_reason=c.rejection_reason,
            )
            for c in claims
        ]

    def get_benefits(self, member_id: str) -> MemberRecord | None:
        member = self._db.execute(
            select(Member).where(Member.tenant_id == self._tenant_id, Member.member_id == member_id)
        ).scalar_one_or_none()
        return _to_member_record(member) if member is not None else None

    def search_formulary(self, drug_name: str) -> list[FormularyEntry]:
        drugs = (
            self._db.execute(
                select(Drug).where(Drug.tenant_id == self._tenant_id, Drug.name.ilike(f"%{drug_name}%"))
            )
            .scalars()
            .all()
        )
        return [
            FormularyEntry(
                name=d.name, tier=d.tier, prior_auth_required=d.prior_auth_required, copay=d.copay, notes=d.notes
            )
            for d in drugs
        ]

    def find_pharmacy(self, zip_code: str) -> list[PharmacyRecord]:
        pharmacies = (
            self._db.execute(
                select(Pharmacy).where(
                    Pharmacy.tenant_id == self._tenant_id,
                    Pharmacy.zip_code == zip_code,
                    Pharmacy.in_network == True,  # noqa: E712
                )
            )
            .scalars()
            .all()
        )
        return [PharmacyRecord(name=p.name, address=p.address, phone=p.phone) for p in pharmacies]
