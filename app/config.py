"""Application settings, loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env against the project root rather than the working directory, so
# the application picks up its configuration however it was started.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

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
    gemini_api_key: str = ""
    # Flash is the cheap, fast tier, and reading a list out of an email is not
    # work that a larger model does better.
    gemini_model: str = "gemini-2.0-flash"

    # Outbound mail. Empty means reminders are computed but never sent, which
    # is the correct behaviour everywhere except production.
    resend_api_key: str = ""
    mail_from: str = ""

    @property
    def mail_enabled(self) -> bool:
        return bool(self.resend_api_key and self.mail_from)

    @property
    def ai_enabled(self) -> bool:
        return bool(self.anthropic_api_key or self.gemini_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
