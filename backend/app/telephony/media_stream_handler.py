import asyncio
import base64
import json
import logging
import uuid

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy import select

from dataclasses import dataclass

from sqlalchemy import update

from app.audit import logger as audit
from app.conversation.agent import run_turn
from app.conversation.customer_memory import build_memory_context
from app.conversation.orchestrator import ConversationSession
from app.conversation.persistence import persist_message
from app.conversation.router import classify_department
from app.db.session import tenant_session
from app.models.agent import Agent
from app.models.call import Call
from app.models.conversation_message import MessageRole
from app.models.customer_profile import CustomerProfile
from app.speech.stt import transcribe_pcm16
from app.speech.tts import synthesize_mulaw8k
from app.telephony.audio_codec import mulaw8k_to_pcm16_16k_bytes
from app.telephony.vad import UtteranceBuffer
from app.tools.context import CallContext

logger = logging.getLogger("telephony")


@dataclass
class CallStartInfo:
    agent: Agent
    customer_id: uuid.UUID | None
    customer_name: str | None
    memory_context: str | None


async def _send_audio(websocket: WebSocket, stream_sid: str, mulaw_audio: bytes) -> None:
    payload = base64.b64encode(mulaw_audio).decode("ascii")
    await websocket.send_text(
        json.dumps({"event": "media", "streamSid": stream_sid, "media": {"payload": payload}})
    )


def _load_call_start_info(tenant_id: uuid.UUID, agent_id: uuid.UUID, call_id: uuid.UUID) -> CallStartInfo:
    with tenant_session(tenant_id) as db:
        agent = db.execute(select(Agent).where(Agent.id == agent_id)).scalar_one()
        call = db.execute(select(Call).where(Call.id == call_id)).scalar_one_or_none()

        customer_id: uuid.UUID | None = None
        customer_name: str | None = None
        memory_context: str | None = None
        if call is not None and call.customer_id is not None:
            profile = db.execute(
                select(CustomerProfile).where(CustomerProfile.id == call.customer_id)
            ).scalar_one_or_none()
            if profile is not None:
                customer_id = profile.id
                customer_name = profile.name
                memory_context = build_memory_context(db, profile)

        db.expunge(agent)
        return CallStartInfo(
            agent=agent, customer_id=customer_id, customer_name=customer_name, memory_context=memory_context
        )


def _persist_assistant_message(tenant_id: uuid.UUID, call_id: uuid.UUID, content: str) -> None:
    with tenant_session(tenant_id) as db:
        persist_message(db, tenant_id, call_id, MessageRole.ASSISTANT, content)


def _maybe_route(tenant_id: uuid.UUID, call_id: uuid.UUID, current_agent: Agent, transcript: str) -> Agent:
    """One-time routing decision on a call's first utterance. Only routes
    away from a "general" agent — if an admin has already assigned a
    specialist as the number's default, that's an explicit choice we don't
    second-guess. Returns current_agent unchanged on any non-match."""
    if (current_agent.department or "general").lower() != "general":
        return current_agent

    with tenant_session(tenant_id) as db:
        agents = db.execute(select(Agent).where(Agent.tenant_id == tenant_id)).scalars().all()
        departments = sorted({(a.department or "general").lower() for a in agents})
        if len(departments) <= 1:
            return current_agent  # no specialists configured for this tenant — nothing to route to

        chosen = classify_department(transcript, departments)
        if chosen == "general":
            return current_agent

        specialist = next(
            (a for a in agents if (a.department or "general").lower() == chosen and a.id != current_agent.id),
            None,
        )
        if specialist is None:
            return current_agent

        db.execute(update(Call).where(Call.id == call_id).values(agent_id=specialist.id))
        audit.record(
            db,
            tenant_id=tenant_id,
            action="call.routed",
            resource_type="call",
            resource_id=str(call_id),
            metadata={"department": chosen, "agent_id": str(specialist.id)},
        )
        db.expunge(specialist)
        return specialist


def _run_turn_and_persist(
    tenant_id: uuid.UUID,
    agent_id: uuid.UUID,
    call_id: uuid.UUID,
    customer_id: uuid.UUID | None,
    session: ConversationSession,
    transcript: str,
) -> str:
    with tenant_session(tenant_id) as db:
        persist_message(db, tenant_id, call_id, MessageRole.CUSTOMER, transcript)
        ctx = CallContext(
            db=db,
            tenant_id=tenant_id,
            agent_id=agent_id,
            call_id=call_id,
            customer_id=customer_id,
            department=session.department,
            verified_member_id=session.verified_member_id,
        )
        reply = run_turn(session, ctx)
        session.verified_member_id = ctx.verified_member_id
        return reply


async def handle_media_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    buffer = UtteranceBuffer()
    stream_sid: str | None = None
    tenant_id: uuid.UUID | None = None
    agent_id: uuid.UUID | None = None
    call_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    session: ConversationSession | None = None
    agent: Agent | None = None
    routed = False

    try:
        while True:
            raw = await websocket.receive_text()
            message = json.loads(raw)
            event = message.get("event")

            if event == "start":
                stream_sid = message["start"]["streamSid"]
                params = message["start"].get("customParameters", {})
                tenant_id = uuid.UUID(params["tenant_id"])
                agent_id = uuid.UUID(params["agent_id"])
                call_id = uuid.UUID(params["call_id"])
                logger.info("Call started: %s (tenant=%s agent=%s)", stream_sid, tenant_id, agent_id)

                start_info = await asyncio.to_thread(_load_call_start_info, tenant_id, agent_id, call_id)
                agent = start_info.agent
                customer_id = start_info.customer_id
                session = ConversationSession(
                    agent_name=agent.name, persona=agent.persona, memory_context=start_info.memory_context
                )
                session.department = (agent.department or "general").lower()
                # Name only, in the canned greeting — a known caller by
                # name is low-sensitivity and standard for CSR lines. Prior
                # medical/claims details stay gated behind the in-call
                # identity-confirmation rule in CUSTOMER_MEMORY_SECTION.
                greeting = (
                    f"Welcome back, {start_info.customer_name}! This is {agent.name}. How can I help you today?"
                    if start_info.customer_name
                    else f"Hello, this is {agent.name}. How can I help you today?"
                )
                session.add_assistant_message(greeting)
                await asyncio.to_thread(_persist_assistant_message, tenant_id, call_id, greeting)
                greeting_audio = await asyncio.to_thread(synthesize_mulaw8k, greeting, agent.voice)
                await _send_audio(websocket, stream_sid, greeting_audio)

            elif event == "media" and stream_sid and session is not None and agent is not None:
                mulaw_chunk = base64.b64decode(message["media"]["payload"])
                pcm16_16k = mulaw8k_to_pcm16_16k_bytes(mulaw_chunk)
                utterance = buffer.add_frame(pcm16_16k)
                if utterance is not None:
                    transcript = await asyncio.to_thread(transcribe_pcm16, utterance)
                    if transcript.strip():
                        if not routed:
                            routed = True
                            new_agent = await asyncio.to_thread(_maybe_route, tenant_id, call_id, agent, transcript)
                            if new_agent.id != agent.id:
                                logger.info(
                                    "Call %s routed to department=%s agent=%s",
                                    call_id, new_agent.department, new_agent.id,
                                )
                                agent = new_agent
                                agent_id = new_agent.id
                                session.switch_agent(agent.name, agent.persona)
                                session.department = (agent.department or "general").lower()

                        session.add_user_message(transcript)
                        reply = await asyncio.to_thread(
                            _run_turn_and_persist, tenant_id, agent_id, call_id, customer_id, session, transcript
                        )
                        audio = await asyncio.to_thread(synthesize_mulaw8k, reply, agent.voice)
                        await _send_audio(websocket, stream_sid, audio)

            elif event == "stop":
                logger.info("Call ended: %s", stream_sid)
                break

    except WebSocketDisconnect:
        logger.info("Twilio stream disconnected")
    except Exception:
        logger.exception("Error in media stream session")
