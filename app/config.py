"""Application settings, loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_secret: str = "change-me"
    app_base_url: str = "http://127.0.0.1:8000"

    supabase_url: str = ""
    supabase_anon_key: str = ""
    # Server-side only. Bypasses row level security — never send to a browser.
    supabase_service_key: str = ""

    ingest_domain: str = ""
    ingest_webhook_secret: str = ""

    # Empty means AI features stay switched off; the app runs fully without them.
    anthropic_api_key: str = ""

    @property
    def ai_enabled(self) -> bool:
        return bool(self.anthropic_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
