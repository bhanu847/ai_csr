import asyncio
import base64
import json
import logging
import uuid

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.conversation.agent import run_turn
from app.conversation.orchestrator import ConversationSession
from app.db.session import tenant_session
from app.models.agent import Agent
from app.speech.stt import transcribe_pcm16
from app.speech.tts import synthesize_mulaw8k
from app.telephony.audio_codec import mulaw8k_to_pcm16_16k_bytes
from app.telephony.vad import UtteranceBuffer
from app.tools.context import CallContext

logger = logging.getLogger("telephony")


async def _send_audio(websocket: WebSocket, stream_sid: str, mulaw_audio: bytes) -> None:
    payload = base64.b64encode(mulaw_audio).decode("ascii")
    await websocket.send_text(
        json.dumps({"event": "media", "streamSid": stream_sid, "media": {"payload": payload}})
    )


def _load_agent(tenant_id: uuid.UUID, agent_id: uuid.UUID) -> Agent:
    with tenant_session(tenant_id) as db:
        agent = db.execute(select(Agent).where(Agent.id == agent_id)).scalar_one()
        db.expunge(agent)
        return agent


def _run_turn_and_persist(
    tenant_id: uuid.UUID, agent_id: uuid.UUID, call_id: uuid.UUID, session: ConversationSession
) -> str:
    with tenant_session(tenant_id) as db:
        ctx = CallContext(db=db, tenant_id=tenant_id, agent_id=agent_id, call_id=call_id)
        return run_turn(session, ctx)


async def handle_media_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    buffer = UtteranceBuffer()
    stream_sid: str | None = None
    tenant_id: uuid.UUID | None = None
    agent_id: uuid.UUID | None = None
    call_id: uuid.UUID | None = None
    session: ConversationSession | None = None
    agent: Agent | None = None

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

                agent = await asyncio.to_thread(_load_agent, tenant_id, agent_id)
                session = ConversationSession(agent_name=agent.name, persona=agent.persona)
                greeting = f"Hello, this is {agent.name}. How can I help you today?"
                session.add_assistant_message(greeting)
                greeting_audio = await asyncio.to_thread(synthesize_mulaw8k, greeting, agent.voice)
                await _send_audio(websocket, stream_sid, greeting_audio)

            elif event == "media" and stream_sid and session is not None and agent is not None:
                mulaw_chunk = base64.b64decode(message["media"]["payload"])
                pcm16_16k = mulaw8k_to_pcm16_16k_bytes(mulaw_chunk)
                utterance = buffer.add_frame(pcm16_16k)
                if utterance is not None:
                    transcript = await asyncio.to_thread(transcribe_pcm16, utterance)
                    if transcript.strip():
                        session.add_user_message(transcript)
                        reply = await asyncio.to_thread(
                            _run_turn_and_persist, tenant_id, agent_id, call_id, session
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
