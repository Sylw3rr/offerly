"""Reusable answers for recruitment forms.

Every external form asks the same handful of questions — notice period, expected
rate, driving licence, GDPR clause. Keeping the wording in one place means it is
answered once and pasted afterwards, rather than re-improvised at midnight.
"""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth.dependencies import CurrentUser, require_user
from app.db import repositories as repo
from app.web.templates import templates

router = APIRouter(tags=["answers"])

# Shown on an empty list. Suggestions only — nothing is created automatically.
SUGGESTED_LABELS = [
    "Notice period",
    "Expected salary",
    "Earliest start date",
    "Willing to relocate",
    "Driving licence",
    "English level",
    "GDPR clause",
]


def _render(request: Request, user: CurrentUser, error: str | None = None):
    return templates.TemplateResponse(
        request,
        "answers.html",
        {
            "user": user,
            "answers": repo.list_profile_answers(user.access_token),
            "suggestions": SUGGESTED_LABELS,
            "error": error,
        },
    )


@router.get("/answers", response_class=HTMLResponse)
def list_answers(request: Request, user: CurrentUser = Depends(require_user)):
    return _render(request, user)


@router.post("/answers")
def create_answer(
    request: Request,
    label: str = Form(...),
    value: str = Form(...),
    user: CurrentUser = Depends(require_user),
):
    if not label.strip() or not value.strip():
        return _render(request, user, "Both a label and an answer are needed.")
    try:
        repo.create_profile_answer(user.access_token, user.id, label, value)
    except Exception:
        # The only constraint that can realistically fail here is the unique
        # (user_id, label) pair; say so rather than showing a database error.
        return _render(request, user, f"You already have an answer labelled “{label.strip()}”.")
    return RedirectResponse("/answers", status_code=303)


@router.post("/answers/{answer_id}")
def update_answer(
    request: Request,
    answer_id: str,
    label: str = Form(...),
    value: str = Form(...),
    user: CurrentUser = Depends(require_user),
):
    if not label.strip() or not value.strip():
        return _render(request, user, "Both a label and an answer are needed.")
    try:
        repo.update_profile_answer(user.access_token, answer_id, label, value)
    except Exception:
        return _render(request, user, f"You already have an answer labelled “{label.strip()}”.")
    return RedirectResponse("/answers", status_code=303)


@router.post("/answers/{answer_id}/delete")
def delete_answer(answer_id: str, user: CurrentUser = Depends(require_user)):
    repo.delete_profile_answer(user.access_token, answer_id)
    return RedirectResponse("/answers", status_code=303)
