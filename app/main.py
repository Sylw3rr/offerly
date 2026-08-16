"""Offerly — job application tracker.

Entry point. Routers are mounted here as they are built.
"""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth.dependencies import _RedirectToLogin, get_current_user, set_session_cookies
from app.config import get_settings
from app.web.routes_answers import router as answers_router
from app.web.routes_applications import router as applications_router
from app.web.routes_auth import router as auth_router
from app.web.routes_dashboard import router as dashboard_router

settings = get_settings()

app = FastAPI(
    title="Offerly",
    description="Job application tracker that reads your inbox so you don't have to.",
    version="0.1.0",
)

app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(applications_router)
app.include_router(answers_router)


@app.middleware("http")
async def persist_refreshed_session(request: Request, call_next):
    """Write rotated tokens back to the browser.

    `get_current_user` refreshes an expired access token and leaves the new
    pair on request.state; without this the refresh would happen on every
    request instead of once.
    """
    response = await call_next(request)
    session = getattr(request.state, "refreshed_session", None)
    if session is not None:
        set_session_cookies(response, session)
    return response


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
    return RedirectResponse("/dashboard", status_code=303)
