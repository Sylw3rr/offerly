"""What arrived by mail, and what to do about it.

Everything the webhook could not act on with certainty ends up here rather than
being guessed at. The confident cases have already moved their application and
appear as a record of that; the uncertain ones wait for a person, which is the
entire reason for having an inbox instead of an automation.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth.dependencies import CurrentUser, require_user
from app.db import repositories as repo
from app.ingest.reading import KIND_REPLY, Message, read
from app.web.templates import render

router = APIRouter(tags=["inbox"])


def _suggestion(row: dict) -> str | None:
    """What this message looks like it means, read again at display time.

    Read rather than stored, so a message that arrived before the rules
    improved is judged by the rules as they are now.
    """
    reading = read(
        Message(
            to_address="",
            from_address=row.get("from_address") or "",
            subject=row.get("subject") or "",
            body=row.get("body") or "",
        )
    )
    return reading.status if reading.kind == KIND_REPLY else None


@router.get("/inbox", response_class=HTMLResponse)
def inbox(request: Request, user: CurrentUser = Depends(require_user)):
    rows = repo.list_inbound(user.access_token)

    items = []
    for row in rows:
        application = row.get("applications") or {}
        offer = application.get("offers") or {}
        suggestion = _suggestion(row)
        items.append(
            {
                **row,
                "suggestion": suggestion,
                "company": (offer.get("companies") or {}).get("name"),
                "title": offer.get("title"),
                "current_status": application.get("status"),
                # Worth a person's decision: something to move, and nobody has
                # moved it yet.
                "actionable": bool(
                    suggestion
                    and row.get("application_id")
                    and not row.get("handled_at")
                    and suggestion != application.get("status")
                ),
            }
        )

    return render(
        request,
        "inbox.html",
        {
            "user": user,
            "items": items,
            "waiting": sum(1 for item in items if not item.get("handled_at")),
        },
    )


@router.post("/inbox/{inbound_id}/confirm")
def confirm(inbound_id: str, user: CurrentUser = Depends(require_user)):
    """Accept what the message appears to say and move the application.

    The suggestion is worked out again here rather than trusted from the form:
    a status arriving in a request body is a status anyone could have typed.
    """
    row = repo.get_inbound(user.access_token, inbound_id)
    if row is None or not row.get("application_id"):
        return RedirectResponse("/inbox", status_code=303)

    status = _suggestion(row)
    if status:
        repo.change_status(
            user.access_token,
            user.id,
            row["application_id"],
            status,
            (row.get("subject") or "")[:200] or None,
        )
    repo.mark_inbound_handled(user.access_token, inbound_id)
    return RedirectResponse("/inbox", status_code=303)


@router.post("/inbox/{inbound_id}/dismiss")
def dismiss(inbound_id: str, user: CurrentUser = Depends(require_user)):
    repo.mark_inbound_handled(user.access_token, inbound_id)
    return RedirectResponse("/inbox", status_code=303)
