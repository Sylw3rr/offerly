"""Offerly — job application tracker.

Entry point. Routers are mounted here as they are built.
"""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth.dependencies import _RedirectToLogin, get_current_user
from app.config import get_settings
from app.web.routes_auth import router as auth_router
from app.web.templates import templates

settings = get_settings()

app = FastAPI(
    title="Offerly",
    description="Job application tracker that reads your inbox so you don't have to.",
    version="0.1.0",
)

app.include_router(auth_router)


@app.exception_handler(_RedirectToLogin)
def _handle_redirect_to_login(request: Request, exc: _RedirectToLogin):
    return RedirectResponse("/login", status_code=303)


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


@app.get("/", response_class=HTMLResponse, tags=["web"])
def home(request: Request):
    user = get_current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request, "dashboard.html", {"user": user})
