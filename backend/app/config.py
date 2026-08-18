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

    # Local/self-hosted LLM served through an OpenAI-compatible API — Ollama
    # by default (ollama pull <llm_model>). Any OpenAI-compatible server
    # (vLLM, LocalAI, llama.cpp server, ...) works by pointing the base URL
    # at it; api_key is unchecked by Ollama but the SDK requires a value.
    # Only embeddings still go through this client now (see rag/embeddings.py)
    # — chat completions moved to the hosted Claude API for latency/scale.
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "ollama"
    llm_model: str = "qwen3:8b"

    # Hosted LLM for conversational replies + structured JSON extraction
    # (call summaries, QA scoring, intent routing) — see app/llm/client.py.
    # Azure OpenAI speaks the native OpenAI chat-completions API, so this
    # is a straight endpoint swap, not a format adapter. Real per-token
    # cost, unlike the self-hosted embedding/TTS pieces.
    # azure_openai_deployment is the *deployment name* you chose in Azure
    # AI Studio, not a model name like "gpt-4o" -- Azure routes by
    # deployment, and deployment names are per-resource.
    azure_openai_api_key: str = ""
    azure_openai_endpoint: str = ""
    azure_openai_deployment: str = ""
    azure_openai_api_version: str = "2024-10-21"

    # Local embedding model, also served by Ollama (ollama pull <model>).
    # embedding_dim MUST match the model's native output size — it's baked
    # into the pgvector column, so changing models requires a migration.
    embedding_model: str = "nomic-embed-text"
    embedding_dim: int = 768

    # Speech-to-text and text-to-speech: Azure AI Speech, hosted. One key
    # + region covers both (app/speech/stt.py, app/speech/tts.py). Real
    # per-minute cost. whisper_*/piper_* settings below are unused now but
    # left in place in case of a rollback to self-hosted speech.
    stt_language: str = "en-US"
    whisper_model_size: str = "base"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    azure_speech_key: str = ""
    azure_speech_region: str = ""

    # Azure neural voice used when an agent's `voice` field doesn't match a
    # known name (see app/speech/tts.py's Piper-name compatibility map —
    # existing agents still have Piper voice names stored from before this
    # switch). Full neural voice list: https://speech.microsoft.com/portal/voicegallery
    azure_default_voice: str = "en-US-JennyNeural"

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
