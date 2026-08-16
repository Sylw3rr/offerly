"""Offerly — job application tracker.

Entry point. Routers are mounted here as they are built.
"""

from fastapi import FastAPI

from app.config import get_settings

settings = get_settings()

app = FastAPI(
    title="Offerly",
    description="Job application tracker that reads your inbox so you don't have to.",
    version="0.0.1",
)


@app.get("/health", tags=["meta"])
def health() -> dict[str, object]:
    """Liveness probe. Reports which optional features are configured."""
    return {
        "status": "ok",
        "env": settings.app_env,
        "database_configured": bool(settings.supabase_url),
        "ingest_configured": bool(settings.ingest_domain),
        "ai_enabled": settings.ai_enabled,
    }
