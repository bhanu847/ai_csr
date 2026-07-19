import uuid
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@contextmanager
def tenant_session(tenant_id: uuid.UUID) -> Generator[Session, None, None]:
    """Open a DB session scoped to exactly one tenant.

    Every tenant-owned table has a Row-Level Security policy keyed on the
    `app.current_tenant_id` Postgres session variable set here, so tenant
    isolation is enforced by the database itself rather than depending on
    every query remembering a `WHERE tenant_id = ...` clause.
    """
    db = SessionLocal()
    try:
        # set_config(..., true) is the parameterized equivalent of SET LOCAL —
        # Postgres's SET statement itself doesn't accept bind parameters.
        db.execute(text("SELECT set_config('app.current_tenant_id', :tid, true)"), {"tid": str(tenant_id)})
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def platform_session() -> Generator[Session, None, None]:
    """A session with no tenant context set. Only valid for reading the
    (unprotected, root-level) tenants table itself — e.g. resolving a
    tenant slug at login, before we know which tenant a request belongs
    to. Never use this for any tenant-owned table; RLS will simply return
    zero rows since app.current_tenant_id is unset."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
