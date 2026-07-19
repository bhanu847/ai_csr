from collections.abc import Callable

from app.audit import logger as audit
from app.models.appointment import Appointment
from app.rag import service as rag_service
from app.tools.context import CallContext


def _search_documents(ctx: CallContext, args: dict) -> str:
    results = rag_service.search(ctx.db, ctx.agent_id, args["query"], k=4)
    if not results:
        return "No relevant information found in the knowledge base."
    lines = []
    for r in results:
        citation = r["filename"] + (f" (page {r['page']})" if r["page"] else "")
        lines.append(f"[{citation}]: {r['text']}")
    return "\n\n".join(lines)


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
