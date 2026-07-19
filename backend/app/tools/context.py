import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session


@dataclass
class CallContext:
    db: Session
    tenant_id: uuid.UUID
    agent_id: uuid.UUID
    call_id: uuid.UUID | None
    customer_id: uuid.UUID | None = None
    department: str = "general"
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
