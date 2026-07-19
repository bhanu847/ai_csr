import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session


@dataclass
class CallContext:
    db: Session
    tenant_id: uuid.UUID
    agent_id: uuid.UUID
    call_id: uuid.UUID | None
