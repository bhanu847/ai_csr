import uuid
from collections.abc import Generator
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.security import decode_access_token
from app.db.session import tenant_session
from app.models.user import Role

_bearer_scheme = HTTPBearer()


@dataclass
class CurrentUser:
    id: uuid.UUID
    tenant_id: uuid.UUID
    role: Role
    email: str


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> CurrentUser:
    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    return CurrentUser(
        id=uuid.UUID(payload["sub"]),
        tenant_id=uuid.UUID(payload["tenant_id"]),
        role=Role(payload["role"]),
        email=payload["email"],
    )


def get_db(current_user: CurrentUser = Depends(get_current_user)) -> Generator[Session, None, None]:
    """Tenant-scoped session for any route behind auth — RLS isolation is
    enforced automatically for the tenant in the caller's JWT."""
    with tenant_session(current_user.tenant_id) as db:
        yield db


def require_role(*roles: Role):
    def checker(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if current_user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return current_user

    return checker
