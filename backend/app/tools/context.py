import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session


@dataclass
class CallContext:
    db: Session
    tenant_id: uuid.UUID
    agent_id: uuid.UUID
    call_id: uuid.UUID | None
    # Set by _search_documents when it runs, read back by run_turn so the
    # eventual assistant reply's confidence_score/citations reflect the
    # lookup it was grounded in. Reset per-turn — see agent.run_turn.
    last_confidence: float | None = None
    last_citations: list[dict] | None = None
