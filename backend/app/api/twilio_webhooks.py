import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import select
from twilio.request_validator import RequestValidator

from app.audit import logger as audit
from app.config import settings
from app.conversation.summary import generate_and_store_summary
from app.db.session import platform_session, tenant_session
from app.models.agent import Agent
from app.models.call import Call, CallStatus, ResolutionStatus
from app.models.tenant import Tenant
from app.telephony.twiml import build_voice_stream_twiml
from twilio.twiml.voice_response import Say, VoiceResponse

logger = logging.getLogger("telephony")

router = APIRouter(prefix="/api/twilio", tags=["twilio"])


def _validate_signature(request: Request, form: dict) -> None:
    if not settings.twilio_auth_token:
        return
    validator = RequestValidator(settings.twilio_auth_token)
    expected_url = f"{settings.public_server_url}{request.url.path}"
    signature = request.headers.get("X-Twilio-Signature", "")
    if not validator.validate(expected_url, form, signature):
        logger.warning("Rejected Twilio webhook with invalid signature")
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")


@router.post("/incoming")
async def incoming_call(request: Request) -> Response:
    if not settings.public_server_url:
        raise HTTPException(status_code=503, detail="PUBLIC_SERVER_URL is not configured")

    form = dict(await request.form())
    _validate_signature(request, form)

    to_number = form.get("To", "")
    call_sid = form.get("CallSid", "")
    from_number = form.get("From", "")

    with platform_session() as db:
        tenant = db.execute(select(Tenant).where(Tenant.twilio_phone_number == to_number)).scalar_one_or_none()

    if tenant is None:
        logger.warning("Incoming call to unregistered number %s (CallSid=%s)", to_number, call_sid)
        raise HTTPException(status_code=404, detail="No tenant registered for this number")

    with tenant_session(tenant.id) as db:
        agent = db.execute(
            select(Agent).where(Agent.tenant_id == tenant.id, Agent.is_default == True)  # noqa: E712
        ).scalar_one_or_none()
        if agent is None:
            agent = db.execute(select(Agent).where(Agent.tenant_id == tenant.id)).scalars().first()

        call = Call(
            tenant_id=tenant.id,
            agent_id=agent.id if agent else None,
            twilio_call_sid=call_sid,
            from_number=from_number,
            to_number=to_number,
            status=CallStatus.IN_PROGRESS,
        )
        db.add(call)
        db.flush()
        audit.record(
            db,
            tenant_id=tenant.id,
            action="call.received",
            resource_type="call",
            resource_id=call_sid,
            metadata={"from": from_number, "to": to_number},
        )
        call_id = call.id
        agent_id = agent.id if agent else None

    if agent_id is None:
        logger.warning("No agent configured for tenant %s (CallSid=%s)", tenant.id, call_sid)
        response = VoiceResponse()
        response.append(Say("This business hasn't set up an A.I. employee yet. Goodbye."))
        response.hangup()
        return Response(content=str(response), media_type="application/xml")

    twiml = build_voice_stream_twiml(settings.public_server_url, tenant.id, agent_id, call_id)
    return Response(content=twiml, media_type="application/xml")


@router.post("/status")
async def call_status(request: Request) -> Response:
    form = dict(await request.form())
    _validate_signature(request, form)

    call_sid = form.get("CallSid", "")
    call_status_value = form.get("CallStatus", "")
    to_number = form.get("To", "")

    with platform_session() as db:
        tenant = db.execute(select(Tenant).where(Tenant.twilio_phone_number == to_number)).scalar_one_or_none()

    if tenant is None:
        return Response(status_code=204)

    with tenant_session(tenant.id) as db:
        call = db.execute(select(Call).where(Call.twilio_call_sid == call_sid)).scalar_one_or_none()
        if call is not None and call_status_value in ("completed", "failed", "busy", "no-answer", "canceled"):
            call.status = CallStatus.COMPLETED if call_status_value == "completed" else CallStatus.FAILED
            call.ended_at = datetime.now(timezone.utc)
            if call.resolution_status is None:
                call.resolution_status = (
                    ResolutionStatus.RESOLVED if call_status_value == "completed" else ResolutionStatus.ABANDONED
                )
            audit.record(
                db,
                tenant_id=tenant.id,
                action="call.ended",
                resource_type="call",
                resource_id=call_sid,
                metadata={"twilio_status": call_status_value},
            )
            if call_status_value == "completed" and call.summary is None:
                generate_and_store_summary(db, call.id)

    return Response(status_code=204)
