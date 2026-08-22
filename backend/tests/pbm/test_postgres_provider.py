"""Proves PostgresPBMProvider -- the adapter every real call path uses
today -- still produces the exact same results after being extracted out
of app/tools/handlers.py into app/pbm/postgres_provider.py. This is an
integration test against a real (throwaway) tenant in the actual
configured database, not a mock."""

import uuid
from datetime import date

from app.db.session import tenant_session
from app.models.claim import Claim, ClaimStatus
from app.models.drug import Drug
from app.models.member import Member
from app.models.pharmacy import Pharmacy
from app.pbm.postgres_provider import PostgresPBMProvider

MEMBER_ID = "PBMTEST-001"
DOB = date(1988, 4, 20)
ZIP = "94107"


def _seed(db, tenant_id):
    member = Member(
        tenant_id=tenant_id,
        member_id=MEMBER_ID,
        first_name="Ada",
        last_name="Lovelace",
        date_of_birth=DOB,
        zip_code=ZIP,
        plan_name="Analytical PPO",
        group_number="GRP-AE1",
        copay_primary_care=20.0,
        copay_specialist=40.0,
        copay_er=150.0,
        deductible=1000.0,
        deductible_met=100.0,
    )
    db.add(member)
    db.flush()

    db.add(
        Claim(
            tenant_id=tenant_id,
            member_id=member.id,
            claim_number="PBMTEST-CLM-OLD",
            service_date=date(2026, 1, 1),
            provider_name="Old Provider",
            description="Older claim",
            amount=10.0,
            status=ClaimStatus.APPROVED,
        )
    )
    db.add(
        Claim(
            tenant_id=tenant_id,
            member_id=member.id,
            claim_number="PBMTEST-CLM-NEW",
            service_date=date(2026, 6, 1),
            provider_name="New Provider",
            description="Newer, rejected claim",
            amount=500.0,
            status=ClaimStatus.REJECTED,
            rejection_reason="Not covered under this plan",
        )
    )
    db.add(
        Drug(
            tenant_id=tenant_id,
            name="Testolol",
            tier=2,
            prior_auth_required=True,
            copay=30.0,
            notes="Test fixture drug",
        )
    )
    db.add(
        Pharmacy(
            tenant_id=tenant_id,
            name="In-Network Test Pharmacy",
            address="1 Fixture Way",
            zip_code=ZIP,
            phone="555-0001",
            in_network=True,
        )
    )
    db.add(
        Pharmacy(
            tenant_id=tenant_id,
            name="Out-Of-Network Test Pharmacy",
            address="2 Fixture Way",
            zip_code=ZIP,
            phone="555-0002",
            in_network=False,
        )
    )
    return member.id


def test_verify_member_correct_credentials(pbm_test_tenant_id):
    with tenant_session(pbm_test_tenant_id) as db:
        _seed(db, pbm_test_tenant_id)
        db.flush()

        provider = PostgresPBMProvider(db, pbm_test_tenant_id)
        record = provider.verify_member(MEMBER_ID, DOB, ZIP)

        assert record is not None
        assert record.member_id == MEMBER_ID
        assert record.first_name == "Ada"
        assert record.plan_name == "Analytical PPO"
        assert record.copay_primary_care == 20.0


def test_verify_member_wrong_zip_fails_closed(pbm_test_tenant_id):
    with tenant_session(pbm_test_tenant_id) as db:
        provider = PostgresPBMProvider(db, pbm_test_tenant_id)
        # Same member_id + DOB, wrong ZIP -- must fail, not partially match.
        assert provider.verify_member(MEMBER_ID, DOB, "00000") is None


def test_verify_member_unknown_id_fails_closed(pbm_test_tenant_id):
    with tenant_session(pbm_test_tenant_id) as db:
        provider = PostgresPBMProvider(db, pbm_test_tenant_id)
        assert provider.verify_member("NO-SUCH-MEMBER", DOB, ZIP) is None


def test_get_claims_returns_most_recent_first(pbm_test_tenant_id):
    with tenant_session(pbm_test_tenant_id) as db:
        provider = PostgresPBMProvider(db, pbm_test_tenant_id)
        claims = provider.get_claims(MEMBER_ID, limit=1)

        assert len(claims) == 1
        assert claims[0].claim_number == "PBMTEST-CLM-NEW"
        assert claims[0].status == "rejected"
        assert claims[0].rejection_reason == "Not covered under this plan"


def test_get_claims_filters_by_claim_number(pbm_test_tenant_id):
    with tenant_session(pbm_test_tenant_id) as db:
        provider = PostgresPBMProvider(db, pbm_test_tenant_id)
        claims = provider.get_claims(MEMBER_ID, claim_number="PBMTEST-CLM-OLD")

        assert len(claims) == 1
        assert claims[0].claim_number == "PBMTEST-CLM-OLD"
        assert claims[0].status == "approved"


def test_get_claims_filters_tolerate_spoken_formatting(pbm_test_tenant_id):
    """Regression test for a real bug found on a live call, 2026-08-22:
    STT transcribed a spoken claim number's dash as a space ("CLM 90001"
    vs. the stored "CLM-90001"), and an exact-string-match lookup silently
    failed on a claim that genuinely existed -- triggering an unnecessary
    escalation for an already-verified caller."""
    with tenant_session(pbm_test_tenant_id) as db:
        provider = PostgresPBMProvider(db, pbm_test_tenant_id)
        claims = provider.get_claims(MEMBER_ID, claim_number="pbmtest clm old")

        assert len(claims) == 1
        assert claims[0].claim_number == "PBMTEST-CLM-OLD"


def test_get_benefits_matches_verify_member_data(pbm_test_tenant_id):
    with tenant_session(pbm_test_tenant_id) as db:
        provider = PostgresPBMProvider(db, pbm_test_tenant_id)
        benefits = provider.get_benefits(MEMBER_ID)

        assert benefits is not None
        assert benefits.deductible == 1000.0
        assert benefits.deductible_met == 100.0


def test_search_formulary_case_insensitive_partial_match(pbm_test_tenant_id):
    with tenant_session(pbm_test_tenant_id) as db:
        provider = PostgresPBMProvider(db, pbm_test_tenant_id)
        results = provider.search_formulary("testolol")

        assert len(results) == 1
        assert results[0].name == "Testolol"
        assert results[0].prior_auth_required is True


def test_find_pharmacy_only_returns_in_network(pbm_test_tenant_id):
    with tenant_session(pbm_test_tenant_id) as db:
        provider = PostgresPBMProvider(db, pbm_test_tenant_id)
        results = provider.find_pharmacy(ZIP)

        names = {p.name for p in results}
        assert "In-Network Test Pharmacy" in names
        assert "Out-Of-Network Test Pharmacy" not in names


def test_verify_member_links_customer_id_once(pbm_test_tenant_id):
    """The Postgres-specific enrichment: a first verification links the
    seeded member row to a customer profile; a second verification with a
    DIFFERENT customer_id must not steal the link."""
    from sqlalchemy import select

    from app.models.customer_profile import CustomerProfile

    with tenant_session(pbm_test_tenant_id) as db:
        profile_a = CustomerProfile(tenant_id=pbm_test_tenant_id, phone_number="+15550000001")
        profile_b = CustomerProfile(tenant_id=pbm_test_tenant_id, phone_number="+15550000002")
        db.add(profile_a)
        db.add(profile_b)
        db.flush()
        customer_id_a, customer_id_b = profile_a.id, profile_b.id

    with tenant_session(pbm_test_tenant_id) as db:
        provider = PostgresPBMProvider(db, pbm_test_tenant_id)
        provider.verify_member(MEMBER_ID, DOB, ZIP, link_customer_id=str(customer_id_a))

    with tenant_session(pbm_test_tenant_id) as db:
        provider = PostgresPBMProvider(db, pbm_test_tenant_id)
        provider.verify_member(MEMBER_ID, DOB, ZIP, link_customer_id=str(customer_id_b))

        member = db.execute(select(Member).where(Member.member_id == MEMBER_ID)).scalar_one()
        assert member.customer_id == customer_id_a
