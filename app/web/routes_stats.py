"""Where the search actually goes.

Free: the whole search as one flow. Paid: the same flow cut by CV version and
by job board — see docs/PRICING.md. The question "how am I doing" is free; the
question "why, and what should I change" is the one worth paying for.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app import plans, sankey
from app.auth.dependencies import CurrentUser, require_user
from app.db import repositories as repo
from app.web.templates import render

router = APIRouter(tags=["stats"])


@router.get("/stats", response_class=HTMLResponse)
def stats(request: Request, user: CurrentUser = Depends(require_user)):
    token = user.access_token
    plan = plans.for_profile(repo.get_profile(token))

    return render(
        request,
        "stats.html",
        {
            "user": user,
            "chart": sankey.build(repo.all_status_events(token), repo.current_statuses(token)),
            "stats": repo.funnel_stats(token),
            "breakdowns_locked": not plan.allows(plans.STATS_BREAKDOWN),
        },
    )
