import uuid

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def record(
    db: Session,
    tenant_id: uuid.UUID,
    action: str,
    actor_user_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Write an audit event within the caller's existing transaction. The
    audit_logs table grants this DB role INSERT/SELECT only — no UPDATE or
    DELETE — so nothing here can quietly rewrite history."""
    db.add(
        AuditLog(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            event_metadata=metadata or {},
        )
    )
