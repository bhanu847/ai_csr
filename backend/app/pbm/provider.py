"""The PBM data boundary.

The agent/tool layer (app/tools/handlers.py) must never know whether member,
claim, formulary, and pharmacy data comes from the seeded Postgres tables,
a REST API, a FHIR server, or a real customer's claims/eligibility system.
It only knows this interface. Swap the implementation passed into
CallContext.pbm and every tool that reads PBM data changes backend without
a single line of app/tools/handlers.py changing.

Two implementations exist today:
  - PostgresPBMProvider (postgres_provider.py) -- the seeded dev/test data,
    used in every real call path right now. This is NOT a real PBM
    integration; it is the only backend this project currently has.
  - MockPBMProvider (mock_provider.py) -- a fixed in-memory fake, which
    exists solely to prove in tests that the tool layer only depends on
    this interface, not on Postgres specifically.

A real customer integration (REST/FHIR/their claims platform/etc.) means
writing a third class implementing this same interface. Nothing else in
the call pipeline needs to change for that to work -- that claim is what
tests/pbm/test_substitutability.py exists to check, not just assert.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class MemberRecord:
    """Plain data, not a Member ORM row -- a REST/FHIR-backed provider can
    populate this without ever importing SQLAlchemy."""

    member_id: str
    first_name: str
    last_name: str
    plan_name: str
    group_number: str
    copay_primary_care: float
    copay_specialist: float
    copay_er: float
    deductible: float
    deductible_met: float


@dataclass(frozen=True)
class ClaimRecord:
    claim_number: str
    service_date: date
    provider_name: str
    amount: float
    status: str  # "approved" | "rejected" | "pending" -- see ClaimStatus values
    rejection_reason: str | None = None


@dataclass(frozen=True)
class FormularyEntry:
    name: str
    tier: int
    prior_auth_required: bool
    copay: float
    notes: str | None = None


@dataclass(frozen=True)
class PharmacyRecord:
    name: str
    address: str
    phone: str


class PBMProvider(ABC):
    """A pure data-retrieval boundary. Implementations must NOT do audit
    logging, call-state mutation, or anything else that's a call-handling
    concern rather than a data-access concern -- that stays in
    app/tools/handlers.py, which is the one place that's supposed to know
    it's running inside a phone call."""

    @abstractmethod
    def verify_member(
        self, member_id: str, date_of_birth: date, zip_code: str, link_customer_id: str | None = None
    ) -> MemberRecord | None:
        """Look up a member by the three-factor match (member_id + DOB +
        ZIP) this product verifies identity against. Returns None on any
        mismatch -- deliberately the same response whether the member_id
        doesn't exist at all or exists but DOB/ZIP were wrong, so a caller
        can't use this to enumerate valid member IDs.

        link_customer_id is a Postgres-dev-adapter-specific concept (linking
        the seeded member row to this call's customer_profiles row so
        future calls recognize the same person) -- it's part of the
        interface only so the current adapter can keep doing it without the
        handler reaching into Postgres internals. A real external provider
        has no reason to do anything with it and should ignore it."""

    @abstractmethod
    def get_claims(self, member_id: str, claim_number: str | None = None, limit: int = 1) -> list[ClaimRecord]:
        """Most-recent-first. member_id must already be verified by the
        caller -- this method does not itself enforce that; see
        app.tools.handlers, which gates every call on
        ctx.verified_member_id being set before this is ever invoked."""

    @abstractmethod
    def get_benefits(self, member_id: str) -> MemberRecord | None:
        """Same verification precondition as get_claims."""

    @abstractmethod
    def search_formulary(self, drug_name: str) -> list[FormularyEntry]:
        """Formulary lookups are general plan/network information, not
        tied to one member -- no verification precondition."""

    @abstractmethod
    def find_pharmacy(self, zip_code: str) -> list[PharmacyRecord]:
        """In-network pharmacies only -- no verification precondition."""
