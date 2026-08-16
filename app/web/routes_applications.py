"""The application registry."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth.dependencies import CurrentUser, require_user
from app.db import repositories as repo
from app.web.templates import templates

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

FORM_CHOICES = {
    "statuses": APPLICATION_STATUSES,
    "sources": SOURCES,
    "modes": MODES,
    "levels": LEVELS,
    "salary_kinds": SALARY_KINDS,
    "salary_periods": SALARY_PERIODS,
    "contracts": CONTRACTS,
}


@router.get("/applications", response_class=HTMLResponse)
def list_applications(
    request: Request,
    status: str | None = None,
    user: CurrentUser = Depends(require_user),
):
    applications = repo.list_applications(user.access_token, status)
    stats = repo.funnel_stats(user.access_token)
    return templates.TemplateResponse(
        request,
        "applications_list.html",
        {
            "user": user,
            "applications": applications,
            "stats": stats,
            "active_status": status,
            "statuses": APPLICATION_STATUSES,
        },
    )


@router.get("/applications/new", response_class=HTMLResponse)
def new_application_form(request: Request, user: CurrentUser = Depends(require_user)):
    return templates.TemplateResponse(
        request,
        "application_new.html",
        {"user": user, "documents": repo.list_documents(user.access_token), **FORM_CHOICES},
    )


@router.post("/applications/new")
def create_application(
    request: Request,
    company_name: str = Form(...),
    title: str = Form(...),
    source: str = Form("other"),
    url: str = Form(""),
    location: str = Form(""),
    mode: str = Form(""),
    level: str = Form(""),
    expires_at: str = Form(""),
    cv_document_id: str = Form(""),
    declared_salary: str = Form(""),
    declared_salary_kind: str = Form(""),
    declared_salary_period: str = Form(""),
    declared_contract: str = Form(""),
    status: str = Form("submitted"),
    blocked_reason: str = Form(""),
    notes: str = Form(""),
    user: CurrentUser = Depends(require_user),
):
    try:
        salary = float(declared_salary.replace(",", ".")) if declared_salary.strip() else None
    except ValueError:
        salary = None

    repo.create_application(
        user.access_token,
        user.id,
        company_name=company_name,
        title=title,
        source=source,
        url=url,
        location=location,
        mode=mode,
        level=level,
        expires_at=expires_at,
        cv_document_id=cv_document_id,
        declared_salary=salary,
        declared_salary_kind=declared_salary_kind,
        declared_salary_period=declared_salary_period,
        declared_contract=declared_contract,
        status=status,
        blocked_reason=blocked_reason,
        notes=notes,
    )
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
    return templates.TemplateResponse(
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
