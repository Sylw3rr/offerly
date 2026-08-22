"""The account page: take your data out, or close the account.

Both belong together. A tool holding a job search should make leaving as
straightforward as arriving — and an export is what makes deletion a decision
rather than a loss.
"""

import csv
import io
import logging

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from app import plans
from app.auth import service
from app.auth.dependencies import CurrentUser, clear_session_cookies, require_user
from app.config import get_settings
from app.db import repositories as repo
from app.i18n import LANG_COOKIE, SUPPORTED, template_globals
from app.web.templates import render

log = logging.getLogger(__name__)

router = APIRouter(tags=["account"])

APPLICATION_COLUMNS = [
    "company",
    "role",
    "status",
    "source",
    "location",
    "mode",
    "level",
    "submitted_on",
    "offer_closes",
    "salary_min",
    "salary_max",
    "currency",
    "salary_kind",
    "salary_period",
    "contract_offered",
    "declared_salary",
    "declared_kind",
    "declared_period",
    "declared_contract",
    "cv_version",
    "blocked_reason",
    "url",
    "notes",
]


def _csv_response(filename: str, header: list[str], rows: list[list[object]]) -> Response:
    """A CSV the user's spreadsheet will open without an import wizard.

    The byte order mark is there for Excel: without it, every Polish character
    in a company name arrives mangled.
    """
    buffer = io.StringIO()
    buffer.write("﻿")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/account", response_class=HTMLResponse)
def account(request: Request, user: CurrentUser = Depends(require_user)):
    profile = repo.get_profile(user.access_token)
    settings = get_settings()
    token = profile.get("ingest_token")
    return render(
        request,
        "account.html",
        {
            "user": user,
            "error": None,
            # Empty until a domain is configured; showing "token@" with nothing
            # after it would be worse than saying the feature is not set up.
            "ingest_address": (
                f"{token}@{settings.ingest_domain}" if token and settings.ingest_domain else None
            ),
            "plan": plans.for_profile(profile),
            "plan_until": profile.get("plan_until"),
            "is_plus": plans.for_profile(profile).name == plans.PLUS,
            # The flag rather than the whole profile: that row carries the
            # forwarding token, which is the address's secret and has no
            # business being reachable from every expression in the template.
            "reminders_enabled": profile.get("reminders_enabled", True),
        },
    )


@router.post("/account/preferences")
def save_preferences(lang: str = Form("pl"), user: CurrentUser = Depends(require_user)):
    """Interface language: a cookie for the browser, a column for the jobs.

    The cookie means the sign-in screen can already be in the right language
    before there is anyone to look a profile up for. The column means a
    reminder written by a nightly job is in the same language as the app.
    """
    response = RedirectResponse("/account", status_code=303)
    if lang in SUPPORTED:
        # Written to the account as well as the cookie. The cookie renders the
        # page; the column is what a scheduled job reads at four in the morning
        # when there is no browser to ask.
        #
        # The cookie is set either way. Someone clicking "English" wants this
        # page in English, and failing that because a column could not be
        # written would be trading the thing they asked for against the thing
        # a mail needs next week.
        try:
            repo.set_language(user.access_token, user.id, lang)
        except Exception:  # noqa: BLE001 — the preference still applies
            log.warning("could not record the language for %s", user.id, exc_info=True)
        response.set_cookie(
            LANG_COOKIE,
            lang,
            max_age=60 * 60 * 24 * 365,
            samesite="lax",
            secure=get_settings().app_base_url.startswith("https://"),
            path="/",
        )
    return response


@router.post("/account/reminders")
def save_reminders(reminders_enabled: str = Form(""), user: CurrentUser = Depends(require_user)):
    """The switch for the only mail Offerly sends.

    An unchecked checkbox is simply absent from the form, so the presence of
    the field is the value — which is also why this is its own form rather than
    a field on the language one: submitting that form must not silently switch
    reminders off.
    """
    repo.set_reminders(user.access_token, user.id, bool(reminders_enabled))
    return RedirectResponse("/account", status_code=303)


@router.get("/account/applications.csv")
def export_applications(user: CurrentUser = Depends(require_user)):
    rows = []
    for a in repo.list_applications(user.access_token):
        offer = a.get("offers") or {}
        company = offer.get("companies") or {}
        document = a.get("documents") or {}
        rows.append(
            [
                company.get("name", ""),
                offer.get("title", ""),
                a.get("status", ""),
                offer.get("source", ""),
                offer.get("location", ""),
                offer.get("mode", ""),
                offer.get("level", ""),
                (a.get("submitted_at") or "")[:10],
                offer.get("expires_at", ""),
                offer.get("salary_min", ""),
                offer.get("salary_max", ""),
                offer.get("salary_currency", ""),
                offer.get("salary_kind", ""),
                offer.get("salary_period", ""),
                offer.get("contract", ""),
                a.get("declared_salary", ""),
                a.get("declared_salary_kind", ""),
                a.get("declared_salary_period", ""),
                a.get("declared_contract", ""),
                document.get("label", ""),
                a.get("blocked_reason", ""),
                offer.get("url", ""),
                a.get("notes", ""),
            ]
        )
    return _csv_response("offerly-applications.csv", APPLICATION_COLUMNS, rows)


@router.get("/account/answers.csv")
def export_answers(user: CurrentUser = Depends(require_user)):
    rows = [
        [answer["label"], answer["value"]]
        for answer in repo.list_profile_answers(user.access_token)
    ]
    return _csv_response("offerly-answers.csv", ["label", "answer"], rows)


@router.post("/account/delete")
def delete_account(
    request: Request,
    confirm_email: str = Form(...),
    user: CurrentUser = Depends(require_user),
):
    """Close the account for good.

    Typing the address is the confirmation: it is the one thing a misdirected
    click cannot produce. The id passed to the delete comes from the verified
    session, never from this form — the field is only ever compared.
    """
    if confirm_email.strip().lower() != user.email.lower():
        t = template_globals(request)["t"]
        profile = repo.get_profile(user.access_token)
        return render(
            request,
            "account.html",
            {
                "user": user,
                "error": t("account.error_wrong_email"),
                "plan": plans.for_profile(profile),
                "plan_until": profile.get("plan_until"),
                "is_plus": plans.for_profile(profile).name == plans.PLUS,
                # The flag rather than the whole profile: that row carries the
                # forwarding token, which is the address's secret and has no
                # business being reachable from every expression in the template.
                "reminders_enabled": profile.get("reminders_enabled", True),
            },
            status_code=400,
        )

    service.delete_account(user.id)
    response = RedirectResponse("/login", status_code=303)
    clear_session_cookies(response)
    return response
