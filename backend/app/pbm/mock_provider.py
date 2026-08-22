"""A fixed in-memory PBMProvider with zero Postgres/SQLAlchemy dependency.

This exists for exactly one purpose: proving in tests
(tests/pbm/test_substitutability.py) that app.tools.handlers works
correctly against an implementation that is NOT PostgresPBMProvider,
without changing a single line of handler code. That's the actual evidence
that the tool layer depends only on the PBMProvider interface -- not an
assertion of it.

This is a test fixture, not a second real integration. It is deliberately
tiny and hand-typed, not derived from seed_pbm_data.py, so a test failure
here can't be masked by both sides drifting together.
"""

from dataclasses import dataclass, field
from datetime import date

from app.pbm.provider import (
    ClaimRecord,
    FormularyEntry,
    MemberRecord,
    PBMProvider,
    PharmacyRecord,
    normalize_claim_number,
)


@dataclass
class _MockMember:
    record: MemberRecord
    date_of_birth: date
    zip_code: str
    claims: list[ClaimRecord] = field(default_factory=list)


class MockPBMProvider(PBMProvider):
    def __init__(self) -> None:
        self._members: dict[str, _MockMember] = {
            "MOCK-001": _MockMember(
                record=MemberRecord(
                    member_id="MOCK-001",
                    first_name="Test",
                    last_name="Member",
                    plan_name="Mock Gold PPO",
                    group_number="MOCKGRP1",
                    copay_primary_care=25.0,
                    copay_specialist=50.0,
                    copay_er=175.0,
                    deductible=1000.0,
                    deductible_met=250.0,
                ),
                date_of_birth=date(1985, 3, 14),
                zip_code="99501",
                claims=[
                    ClaimRecord(
                        claim_number="MOCK-CLM-1",
                        service_date=date(2026, 1, 10),
                        provider_name="Mock Clinic",
                        amount=80.0,
                        status="approved",
                    ),
                ],
            ),
        }
        self.link_customer_id_calls: list[tuple[str, str]] = []  # recorded for test assertions

        self._formulary = [
            FormularyEntry(name="MockCillin", tier=1, prior_auth_required=False, copay=5.0, notes=None),
        ]
        # PharmacyRecord has no zip_code field (the real output text never
        # includes one), so ZIP is tracked alongside it here, mirroring how
        # PostgresPBMProvider filters by ZIP before ever building the record.
        self._pharmacies_by_zip: dict[str, list[PharmacyRecord]] = {
            "99501": [PharmacyRecord(name="Mock Pharmacy", address="1 Test Way", phone="555-0100")],
        }

    def verify_member(
        self, member_id: str, date_of_birth: date, zip_code: str, link_customer_id: str | None = None
    ) -> MemberRecord | None:
        member = self._members.get(member_id)
        if member is None or member.date_of_birth != date_of_birth or member.zip_code != zip_code:
            return None
        if link_customer_id is not None:
            self.link_customer_id_calls.append((member_id, link_customer_id))
        return member.record

    def get_claims(self, member_id: str, claim_number: str | None = None, limit: int = 1) -> list[ClaimRecord]:
        member = self._members.get(member_id)
        if member is None:
            return []
        claims = member.claims
        if claim_number:
            normalized = normalize_claim_number(claim_number)
            claims = [c for c in claims if normalize_claim_number(c.claim_number) == normalized]
        return sorted(claims, key=lambda c: c.service_date, reverse=True)[:limit]

    def get_benefits(self, member_id: str) -> MemberRecord | None:
        member = self._members.get(member_id)
        return member.record if member is not None else None

    def search_formulary(self, drug_name: str) -> list[FormularyEntry]:
        return [d for d in self._formulary if drug_name.lower() in d.name.lower()]

    def find_pharmacy(self, zip_code: str) -> list[PharmacyRecord]:
        return list(self._pharmacies_by_zip.get(zip_code, []))
