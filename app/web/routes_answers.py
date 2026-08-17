"""Reusable answers for recruitment forms.

Every external form asks the same handful of questions — notice period, expected
rate, driving licence, GDPR clause. Keeping the wording in one place means it is
answered once and pasted afterwards, rather than re-improvised at midnight.
"""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth.dependencies import CurrentUser, require_user
from app.db import repositories as repo
from app.i18n import template_globals
from app.web.templates import render

router = APIRouter(tags=["answers"])

# Offered as chips under the label field. Suggestions only — pressing one fills
# the box, nothing is created until the form is saved.
SUGGESTED_KEYS = [
    "suggest.notice_period",
    "suggest.expected_salary",
    "suggest.start_date",
    "suggest.relocate",
    "suggest.driving_licence",
    "suggest.english",
    "suggest.gdpr",
]


def _render(
    request: Request,
    user: CurrentUser,
    error_key: str | None = None,
    status_code: int = 200,
    **error_args: str,
):
    t = template_globals(request)["t"]
    return render(
        request,
        "answers.html",
        {
            "user": user,
            "answers": repo.list_profile_answers(user.access_token),
            "suggestions": [t(key) for key in SUGGESTED_KEYS],
            "error": t(error_key, **error_args) if error_key else None,
        },
        status_code=status_code,
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
        return _render(request, user, "answers.error_empty")
    try:
        repo.create_profile_answer(user.access_token, user.id, label, value)
    except Exception:
        # The only constraint that can realistically fail here is the unique
        # (user_id, label) pair; say so rather than showing a database error.
        return _render(request, user, "answers.error_duplicate", label=label.strip())
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
        return _render(request, user, "answers.error_empty")
    try:
        repo.update_profile_answer(user.access_token, answer_id, label, value)
    except Exception:
        return _render(request, user, "answers.error_duplicate", label=label.strip())
    return RedirectResponse("/answers", status_code=303)


@router.post("/answers/{answer_id}/delete")
def delete_answer(answer_id: str, user: CurrentUser = Depends(require_user)):
    repo.delete_profile_answer(user.access_token, answer_id)
    return RedirectResponse("/answers", status_code=303)
