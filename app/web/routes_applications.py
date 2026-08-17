"""The application registry."""

from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth.dependencies import CurrentUser, require_user
from app.db import repositories as repo
from app.i18n import template_globals
from app.web.templates import render

router = APIRouter(tags=["applications"])

APPLICATION_STATUSES = [
    ("draft", "Draft"),
    ("blocked", "Blocked — needs manual step"),
    ("submitted", "Submitted"),
    ("acknowledged", "Acknowledged"),
    ("replied", "Replied"),
    ("interview", "Interview"),
    ("offer", "Offer"),
    ("rejected", "Rejected"),
    ("ghosted", "No answer"),
    ("withdrawn", "Withdrawn"),
]

SOURCES = [
    ("pracuj_pl", "pracuj.pl"),
    ("linkedin", "LinkedIn"),
    ("olx", "OLX"),
    ("justjoin", "justjoin.it"),
    ("rocketjobs", "rocketjobs.pl"),
    ("referral", "Referral"),
    ("direct", "Direct"),
    ("other", "Other"),
]

MODES = [("", "—"), ("onsite", "On-site"), ("hybrid", "Hybrid"), ("remote", "Remote")]
LEVELS = [
    ("", "—"),
    ("intern", "Intern"),
    ("junior", "Junior"),
    ("mid", "Mid"),
    ("senior", "Senior"),
    ("lead", "Lead"),
]
SALARY_KINDS = [("", "—"), ("gross", "Gross"), ("net", "Net")]
SALARY_PERIODS = [("", "—"), ("hour", "per hour"), ("month", "per month")]
CONTRACTS = [
    ("", "—"),
    ("employment", "Employment"),
    ("b2b", "B2B"),
    ("mandate", "Mandate"),
    ("internship", "Internship"),
    ("other", "Other"),
]
CURRENCIES = [("PLN", "PLN"), ("EUR", "EUR"), ("USD", "USD"), ("GBP", "GBP")]

FORM_CHOICES = {
    "statuses": APPLICATION_STATUSES,
    "sources": SOURCES,
    "modes": MODES,
    "levels": LEVELS,
    "salary_kinds": SALARY_KINDS,
    "salary_periods": SALARY_PERIODS,
    "contracts": CONTRACTS,
    "currencies": CURRENCIES,
}


def _amount(text: str) -> float | None:
    """Read a money field typed by hand: blank, comma decimals, stray spaces."""
    cleaned = text.replace(" ", "").replace(" ", "").replace(",", ".")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _plain(value: Any) -> str:
    """Put an amount back in a text field the way it was likely typed.

    Postgres returns 8000.00; showing that in the edit form invites the user to
    wonder whether the pennies mean something.
    """
    if value in (None, ""):
        return ""
    number = float(value)
    return str(int(number)) if number.is_integer() else str(number)


def _timestamp(day: str) -> str | None:
    """Turn a date from a date input into a timestamp.

    Midday rather than midnight: the column is timestamptz, and a date pinned
    to midnight UTC lands on the previous day for anyone west of Greenwich.
    """
    day = day.strip()
    return f"{day}T12:00:00+00:00" if day else None


def application_fields(
    company_name: str = Form(...),
    title: str = Form(...),
    source: str = Form("other"),
    url: str = Form(""),
    location: str = Form(""),
    mode: str = Form(""),
    level: str = Form(""),
    expires_at: str = Form(""),
    salary_min: str = Form(""),
    salary_max: str = Form(""),
    salary_currency: str = Form("PLN"),
    salary_kind: str = Form(""),
    salary_period: str = Form(""),
    contract: str = Form(""),
    cv_document_id: str = Form(""),
    declared_salary: str = Form(""),
    declared_salary_kind: str = Form(""),
    declared_salary_period: str = Form(""),
    declared_contract: str = Form(""),
    submitted_on: str = Form(""),
    blocked_reason: str = Form(""),
    notes: str = Form(""),
) -> dict[str, Any]:
    """Everything the add and edit forms have in common, read once.

    Declared as a dependency so both routes accept the same fields and clean
    them the same way — the two drifting apart is how an edit form starts
    quietly dropping what the add form saved.
    """
    low, high = _amount(salary_min), _amount(salary_max)
    # The database rejects an inverted range; a swapped pair is a typo, not a
    # reason to lose the entry.
    if low is not None and high is not None and low > high:
        low, high = high, low

    return {
        "company_name": company_name,
        "title": title,
        "source": source,
        "url": url,
        "location": location,
        "mode": mode,
        "level": level,
        "expires_at": expires_at,
        "salary_min": low,
        "salary_max": high,
        "salary_currency": salary_currency,
        "salary_kind": salary_kind,
        "salary_period": salary_period,
        "contract": contract,
        "cv_document_id": cv_document_id,
        "declared_salary": _amount(declared_salary),
        "declared_salary_kind": declared_salary_kind,
        "declared_salary_period": declared_salary_period,
        "declared_contract": declared_contract,
        "submitted_at": _timestamp(submitted_on),
        "blocked_reason": blocked_reason,
        "notes": notes,
    }


def _matches(application: dict[str, Any], needle: str) -> bool:
    """Search over what someone would actually remember: who, what, where."""
    offer = application.get("offers") or {}
    company = (offer.get("companies") or {}).get("name") or ""
    haystack = " ".join(
        [
            company,
            offer.get("title") or "",
            offer.get("location") or "",
            application.get("notes") or "",
        ]
    )
    return needle in haystack.lower()


def _moved_label(t, moved_at: str | None, today: date) -> str:
    """How long ago this application last changed status, in words."""
    if not moved_at:
        return t("moved.never")
    try:
        moved = date.fromisoformat(moved_at[:10])
    except ValueError:
        return t("moved.never")

    days = (today - moved).days
    if days <= 0:
        return t("moved.today")
    if days == 1:
        return t("moved.yesterday")
    return t("moved.days", days=days)


@router.get("/applications", response_class=HTMLResponse)
def list_applications(
    request: Request,
    status: str | None = None,
    q: str = "",
    user: CurrentUser = Depends(require_user),
):
    token = user.access_token
    applications = repo.list_applications(token, status)

    needle = q.strip().lower()
    if needle:
        # Filtered here rather than in the query: the embedded company name is
        # awkward to search through PostgREST, and one person's registry is
        # tens of rows, not thousands.
        applications = [a for a in applications if _matches(a, needle)]

    t = template_globals(request)["t"]
    moves = repo.last_moves(token)
    today = datetime.now(UTC).date()
    for application in applications:
        application["moved_label"] = _moved_label(t, moves.get(application["id"]), today)

    return render(
        request,
        "applications_list.html",
        {
            "user": user,
            "applications": applications,
            "stats": repo.funnel_stats(token),
            "active_status": status,
            "q": q.strip(),
            "statuses": APPLICATION_STATUSES,
        },
    )


@router.get("/applications/new", response_class=HTMLResponse)
def new_application_form(request: Request, user: CurrentUser = Depends(require_user)):
    t = template_globals(request)["t"]
    return render(
        request,
        "application_form.html",
        {
            "user": user,
            "documents": repo.list_documents(user.access_token),
            "heading": t("form.heading_new"),
            "intro": t("form.intro_new"),
            "action": "/applications/new",
            "submit_label": t("action.save"),
            "cancel_url": "/applications",
            "form": {},
            "editing": False,
            **FORM_CHOICES,
        },
    )


@router.post("/applications/new")
def create_application(
    status: str = Form("submitted"),
    fields: dict[str, Any] = Depends(application_fields),
    user: CurrentUser = Depends(require_user),
):
    application_id = repo.create_application(user.access_token, user.id, status=status, **fields)
    return RedirectResponse(f"/applications/{application_id}", status_code=303)


@router.get("/applications/{application_id}/edit", response_class=HTMLResponse)
def edit_application_form(
    request: Request,
    application_id: str,
    user: CurrentUser = Depends(require_user),
):
    application = repo.get_application(user.access_token, application_id)
    if application is None:
        return RedirectResponse("/applications", status_code=303)

    offer = application.get("offers") or {}
    company = offer.get("companies") or {}
    t = template_globals(request)["t"]
    return render(
        request,
        "application_form.html",
        {
            "user": user,
            "documents": repo.list_documents(user.access_token),
            "heading": t("form.heading_edit"),
            "intro": t("form.intro_edit"),
            "action": f"/applications/{application_id}/edit",
            "submit_label": t("action.save_change"),
            "cancel_url": f"/applications/{application_id}",
            "editing": True,
            "form": {
                "company_name": company.get("name", ""),
                "title": offer.get("title", ""),
                "source": offer.get("source", ""),
                "url": offer.get("url") or "",
                "location": offer.get("location") or "",
                "mode": offer.get("mode") or "",
                "level": offer.get("level") or "",
                "expires_at": offer.get("expires_at") or "",
                "salary_min": _plain(offer.get("salary_min")),
                "salary_max": _plain(offer.get("salary_max")),
                "salary_currency": offer.get("salary_currency") or "PLN",
                "salary_kind": offer.get("salary_kind") or "",
                "salary_period": offer.get("salary_period") or "",
                "contract": offer.get("contract") or "",
                "cv_document_id": application.get("cv_document_id") or "",
                "declared_salary": _plain(application.get("declared_salary")),
                "declared_salary_kind": application.get("declared_salary_kind") or "",
                "declared_salary_period": application.get("declared_salary_period") or "",
                "declared_contract": application.get("declared_contract") or "",
                "submitted_on": (application.get("submitted_at") or "")[:10],
                "blocked_reason": application.get("blocked_reason") or "",
                "notes": application.get("notes") or "",
            },
            **FORM_CHOICES,
        },
    )


@router.post("/applications/{application_id}/edit")
def edit_application(
    application_id: str,
    fields: dict[str, Any] = Depends(application_fields),
    user: CurrentUser = Depends(require_user),
):
    try:
        repo.update_application(user.access_token, user.id, application_id, **fields)
    except ValueError:
        return RedirectResponse("/applications", status_code=303)
    return RedirectResponse(f"/applications/{application_id}", status_code=303)


@router.post("/applications/{application_id}/delete")
def delete_application(application_id: str, user: CurrentUser = Depends(require_user)):
    repo.delete_application(user.access_token, application_id)
    return RedirectResponse("/applications", status_code=303)


@router.get("/applications/{application_id}", response_class=HTMLResponse)
def application_detail(
    request: Request,
    application_id: str,
    user: CurrentUser = Depends(require_user),
):
    application = repo.get_application(user.access_token, application_id)
    if application is None:
        return RedirectResponse("/applications", status_code=303)
    return render(
        request,
        "application_detail.html",
        {
            "user": user,
            "application": application,
            "history": repo.status_history(user.access_token, application_id),
            "statuses": APPLICATION_STATUSES,
        },
    )


@router.post("/applications/{application_id}/status")
def update_status(
    application_id: str,
    status: str = Form(...),
    note: str = Form(""),
    user: CurrentUser = Depends(require_user),
):
    repo.change_status(user.access_token, user.id, application_id, status, note or None)
    return RedirectResponse(f"/applications/{application_id}", status_code=303)


@router.post("/documents/new")
def create_document(
    label: str = Form(...),
    user: CurrentUser = Depends(require_user),
):
    repo.create_document(user.access_token, user.id, label)
    return RedirectResponse("/applications/new", status_code=303)
