import hashlib
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from app.audit import logger as audit
from app.auth.dependencies import CurrentUser, get_current_user
from app.auth.security import create_access_token, hash_password, verify_password
from app.db.session import platform_session, tenant_session
from app.models.tenant import Tenant
from app.models.user import Role, User
from app.rate_limit import limiter

router = APIRouter(prefix="/api/auth", tags=["auth"])

_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
RESET_TOKEN_TTL_MINUTES = 30


def _hash_reset_token(token: str) -> str:
    # Same principle as password hashing: only the hash is ever stored, so
    # a DB leak alone can't be used to reset anyone's password.
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _utcnow_naive() -> datetime:
    # password_reset_expires_at is a plain (non-timezone) DateTime column,
    # like every other timestamp column in this codebase -- Postgres stores
    # it tz-naive-but-implicitly-UTC, so comparisons must use a naive UTC
    # value too or Python raises on aware-vs-naive comparison.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class RegisterTenantRequest(BaseModel):
    tenant_name: str = Field(min_length=1, max_length=255)
    tenant_slug: str = Field(min_length=1, max_length=100)
    admin_email: EmailStr
    admin_password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    tenant_slug: str
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    role: Role


class ForgotPasswordRequest(BaseModel):
    tenant_slug: str
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    detail: str = "If that account exists, a password reset has been issued."


class ResetPasswordRequest(BaseModel):
    tenant_slug: str
    email: EmailStr
    token: str
    new_password: str = Field(min_length=8)


@router.post("/register-tenant", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/hour")
def register_tenant(request: Request, body: RegisterTenantRequest) -> TokenResponse:
    if not _SLUG_RE.match(body.tenant_slug):
        raise HTTPException(status_code=422, detail="tenant_slug must be lowercase, alphanumeric, hyphen-separated")

    with platform_session() as db:
        existing = db.execute(select(Tenant).where(Tenant.slug == body.tenant_slug)).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(status_code=409, detail="tenant_slug already taken")
        tenant = Tenant(name=body.tenant_name, slug=body.tenant_slug)
        db.add(tenant)
        db.flush()
        tenant_id = tenant.id

    with tenant_session(tenant_id) as db:
        user = User(
            tenant_id=tenant_id,
            email=body.admin_email,
            hashed_password=hash_password(body.admin_password),
            role=Role.ADMIN,
        )
        db.add(user)
        db.flush()
        audit.record(
            db,
            tenant_id=tenant_id,
            actor_user_id=user.id,
            action="tenant.registered",
            resource_type="tenant",
            resource_id=str(tenant_id),
        )
        token = create_access_token(user.id, tenant_id, user.role, user.email)

    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
def login(request: Request, body: LoginRequest) -> TokenResponse:
    with platform_session() as db:
        tenant = db.execute(select(Tenant).where(Tenant.slug == body.tenant_slug)).scalar_one_or_none()
        if tenant is None:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        tenant_id = tenant.id

    with tenant_session(tenant_id) as db:
        user = db.execute(select(User).where(User.email == body.email)).scalar_one_or_none()
        if user is None or user.hashed_password is None or not verify_password(body.password, user.hashed_password):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        audit.record(db, tenant_id=tenant_id, actor_user_id=user.id, action="user.login")
        token = create_access_token(user.id, tenant_id, user.role, user.email)

    return TokenResponse(access_token=token)


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
@limiter.limit("3/hour")
def forgot_password(request: Request, body: ForgotPasswordRequest) -> ForgotPasswordResponse:
    generic_response = ForgotPasswordResponse()

    with platform_session() as db:
        tenant = db.execute(select(Tenant).where(Tenant.slug == body.tenant_slug)).scalar_one_or_none()
    if tenant is None:
        return generic_response  # same response whether or not the tenant/email exists -- no enumeration

    with tenant_session(tenant.id) as db:
        user = db.execute(select(User).where(User.email == body.email)).scalar_one_or_none()
        if user is None or user.hashed_password is None:
            return generic_response  # hashed_password is None for SSO-only accounts -- nothing to reset

        raw_token = secrets.token_urlsafe(32)
        user.password_reset_token_hash = _hash_reset_token(raw_token)
        user.password_reset_expires_at = _utcnow_naive() + timedelta(minutes=RESET_TOKEN_TTL_MINUTES)
        db.flush()

        # No email provider is configured in this environment (see
        # app.tools.handlers._send_email for the same limitation) -- the
        # token is recorded here for a human/future integration to deliver,
        # rather than emailed. It is deliberately NOT returned in the API
        # response: doing so would let anyone request a reset for any email
        # and read back the token themselves, defeating the entire point.
        audit.record(
            db,
            tenant_id=tenant.id,
            actor_user_id=user.id,
            action="user.password_reset_requested",
            resource_type="user",
            resource_id=str(user.id),
            metadata={"reset_token": raw_token, "expires_at": user.password_reset_expires_at.isoformat()},
        )

    return generic_response


@router.post("/reset-password", response_model=TokenResponse)
@limiter.limit("10/hour")
def reset_password(request: Request, body: ResetPasswordRequest) -> TokenResponse:
    with platform_session() as db:
        tenant = db.execute(select(Tenant).where(Tenant.slug == body.tenant_slug)).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    with tenant_session(tenant.id) as db:
        user = db.execute(select(User).where(User.email == body.email)).scalar_one_or_none()
        token_hash = _hash_reset_token(body.token)

        valid = (
            user is not None
            and user.password_reset_token_hash is not None
            and secrets.compare_digest(user.password_reset_token_hash, token_hash)
            and user.password_reset_expires_at is not None
            and user.password_reset_expires_at > _utcnow_naive()
        )
        if not valid:
            raise HTTPException(status_code=400, detail="Invalid or expired reset token")

        user.hashed_password = hash_password(body.new_password)
        user.password_reset_token_hash = None
        user.password_reset_expires_at = None
        db.flush()
        audit.record(db, tenant_id=tenant.id, actor_user_id=user.id, action="user.password_reset_completed")
        token = create_access_token(user.id, tenant.id, user.role, user.email)

    return TokenResponse(access_token=token)


@router.get("/me", response_model=MeResponse)
def me(current_user: CurrentUser = Depends(get_current_user)) -> MeResponse:
    return MeResponse(
        id=current_user.id, tenant_id=current_user.tenant_id, email=current_user.email, role=current_user.role
    )
