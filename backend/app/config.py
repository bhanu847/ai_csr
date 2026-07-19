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

    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_deployment: str = ""
    azure_openai_embedding_deployment: str = ""
    azure_openai_api_version: str = "2024-08-01-preview"

    azure_speech_key: str = ""
    azure_speech_region: str = "centralindia"
    stt_language: str = "en-IN"

    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    public_server_url: str = ""

    cors_origins: str = "http://localhost:4200,http://127.0.0.1:4200"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
