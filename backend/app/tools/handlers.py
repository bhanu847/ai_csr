from collections.abc import Callable

from sqlalchemy import update

from app import confidence_service
from app.audit import logger as audit
from app.models.appointment import Appointment
from app.models.call import Call, ResolutionStatus
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


def build_tool_handlers(ctx: CallContext) -> dict[str, Callable[[dict], str]]:
    return {
        "search_documents": lambda args: _search_documents(ctx, args),
        "schedule_appointment": lambda args: _schedule_appointment(ctx, args),
        "escalate_to_human": lambda args: _escalate_to_human(ctx, args),
    }
