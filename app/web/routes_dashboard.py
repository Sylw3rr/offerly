"""The landing page: what needs doing, and how the search is going."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app import attention
from app.auth.dependencies import CurrentUser, require_user
from app.db import repositories as repo
from app.web.templates import templates

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, user: CurrentUser = Depends(require_user)):
    token = user.access_token
    profile = repo.get_profile(token)
    ghost_after_days = profile.get("ghost_after_days") or repo.DEFAULT_GHOST_AFTER_DAYS

    items = attention.collect(
        repo.open_applications(token),
        today=datetime.now(UTC).date(),
        ghost_after_days=ghost_after_days,
    )

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user,
            "profile": profile,
            "items": items,
            "stats": repo.funnel_stats(token),
            "events": repo.recent_events(token),
            "ghost_after_days": ghost_after_days,
        },
    )
