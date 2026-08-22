"""Getting a new account to the point where mail arrives.

Everything else in the application is built for somebody who already knows
what Offerly is. This page is for the ten minutes before that: a person has a
code, has signed up, and is looking at an empty dashboard wondering what they
were promised.

The one thing they have to do is set up forwarding, and it is the one thing
nothing in the product could do for them — we deliberately hold no password to
their mailbox, so the filter has to be theirs.

Whether it worked is not asked, it is observed: if any message has ever
arrived, the account is set up. A checkbox here would only record what
somebody believed at the time.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.auth.dependencies import CurrentUser, require_user
from app.config import get_settings
from app.db import repositories as repo
from app.web.templates import render

router = APIRouter(tags=["web"])

# Boards whose alerts the ingest side recognises. Kept as domains rather than
# exact senders: a board changes `jobalert@` to `noreply@` without warning, and
# a filter that silently stops matching is worse than one that is slightly wide.
BOARDS = (
    "pracuj.pl",
    "linkedin.com",
    "justjoin.it",
    "olx.pl",
    "nofluffjobs.com",
    "rocketjobs.pl",
    "theprotocol.it",
    "praca.pl",
    "indeed.com",
)

# A net for employer replies, which arrive from company domains nobody can
# enumerate. Deliberately narrow: this is somebody's private mailbox, and a
# filter that forwards too much would break the promise the landing page makes.
REPLY_TERMS = ("rekrutacj", "aplikacj", "kandydat", "CV", "zgłoszeni")


@router.get("/start", response_class=HTMLResponse)
def start(request: Request, user: CurrentUser = Depends(require_user)):
    profile = repo.get_profile(user.access_token)
    settings = get_settings()
    token = profile.get("ingest_token")
    address = f"{token}@{settings.ingest_domain}" if token and settings.ingest_domain else None

    return render(
        request,
        "start.html",
        {
            "user": user,
            "address": address,
            # Not "did you finish?" but "has anything arrived?". The only
            # answer that means anything.
            "arrived": repo.inbound_count(user.access_token),
            "board_filter": "from:(" + " OR ".join(BOARDS) + ")",
            "reply_filter": "{" + " ".join(REPLY_TERMS) + "}",
        },
    )
