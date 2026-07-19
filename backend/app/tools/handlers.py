from collections.abc import Callable
from datetime import date

from sqlalchemy import select, update

from app import confidence_service
from app.audit import logger as audit
from app.models.appointment import Appointment
from app.models.call import Call, ResolutionStatus
from app.models.claim import Claim, ClaimStatus
from app.models.customer_profile import CustomerProfile
from app.models.drug import Drug
from app.models.member import Member
from app.models.pharmacy import Pharmacy
from app.models.ticket import Ticket
from app.rag import service as rag_service
from app.tools.context import CallContext


def _search_documents(ctx: CallContext, args: dict) -> str:
    results = rag_service.search(ctx.db, ctx.agent_id, args["query"], k=4)
    result = confidence_service.evaluate(results)
    ctx.last_confidence = result.score
    directive = f"[CONFIDENCE: {result.score}% — {result.band.value.upper()}] {confidence_service.build_directive(result)}"

    if not results or result.band == confidence_service.ConfidenceBand.LOW:
        # Withhold the (unreliable) chunk text entirely — a weak match is
        # treated the same as no match, not handed to the LLM to answer from.
        ctx.last_citations = None
        return directive

    # Structured, per-chunk citations for the trust/audit trail (shown in
    # the supervisor transcript UI) — kept separate from the spoken reply,
    # which per the voice rules below never reads out filenames.
    ctx.last_citations = [
        {
            "filename": r["filename"],
            "page": r["page"],
            "confidence": confidence_service.score_from_distance(r["distance"]),
        }
        for r in results
    ]

    lines = [directive, ""]
    for r in results:
        citation = r["filename"] + (f" (page {r['page']})" if r["page"] else "")
        lines.append(f"[{citation}]: {r['text']}")
    return "\n".join(lines)


def _schedule_appointment(ctx: CallContext, args: dict) -> str:
    appointment = Appointment(
        tenant_id=ctx.tenant_id,
        agent_id=ctx.agent_id,
        call_id=ctx.call_id,
        caller_name=args["name"],
        caller_phone=args["phone"],
        preferred_time=args["preferred_time"],
        reason=args.get("reason", ""),
    )
    ctx.db.add(appointment)
    ctx.db.flush()
    audit.record(
        ctx.db,
        tenant_id=ctx.tenant_id,
        action="appointment.scheduled",
        resource_type="appointment",
        resource_id=str(appointment.id),
        metadata={"name": args["name"], "preferred_time": args["preferred_time"]},
    )

    # Opportunistic enrichment — this is the only place a caller's name is
    # captured today, so feed it back into their profile for next time.
    if ctx.customer_id is not None:
        ctx.db.execute(
            update(CustomerProfile)
            .where(CustomerProfile.id == ctx.customer_id, CustomerProfile.name.is_(None))
            .values(name=args["name"])
        )

    return f"Appointment booked for {args['name']} at {args['preferred_time']}."


def _escalate_to_human(ctx: CallContext, args: dict) -> str:
    if ctx.call_id is not None:
        ctx.db.execute(
            update(Call).where(Call.id == ctx.call_id).values(resolution_status=ResolutionStatus.ESCALATED)
        )
    audit.record(
        ctx.db,
        tenant_id=ctx.tenant_id,
        action="call.escalated",
        resource_type="call",
        resource_id=str(ctx.call_id) if ctx.call_id else None,
        metadata={"reason": args["reason"]},
    )
    return f"Escalation logged: {args['reason']}. A human will follow up."


def _verify_member(ctx: CallContext, args: dict) -> str:
    try:
        dob = date.fromisoformat(args["date_of_birth"])
    except ValueError:
        return "That date of birth wasn't understood — ask for it as year-month-day."

    member = ctx.db.execute(
        select(Member).where(
            Member.tenant_id == ctx.tenant_id,
            Member.member_id == args["member_id"],
            Member.date_of_birth == dob,
            Member.zip_code == args["zip_code"],
        )
    ).scalar_one_or_none()

    if member is None:
        # Deliberately generic on failure — don't reveal whether the
        # member ID exists but DOB/ZIP were wrong vs. it not existing at all.
        audit.record(
            ctx.db,
            tenant_id=ctx.tenant_id,
            action="member.verification_failed",
            resource_type="call",
            resource_id=str(ctx.call_id) if ctx.call_id else None,
            metadata={"member_id_attempted": args["member_id"]},
        )
        return "Verification failed — the member ID, date of birth, and ZIP code didn't all match our records."

    ctx.verified_member_id = member.member_id
    if ctx.customer_id is not None and member.customer_id is None:
        ctx.db.execute(update(Member).where(Member.id == member.id).values(customer_id=ctx.customer_id))
    audit.record(
        ctx.db,
        tenant_id=ctx.tenant_id,
        action="member.verified",
        resource_type="call",
        resource_id=str(ctx.call_id) if ctx.call_id else None,
        metadata={"member_id": member.member_id},
    )
    return f"Identity verified for {member.first_name} {member.last_name}, plan {member.plan_name}."


def _get_verified_member(ctx: CallContext) -> Member | None:
    if ctx.verified_member_id is None:
        return None
    return ctx.db.execute(
        select(Member).where(Member.tenant_id == ctx.tenant_id, Member.member_id == ctx.verified_member_id)
    ).scalar_one_or_none()


def _check_claim_status(ctx: CallContext, args: dict) -> str:
    member = _get_verified_member(ctx)
    if member is None:
        return "[VERIFICATION REQUIRED] Identity has not been verified this call."

    query = select(Claim).where(Claim.tenant_id == ctx.tenant_id, Claim.member_id == member.id)
    claim_number = args.get("claim_number")
    if claim_number:
        query = query.where(Claim.claim_number == claim_number)
    query = query.order_by(Claim.service_date.desc()).limit(1)

    claim = ctx.db.execute(query).scalar_one_or_none()
    if claim is None:
        return "No claims found for this member."

    result = (
        f"Claim {claim.claim_number}, service date {claim.service_date}, provider {claim.provider_name}, "
        f"amount ${claim.amount:.2f}, status: {claim.status.value}."
    )
    if claim.status == ClaimStatus.REJECTED and claim.rejection_reason:
        result += f" Rejection reason: {claim.rejection_reason}."
    return result


def _get_benefits(ctx: CallContext, args: dict) -> str:
    member = _get_verified_member(ctx)
    if member is None:
        return "[VERIFICATION REQUIRED] Identity has not been verified this call."

    return (
        f"Plan: {member.plan_name} (group {member.group_number}). "
        f"Copays — primary care ${member.copay_primary_care:.2f}, specialist ${member.copay_specialist:.2f}, "
        f"ER ${member.copay_er:.2f}. Deductible ${member.deductible:.2f}, "
        f"met so far ${member.deductible_met:.2f}."
    )


def _search_formulary(ctx: CallContext, args: dict) -> str:
    drugs = (
        ctx.db.execute(
            select(Drug).where(Drug.tenant_id == ctx.tenant_id, Drug.name.ilike(f"%{args['drug_name']}%"))
        )
        .scalars()
        .all()
    )
    if not drugs:
        return f"No formulary entry found for '{args['drug_name']}'."

    lines = []
    for d in drugs:
        pa = "prior authorization required" if d.prior_auth_required else "no prior authorization required"
        note = f" {d.notes}" if d.notes else ""
        lines.append(f"{d.name}: tier {d.tier}, copay ${d.copay:.2f}, {pa}.{note}")
    return "\n".join(lines)


def _find_pharmacy(ctx: CallContext, args: dict) -> str:
    pharmacies = (
        ctx.db.execute(
            select(Pharmacy).where(
                Pharmacy.tenant_id == ctx.tenant_id,
                Pharmacy.zip_code == args["zip_code"],
                Pharmacy.in_network == True,  # noqa: E712
            )
        )
        .scalars()
        .all()
    )
    if not pharmacies:
        return f"No in-network pharmacies found in ZIP {args['zip_code']}."
    return "\n".join(f"{p.name}, {p.address}, {p.phone}" for p in pharmacies)


def _create_ticket(ctx: CallContext, args: dict) -> str:
    ticket = Ticket(
        tenant_id=ctx.tenant_id,
        call_id=ctx.call_id,
        customer_id=ctx.customer_id,
        subject=args["subject"],
        description=args.get("description", ""),
    )
    ctx.db.add(ticket)
    ctx.db.flush()
    audit.record(
        ctx.db,
        tenant_id=ctx.tenant_id,
        action="ticket.created",
        resource_type="ticket",
        resource_id=str(ticket.id),
        metadata={"subject": args["subject"]},
    )
    return f"Ticket opened: {args['subject']}."


def _schedule_callback(ctx: CallContext, args: dict) -> str:
    name = "Customer"
    if ctx.customer_id is not None:
        profile = ctx.db.execute(
            select(CustomerProfile).where(CustomerProfile.id == ctx.customer_id)
        ).scalar_one_or_none()
        if profile and profile.name:
            name = profile.name

    appointment = Appointment(
        tenant_id=ctx.tenant_id,
        agent_id=ctx.agent_id,
        call_id=ctx.call_id,
        caller_name=name,
        caller_phone=args["phone"],
        preferred_time=args["preferred_time"],
        reason=f"Callback: {args.get('reason', '')}".strip(),
    )
    ctx.db.add(appointment)
    ctx.db.flush()
    audit.record(
        ctx.db,
        tenant_id=ctx.tenant_id,
        action="callback.scheduled",
        resource_type="appointment",
        resource_id=str(appointment.id),
        metadata={"preferred_time": args["preferred_time"]},
    )
    return f"Callback scheduled for {args['preferred_time']}."


def _send_email(ctx: CallContext, args: dict) -> str:
    # No email provider is configured in this environment (see
    # app.config.Settings) — this records the intent for a human/future
    # integration to act on rather than actually sending anything.
    audit.record(
        ctx.db,
        tenant_id=ctx.tenant_id,
        action="email.queued",
        resource_type="call",
        resource_id=str(ctx.call_id) if ctx.call_id else None,
        metadata={"to": args["to"], "subject": args["subject"]},
    )
    return f"Email queued for {args['to']}: {args['subject']}."


def _update_customer(ctx: CallContext, args: dict) -> str:
    if ctx.customer_id is None:
        return "No customer profile linked to this call."

    values = {}
    if args.get("name"):
        values["name"] = args["name"]
    if args.get("language"):
        values["language"] = args["language"]
    if not values:
        return "Nothing to update."

    ctx.db.execute(update(CustomerProfile).where(CustomerProfile.id == ctx.customer_id).values(**values))
    return "Customer profile updated."


def build_tool_handlers(ctx: CallContext) -> dict[str, Callable[[dict], str]]:
    return {
        "search_documents": lambda args: _search_documents(ctx, args),
        "schedule_appointment": lambda args: _schedule_appointment(ctx, args),
        "escalate_to_human": lambda args: _escalate_to_human(ctx, args),
        "verify_member": lambda args: _verify_member(ctx, args),
        "check_claim_status": lambda args: _check_claim_status(ctx, args),
        "get_benefits": lambda args: _get_benefits(ctx, args),
        "search_formulary": lambda args: _search_formulary(ctx, args),
        "find_pharmacy": lambda args: _find_pharmacy(ctx, args),
        "create_ticket": lambda args: _create_ticket(ctx, args),
        "schedule_callback": lambda args: _schedule_callback(ctx, args),
        "send_email": lambda args: _send_email(ctx, args),
        "update_customer": lambda args: _update_customer(ctx, args),
    }
