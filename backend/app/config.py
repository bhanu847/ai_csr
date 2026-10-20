from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator

# The exact placeholder shipped in .env.example — if this is still the live
# value, every JWT the app issues is forgeable by anyone who's read the
# public repo. Rejected at startup rather than left as a silent footgun.
_PLACEHOLDER_JWT_SECRETS = {"change-me-to-a-long-random-value", "changeme", "secret"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Runtime DB role — must NOT be a superuser/BYPASSRLS role, or
    # tenant-isolation Row-Level Security policies are silently skipped.
    database_url: str

    # Superuser/owner connection used only for running migrations
    # (creating roles, granting privileges, defining RLS policies).
    migrations_database_url: str

    # See app.db.session -- SQLAlchemy's untouched defaults (5 + 10) cap
    # this process at 15 concurrent DB connections. Must stay under
    # Postgres's own max_connections (default 100) with headroom for
    # migrations/other clients, and needs re-checking if this process is
    # ever scaled to multiple workers (each gets its own pool).
    db_pool_size: int = 20
    db_pool_max_overflow: int = 20

    # Every blocking STT/LLM/TTS/DB call in a call turn runs via
    # asyncio.to_thread, which by default shares Python's tiny
    # min(32, cpu_count()+4) executor across ALL of them combined (12
    # threads total on an 8-core box). Raised well past that so concurrent
    # calls don't queue behind each other for a free thread purely due to
    # this default -- it does NOT mean this many calls can actually run
    # at once; the real ceiling is STT/LLM compute capacity, not thread
    # count, and needs load testing against whatever backs a deployment.
    blocking_thread_pool_size: int = 200

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 60 * 12

    @field_validator("jwt_secret")
    @classmethod
    def _validate_jwt_secret(cls, value: str) -> str:
        if value.strip().lower() in _PLACEHOLDER_JWT_SECRETS:
            raise ValueError(
                "JWT_SECRET is still the placeholder value from .env.example — "
                "every login token would be forgeable. Set a real random value."
            )
        if len(value) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters — it's too short to resist guessing.")
        return value

    # The one self-hosted LLM, served through an OpenAI-compatible API —
    # Ollama by default (ollama pull <llm_model>). Any OpenAI-compatible
    # server (vLLM, LocalAI, llama.cpp server, ...) works by pointing the
    # base URL at it; api_key is unchecked by Ollama but the SDK requires a
    # value. Used for embeddings (app/rag/embeddings.py) AND conversational
    # replies + structured JSON extraction (app/llm/client.py) — no hosted
    # LLM involved anywhere. Ollama's OpenAI-compat endpoint drops
    # `keep_alive`, so set OLLAMA_KEEP_ALIVE on the Ollama process itself
    # (not here) to stop the model unloading between calls on a live line.
    #
    # qwen3:1.7b is the default because, measured on this project's own
    # CPU-only dev hardware (no GPU), qwen3:8b took ~140-150s per call --
    # unusable for a live phone turn. qwen3:1.7b is ~15-19s with thinking
    # disabled below: still slow for live conversation, but workable for
    # development, and far better than the 8b model on CPU. A bigger model
    # (qwen3:8b or larger) is a straight quality/tool-calling-reliability
    # upgrade IF you have GPU hardware to run it at acceptable latency --
    # that tradeoff hasn't been measured here, only the CPU numbers above.
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "ollama"
    llm_model: str = "qwen3:1.7b"

    # Qwen3 "thinks" (emits chain-of-thought) before answering by default,
    # which on CPU-only inference adds real seconds of otherwise-invisible
    # latency per call. Disabling it is a clear latency win; it's a
    # genuine, UNVERIFIED tradeoff against tool-calling reliability on the
    # 5-round PBM tool loop (app/conversation/agent.py) -- reasoning models
    # sometimes use that chain-of-thought to pick the right tool. Flip to
    # False to test with thinking back on.
    llm_disable_thinking: bool = True

    # Local embedding model, also served by Ollama (ollama pull <model>).
    # embedding_dim MUST match the model's native output size — it's baked
    # into the pgvector column, so changing models requires a migration.
    embedding_model: str = "nomic-embed-text"
    embedding_dim: int = 768

    # Speech-to-text (faster-whisper, app/speech/stt.py) and text-to-speech
    # (piper-tts, app/speech/tts.py) — both self-hosted, no account/key
    # needed. stt_language stays in BCP-47 form ("en-US") for display/
    # consistency; stt.py derives the bare ISO 639-1 code faster-whisper
    # actually wants ("en").
    stt_language: str = "en-US"
    whisper_model_size: str = "base"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"

    # Piper voice model directory (.onnx + .onnx.json per voice) and the
    # voice used when an agent's `voice` field is empty.
    piper_voices_dir: str = "./voices"
    piper_default_voice: str = "en_US-amy-medium"

    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    public_server_url: str = ""

    # Barge-in tuning (tweakable per-deployment without a code change — call
    # audio quality varies a lot by carrier/handset). barge_in_ms is how much
    # *consecutive* caller speech during AI playback counts as a genuine
    # interruption. barge_in_rms_threshold is intentionally higher than the
    # normal turn-taking speech threshold (vad.SPEECH_RMS_THRESHOLD) because
    # on speakerphone calls the caller's handset can leak the AI's own voice
    # back into their mic as echo — a higher bar makes that leaked echo less
    # likely to falsely trigger a cutoff than genuine direct speech would.
    barge_in_ms: int = 200
    barge_in_rms_threshold: int = 750

    cors_origins: str = "http://localhost:4200,http://127.0.0.1:4200"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
