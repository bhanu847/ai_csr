import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from app.audit import logger as audit
from app.auth.dependencies import CurrentUser, get_current_user
from app.auth.security import create_access_token, hash_password, verify_password
from app.db.session import platform_session, tenant_session
from app.models.tenant import Tenant
from app.models.user import Role, User

router = APIRouter(prefix="/api/auth", tags=["auth"])

_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


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


@router.post("/register-tenant", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register_tenant(body: RegisterTenantRequest) -> TokenResponse:
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
def login(body: LoginRequest) -> TokenResponse:
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


@router.get("/me", response_model=MeResponse)
def me(current_user: CurrentUser = Depends(get_current_user)) -> MeResponse:
    return MeResponse(
        id=current_user.id, tenant_id=current_user.tenant_id, email=current_user.email, role=current_user.role
    )
