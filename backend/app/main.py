import logging

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from app.api.agents import router as agents_router
from app.api.appointments import router as appointments_router
from app.api.auth import router as auth_router
from app.api.calls import router as calls_router
from app.api.dashboard import router as dashboard_router
from app.api.knowledge import router as knowledge_router
from app.api.twilio_webhooks import router as twilio_router
from app.config import settings
from app.telephony.media_stream_handler import handle_media_stream

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="AI Workforce Platform")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(agents_router)
app.include_router(calls_router)
app.include_router(appointments_router)
app.include_router(knowledge_router)
app.include_router(dashboard_router)
app.include_router(twilio_router)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


@app.websocket("/media-stream")
async def ws_media_stream(websocket: WebSocket) -> None:
    await handle_media_stream(websocket)
