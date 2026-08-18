from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Runtime DB role — must NOT be a superuser/BYPASSRLS role, or
    # tenant-isolation Row-Level Security policies are silently skipped.
    database_url: str

    # Superuser/owner connection used only for running migrations
    # (creating roles, granting privileges, defining RLS policies).
    migrations_database_url: str

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 60 * 12

    # Local/self-hosted LLM served through an OpenAI-compatible API — Ollama
    # by default (ollama pull <llm_model>). Any OpenAI-compatible server
    # (vLLM, LocalAI, llama.cpp server, ...) works by pointing the base URL
    # at it; api_key is unchecked by Ollama but the SDK requires a value.
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "ollama"
    llm_model: str = "qwen3:8b"

    # Local embedding model, also served by Ollama (ollama pull <model>).
    # embedding_dim MUST match the model's native output size — it's baked
    # into the pgvector column, so changing models requires a migration.
    embedding_model: str = "nomic-embed-text"
    embedding_dim: int = 768

    # Local speech-to-text (faster-whisper, runs in-process — no server).
    stt_language: str = "en"
    whisper_model_size: str = "base"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"

    # Local text-to-speech (Piper, runs in-process — no server). Voice
    # models are downloaded once with `python -m piper.download_voices`
    # into piper_voices_dir; agents.voice stores a Piper voice name
    # (e.g. "en_US-amy-medium") matching a .onnx file in that directory.
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
