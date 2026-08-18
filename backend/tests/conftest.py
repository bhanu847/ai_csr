"""Shared pytest fixtures. These tests hit a real Postgres database (the
same one the app runs against locally) -- they are integration tests, not
pure unit tests, and require the DB configured in backend/.env to be
reachable with migrations applied."""

import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, delete  # noqa: E402

from app.config import settings  # noqa: E402
from app.db.session import platform_session, tenant_session  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402


@pytest.fixture(scope="module")
def pbm_test_tenant_id():
    """A throwaway tenant, isolated from any real tenant, that exists only
    for the duration of the test module. Deleting it cascades (ON DELETE
    CASCADE on tenant_id) to every row created under it."""
    tenant_id = uuid.uuid4()
    slug = f"pytest-pbm-{tenant_id.hex[:12]}"

    with platform_session() as db:
        db.add(Tenant(id=tenant_id, name="Pytest PBM Test Tenant", slug=slug))

    yield tenant_id

    # app_user (the runtime role platform_session/tenant_session connect
    # as) deliberately has no DELETE grant on tenants -- there's no
    # "delete my account" feature, so it was never granted (confirmed by
    # this fixture failing with InsufficientPrivilege before this fix).
    # That's real, working least-privilege enforcement, not a bug to work
    # around by widening app_user's grants -- so cleanup uses the
    # migrations (superuser) connection instead, same as Alembic does.
    cleanup_engine = create_engine(settings.migrations_database_url)
    with cleanup_engine.begin() as conn:
        conn.execute(delete(Tenant).where(Tenant.id == tenant_id))
    cleanup_engine.dispose()
