import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.agents import router as agents_router
from app.api.appointments import router as appointments_router
from app.api.auth import router as auth_router
from app.api.calls import router as calls_router
from app.api.customers import router as customers_router
from app.api.dashboard import router as dashboard_router
from app.api.data_import import router as data_import_router
from app.api.knowledge import router as knowledge_router
from app.api.supervisor import router as supervisor_router
from app.api.training import router as training_router
from app.api.twilio_webhooks import router as twilio_router
from app.api.workflows import router as workflows_router
from app.config import settings
from app.rate_limit import limiter
from app.telephony.media_stream_handler import handle_media_stream

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # See settings.blocking_thread_pool_size -- removes Python's default
    # ~12-thread ceiling on concurrent blocking work (DB/STT/LLM/TTS).
    asyncio.get_event_loop().set_default_executor(
        ThreadPoolExecutor(max_workers=settings.blocking_thread_pool_size)
    )
    yield


app = FastAPI(title="AI Workforce Platform", lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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
app.include_router(customers_router)
app.include_router(data_import_router)
app.include_router(training_router)
app.include_router(workflows_router)
app.include_router(supervisor_router)
app.include_router(twilio_router)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


@app.websocket("/media-stream")
async def ws_media_stream(websocket: WebSocket) -> None:
    await handle_media_stream(websocket)
