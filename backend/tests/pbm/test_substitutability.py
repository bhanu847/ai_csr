"""The core claim under test: app.tools.handlers (verify_member,
check_claim_status, get_benefits, search_formulary, find_pharmacy) behaves
correctly when CallContext.pbm is MockPBMProvider -- an implementation with
zero Postgres/SQLAlchemy dependency -- with NOT ONE LINE of handler code
touched to make that work. That is what proves the tool layer depends only
on the PBMProvider interface, not on any concrete backend.

The DB session (ctx.db) is still real Postgres here, because audit logging
is a call-handling concern independent of which PBM data backend is in
use -- only the PBM data lookups are swapped. See app/pbm/provider.py's
module docstring for why that split is deliberate.

This module also proves the second required property: identity
verification is a hard prerequisite for PHI-protected tools, enforced at
the handler layer, so it holds true regardless of which PBMProvider is
plugged in.
"""

import uuid

from app.db.session import tenant_session
from app.pbm.mock_provider import MockPBMProvider
from app.tools.context import CallContext
from app.tools.handlers import build_tool_handlers


def _make_ctx(db, tenant_id):
    return CallContext(
        db=db,
        tenant_id=tenant_id,
        agent_id=uuid.uuid4(),
        call_id=None,
        customer_id=None,
        pbm=MockPBMProvider(),
    )


def test_verify_member_succeeds_against_mock_provider(pbm_test_tenant_id):
    with tenant_session(pbm_test_tenant_id) as db:
        ctx = _make_ctx(db, pbm_test_tenant_id)
        handlers = build_tool_handlers(ctx)

        result = handlers["verify_member"](
            {"member_id": "MOCK-001", "date_of_birth": "1985-03-14", "zip_code": "99501"}
        )

        assert "Identity verified" in result
        assert "Test Member" in result
        assert ctx.verified_member_id == "MOCK-001"


def test_verify_member_fails_closed_against_mock_provider(pbm_test_tenant_id):
    with tenant_session(pbm_test_tenant_id) as db:
        ctx = _make_ctx(db, pbm_test_tenant_id)
        handlers = build_tool_handlers(ctx)

        result = handlers["verify_member"](
            {"member_id": "MOCK-001", "date_of_birth": "1985-03-14", "zip_code": "WRONG"}
        )

        assert "Verification failed" in result
        assert ctx.verified_member_id is None


def test_check_claim_status_requires_verification_regardless_of_provider(pbm_test_tenant_id):
    with tenant_session(pbm_test_tenant_id) as db:
        ctx = _make_ctx(db, pbm_test_tenant_id)
        handlers = build_tool_handlers(ctx)

        # No verify_member call happened -- the gate must trip here, at the
        # handler layer, before the mock provider is ever asked for data.
        result = handlers["check_claim_status"]({})
        assert result.startswith("[VERIFICATION REQUIRED]")


def test_get_benefits_requires_verification_regardless_of_provider(pbm_test_tenant_id):
    with tenant_session(pbm_test_tenant_id) as db:
        ctx = _make_ctx(db, pbm_test_tenant_id)
        handlers = build_tool_handlers(ctx)

        result = handlers["get_benefits"]({})
        assert result.startswith("[VERIFICATION REQUIRED]")


def test_check_claim_status_after_verification_uses_mock_data(pbm_test_tenant_id):
    with tenant_session(pbm_test_tenant_id) as db:
        ctx = _make_ctx(db, pbm_test_tenant_id)
        handlers = build_tool_handlers(ctx)

        handlers["verify_member"]({"member_id": "MOCK-001", "date_of_birth": "1985-03-14", "zip_code": "99501"})
        result = handlers["check_claim_status"]({})

        assert "MOCK-CLM-1" in result
        assert "approved" in result


def test_get_benefits_after_verification_uses_mock_data(pbm_test_tenant_id):
    with tenant_session(pbm_test_tenant_id) as db:
        ctx = _make_ctx(db, pbm_test_tenant_id)
        handlers = build_tool_handlers(ctx)

        handlers["verify_member"]({"member_id": "MOCK-001", "date_of_birth": "1985-03-14", "zip_code": "99501"})
        result = handlers["get_benefits"]({})

        assert "Mock Gold PPO" in result
        assert "$25.00" in result  # copay_primary_care


def test_search_formulary_uses_mock_data_no_verification_needed(pbm_test_tenant_id):
    with tenant_session(pbm_test_tenant_id) as db:
        ctx = _make_ctx(db, pbm_test_tenant_id)
        handlers = build_tool_handlers(ctx)

        # No verify_member call at all -- formulary is not PHI-gated.
        result = handlers["search_formulary"]({"drug_name": "mockcillin"})
        assert "MockCillin" in result
        assert "tier 1" in result


def test_find_pharmacy_uses_mock_data_no_verification_needed(pbm_test_tenant_id):
    with tenant_session(pbm_test_tenant_id) as db:
        ctx = _make_ctx(db, pbm_test_tenant_id)
        handlers = build_tool_handlers(ctx)

        result = handlers["find_pharmacy"]({"zip_code": "99501"})
        assert "Mock Pharmacy" in result

        no_match = handlers["find_pharmacy"]({"zip_code": "00000"})
        assert "No in-network pharmacies" in no_match


def test_link_customer_id_reaches_the_provider(pbm_test_tenant_id):
    """Confirms link_customer_id actually flows through the handler into
    the provider call -- proving the handler passes it generically rather
    than assuming a Postgres-only code path."""
    customer_id = uuid.uuid4()
    with tenant_session(pbm_test_tenant_id) as db:
        ctx = CallContext(
            db=db,
            tenant_id=pbm_test_tenant_id,
            agent_id=uuid.uuid4(),
            call_id=None,
            customer_id=customer_id,
            pbm=MockPBMProvider(),
        )
        handlers = build_tool_handlers(ctx)
        handlers["verify_member"]({"member_id": "MOCK-001", "date_of_birth": "1985-03-14", "zip_code": "99501"})

        assert ctx.pbm.link_customer_id_calls == [("MOCK-001", str(customer_id))]
