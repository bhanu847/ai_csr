"""Bulk import for PBM reference data (members/claims/drugs/pharmacies) from
CSV exports. The frontend parses the CSV and maps columns to our field names
client-side (see data-import.component.ts); this endpoint receives already-
mapped JSON rows and validates/upserts them one at a time, so one bad row
(a typo'd date, a missing field) doesn't block the rest of the batch — the
same reason a single failed call shouldn't crash a webhook elsewhere in
this codebase."""

from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import logger as audit
from app.auth.dependencies import CurrentUser, get_db, require_role
from app.models.claim import Claim, ClaimStatus
from app.models.drug import Drug
from app.models.member import Member
from app.models.pharmacy import Pharmacy
from app.models.user import Role

router = APIRouter(prefix="/api/import", tags=["data-import"])


class ImportRequest(BaseModel):
    records: list[dict]


class RowError(BaseModel):
    row: int
    message: str


class ImportResult(BaseModel):
    created: int
    updated: int
    errors: list[RowError]


def _format_validation_error(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        field = ".".join(str(loc) for loc in err["loc"])
        parts.append(f"{field}: {err['msg']}")
    return "; ".join(parts)


# --- Row schemas -------------------------------------------------------


class MemberRow(BaseModel):
    member_id: str = Field(min_length=1, max_length=32)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    date_of_birth: date
    zip_code: str = Field(min_length=1, max_length=10)
    plan_name: str = Field(min_length=1, max_length=255)
    group_number: str = Field(min_length=1, max_length=32)
    copay_primary_care: float
    copay_specialist: float
    copay_er: float
    deductible: float
    deductible_met: float = 0.0


class ClaimRow(BaseModel):
    claim_number: str = Field(min_length=1, max_length=32)
    member_id: str = Field(min_length=1, max_length=32)  # business key, resolved below
    service_date: date
    provider_name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=500)
    amount: float
    status: ClaimStatus
    rejection_reason: str | None = Field(default=None, max_length=500)


class DrugRow(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    tier: int
    prior_auth_required: bool = False
    copay: float
    notes: str | None = Field(default=None, max_length=500)


class PharmacyRow(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    address: str = Field(min_length=1, max_length=500)
    zip_code: str = Field(min_length=1, max_length=10)
    phone: str = Field(min_length=1, max_length=32)
    in_network: bool = True


# --- Endpoints -----------------------------------------------------------


@router.post("/members", response_model=ImportResult)
def import_members(
    body: ImportRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(Role.ADMIN, Role.AGENT_BUILDER)),
) -> ImportResult:
    created = updated = 0
    errors: list[RowError] = []

    for i, raw in enumerate(body.records, start=1):
        try:
            row = MemberRow.model_validate(raw)
        except ValidationError as exc:
            errors.append(RowError(row=i, message=_format_validation_error(exc)))
            continue

        existing = db.execute(
            select(Member).where(Member.tenant_id == current_user.tenant_id, Member.member_id == row.member_id)
        ).scalar_one_or_none()
        if existing is not None:
            for field, value in row.model_dump().items():
                setattr(existing, field, value)
            updated += 1
        else:
            db.add(Member(tenant_id=current_user.tenant_id, **row.model_dump()))
            created += 1

    db.flush()
    audit.record(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="data.imported",
        resource_type="member",
        metadata={"created": created, "updated": updated, "error_count": len(errors)},
    )
    return ImportResult(created=created, updated=updated, errors=errors)


@router.post("/claims", response_model=ImportResult)
def import_claims(
    body: ImportRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(Role.ADMIN, Role.AGENT_BUILDER)),
) -> ImportResult:
    created = updated = 0
    errors: list[RowError] = []

    for i, raw in enumerate(body.records, start=1):
        try:
            row = ClaimRow.model_validate(raw)
        except ValidationError as exc:
            errors.append(RowError(row=i, message=_format_validation_error(exc)))
            continue

        member = db.execute(
            select(Member).where(Member.tenant_id == current_user.tenant_id, Member.member_id == row.member_id)
        ).scalar_one_or_none()
        if member is None:
            errors.append(RowError(row=i, message=f"member_id '{row.member_id}' not found — import members first"))
            continue

        values = row.model_dump(exclude={"member_id"})
        existing = db.execute(
            select(Claim).where(Claim.tenant_id == current_user.tenant_id, Claim.claim_number == row.claim_number)
        ).scalar_one_or_none()
        if existing is not None:
            for field, value in values.items():
                setattr(existing, field, value)
            existing.member_id = member.id
            updated += 1
        else:
            db.add(Claim(tenant_id=current_user.tenant_id, member_id=member.id, **values))
            created += 1

    db.flush()
    audit.record(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="data.imported",
        resource_type="claim",
        metadata={"created": created, "updated": updated, "error_count": len(errors)},
    )
    return ImportResult(created=created, updated=updated, errors=errors)


@router.post("/drugs", response_model=ImportResult)
def import_drugs(
    body: ImportRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(Role.ADMIN, Role.AGENT_BUILDER)),
) -> ImportResult:
    created = updated = 0
    errors: list[RowError] = []

    for i, raw in enumerate(body.records, start=1):
        try:
            row = DrugRow.model_validate(raw)
        except ValidationError as exc:
            errors.append(RowError(row=i, message=_format_validation_error(exc)))
            continue

        existing = db.execute(
            select(Drug).where(Drug.tenant_id == current_user.tenant_id, Drug.name == row.name)
        ).scalar_one_or_none()
        if existing is not None:
            for field, value in row.model_dump().items():
                setattr(existing, field, value)
            updated += 1
        else:
            db.add(Drug(tenant_id=current_user.tenant_id, **row.model_dump()))
            created += 1

    db.flush()
    audit.record(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="data.imported",
        resource_type="drug",
        metadata={"created": created, "updated": updated, "error_count": len(errors)},
    )
    return ImportResult(created=created, updated=updated, errors=errors)


@router.post("/pharmacies", response_model=ImportResult)
def import_pharmacies(
    body: ImportRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(Role.ADMIN, Role.AGENT_BUILDER)),
) -> ImportResult:
    created = updated = 0
    errors: list[RowError] = []

    for i, raw in enumerate(body.records, start=1):
        try:
            row = PharmacyRow.model_validate(raw)
        except ValidationError as exc:
            errors.append(RowError(row=i, message=_format_validation_error(exc)))
            continue

        existing = db.execute(
            select(Pharmacy).where(
                Pharmacy.tenant_id == current_user.tenant_id,
                Pharmacy.name == row.name,
                Pharmacy.zip_code == row.zip_code,
            )
        ).scalar_one_or_none()
        if existing is not None:
            for field, value in row.model_dump().items():
                setattr(existing, field, value)
            updated += 1
        else:
            db.add(Pharmacy(tenant_id=current_user.tenant_id, **row.model_dump()))
            created += 1

    db.flush()
    audit.record(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="data.imported",
        resource_type="pharmacy",
        metadata={"created": created, "updated": updated, "error_count": len(errors)},
    )
    return ImportResult(created=created, updated=updated, errors=errors)
