import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.pbm.postgres_provider import PostgresPBMProvider
from app.pbm.provider import PBMProvider


@dataclass
class CallContext:
    db: Session
    tenant_id: uuid.UUID
    agent_id: uuid.UUID
    call_id: uuid.UUID | None
    customer_id: uuid.UUID | None = None
    department: str = "general"
    # The PBM data backend for verify_member/check_claim_status/get_benefits/
    # search_formulary/find_pharmacy (app.tools.handlers). Defaults to the
    # seeded-Postgres dev adapter -- see app/pbm/provider.py for why the
    # handler layer only ever talks to this interface, never a concrete
    # implementation. Real callers don't need to pass this; tests substitute
    # app.pbm.mock_provider.MockPBMProvider to prove that substitution works.
    pbm: PBMProvider = field(default=None)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.pbm is None:
            self.pbm = PostgresPBMProvider(db=self.db, tenant_id=self.tenant_id)
    # Set by _search_documents when it runs, read back by run_turn so the
    # eventual assistant reply's confidence_score/citations reflect the
    # lookup it was grounded in. Reset per-turn — see agent.run_turn.
    last_confidence: float | None = None
    last_citations: list[dict] | None = None
    # Set by _verify_member once identity is confirmed THIS call. Unlike
    # last_confidence/last_citations, this must survive across turns (not
    # reset each run_turn) — see ConversationSession.verified_member_id
    # and media_stream_handler._run_turn_and_persist, which copies it in
    # and back out each turn since a fresh CallContext is built per turn.
    verified_member_id: str | None = None
