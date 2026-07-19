"""Seed sample PBM data (members, claims, formulary, pharmacies) for a
tenant, so the Phase 7 healthcare tools (verify_member, check_claim_status,
get_benefits, search_formulary, find_pharmacy) have real data to query.

Usage:
    venv/Scripts/python.exe scripts/seed_pbm_data.py [tenant-slug]

Defaults to the first tenant found if no slug is given. Idempotent — safe
to run repeatedly, skips rows that already exist.
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db.session import platform_session, tenant_session  # noqa: E402
from app.models.claim import Claim, ClaimStatus  # noqa: E402
from app.models.drug import Drug  # noqa: E402
from app.models.member import Member  # noqa: E402
from app.models.pharmacy import Pharmacy  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402

MEMBERS = [
    dict(
        member_id="M100234",
        first_name="John",
        last_name="Smith",
        date_of_birth=date(1980, 5, 12),
        zip_code="10001",
        plan_name="Gold PPO",
        group_number="GRP001",
        copay_primary_care=20.0,
        copay_specialist=40.0,
        copay_er=150.0,
        deductible=1500.0,
        deductible_met=500.0,
    ),
    dict(
        member_id="M100567",
        first_name="Maria",
        last_name="Garcia",
        date_of_birth=date(1975, 11, 3),
        zip_code="30301",
        plan_name="Silver HMO",
        group_number="GRP002",
        copay_primary_care=15.0,
        copay_specialist=35.0,
        copay_er=200.0,
        deductible=2000.0,
        deductible_met=2000.0,
    ),
    dict(
        member_id="M100890",
        first_name="David",
        last_name="Lee",
        date_of_birth=date(1990, 2, 28),
        zip_code="60601",
        plan_name="Bronze PPO",
        group_number="GRP003",
        copay_primary_care=30.0,
        copay_specialist=60.0,
        copay_er=300.0,
        deductible=3000.0,
        deductible_met=0.0,
    ),
]

CLAIMS_BY_MEMBER_ID = {
    "M100234": [
        dict(
            claim_number="CLM-0001",
            service_date=date(2026, 6, 1),
            provider_name="City Health Clinic",
            description="Specialty medication - Humira",
            amount=1200.0,
            status=ClaimStatus.REJECTED,
            rejection_reason="Prior authorization required for specialty medication",
        ),
        dict(
            claim_number="CLM-0002",
            service_date=date(2026, 7, 1),
            provider_name="Downtown Pharmacy",
            description="Generic prescription refill",
            amount=45.0,
            status=ClaimStatus.APPROVED,
            rejection_reason=None,
        ),
    ],
    "M100567": [
        dict(
            claim_number="CLM-0003",
            service_date=date(2026, 5, 15),
            provider_name="Atlanta Medical Group",
            description="Annual physical exam",
            amount=250.0,
            status=ClaimStatus.APPROVED,
            rejection_reason=None,
        ),
    ],
    "M100890": [
        dict(
            claim_number="CLM-0004",
            service_date=date(2026, 7, 10),
            provider_name="Chicago Urgent Care",
            description="ER visit - chest pain",
            amount=3200.0,
            status=ClaimStatus.PENDING,
            rejection_reason=None,
        ),
    ],
}

DRUGS = [
    dict(
        name="Humira",
        tier=4,
        prior_auth_required=True,
        copay=150.0,
        notes="Specialty medication — requires prior authorization and specialty pharmacy dispensing.",
    ),
    dict(name="Lipitor", tier=2, prior_auth_required=False, copay=15.0, notes=None),
    dict(name="Metformin", tier=1, prior_auth_required=False, copay=5.0, notes=None),
    dict(
        name="Advair Diskus",
        tier=3,
        prior_auth_required=True,
        copay=60.0,
        notes="Step therapy may apply — try a generic inhaler first.",
    ),
    dict(
        name="Ozempic",
        tier=4,
        prior_auth_required=True,
        copay=125.0,
        notes="Requires diagnosis of type 2 diabetes.",
    ),
    dict(name="Amoxicillin", tier=1, prior_auth_required=False, copay=5.0, notes=None),
    dict(name="Lisinopril", tier=1, prior_auth_required=False, copay=5.0, notes=None),
    dict(name="Xarelto", tier=3, prior_auth_required=False, copay=45.0, notes=None),
]

PHARMACIES = [
    dict(name="Downtown Pharmacy", address="123 Main St", zip_code="10001", phone="(212) 555-0101", in_network=True),
    dict(name="Uptown Drugs", address="456 Park Ave", zip_code="10001", phone="(212) 555-0102", in_network=False),
    dict(
        name="Atlanta Family Pharmacy",
        address="789 Peachtree St",
        zip_code="30301",
        phone="(404) 555-0103",
        in_network=True,
    ),
    dict(
        name="Chicago Loop Pharmacy", address="321 State St", zip_code="60601", phone="(312) 555-0104", in_network=True
    ),
    dict(
        name="Midwest Discount Pharmacy",
        address="654 Wabash Ave",
        zip_code="60601",
        phone="(312) 555-0105",
        in_network=False,
    ),
]


def main() -> None:
    slug = sys.argv[1] if len(sys.argv) > 1 else None

    with platform_session() as db:
        query = select(Tenant)
        if slug:
            query = query.where(Tenant.slug == slug)
        tenant = db.execute(query).scalars().first()

    if tenant is None:
        print(f"No tenant found{f' with slug {slug!r}' if slug else ''}. Aborting.")
        return

    print(f"Seeding PBM data for tenant {tenant.slug!r} ({tenant.id})")

    with tenant_session(tenant.id) as db:
        member_ids_by_code: dict[str, object] = {}

        for m in MEMBERS:
            existing = db.execute(
                select(Member).where(Member.tenant_id == tenant.id, Member.member_id == m["member_id"])
            ).scalar_one_or_none()
            if existing is not None:
                member_ids_by_code[m["member_id"]] = existing.id
                continue
            member = Member(tenant_id=tenant.id, **m)
            db.add(member)
            db.flush()
            member_ids_by_code[m["member_id"]] = member.id
            print(f"  + member {m['member_id']} ({m['first_name']} {m['last_name']})")

        for member_code, claims in CLAIMS_BY_MEMBER_ID.items():
            for c in claims:
                existing = db.execute(
                    select(Claim).where(Claim.tenant_id == tenant.id, Claim.claim_number == c["claim_number"])
                ).scalar_one_or_none()
                if existing is not None:
                    continue
                db.add(Claim(tenant_id=tenant.id, member_id=member_ids_by_code[member_code], **c))
                print(f"  + claim {c['claim_number']} for {member_code}")

        for d in DRUGS:
            existing = db.execute(
                select(Drug).where(Drug.tenant_id == tenant.id, Drug.name == d["name"])
            ).scalar_one_or_none()
            if existing is not None:
                continue
            db.add(Drug(tenant_id=tenant.id, **d))
            print(f"  + drug {d['name']}")

        for p in PHARMACIES:
            existing = db.execute(
                select(Pharmacy).where(
                    Pharmacy.tenant_id == tenant.id, Pharmacy.name == p["name"], Pharmacy.zip_code == p["zip_code"]
                )
            ).scalar_one_or_none()
            if existing is not None:
                continue
            db.add(Pharmacy(tenant_id=tenant.id, **p))
            print(f"  + pharmacy {p['name']} ({p['zip_code']})")

    print("Done.")


if __name__ == "__main__":
    main()
