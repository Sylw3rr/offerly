"""Every signed-in page renders.

The templates are where this project breaks quietly: a renamed column or a
mistyped attribute produces a blank cell rather than an error, and nothing
notices until the page is opened by hand. These tests sign in a fake user and
feed each page the shape the repositories return, so a rendering mistake fails
here instead of in the browser.
"""

import re

import pytest
from fastapi.testclient import TestClient

from app.auth import service
from app.auth.dependencies import CurrentUser, require_user
from app.db import repositories as repo
from app.main import app

USER = CurrentUser(id="user-1", email="patryk@example.com", access_token="token")

OFFER = {
    "id": "o1",
    "title": "Support specialist",
    "source": "pracuj_pl",
    "url": "https://example.com/offer",
    "location": "Gliwice",
    "mode": "hybrid",
    "level": "junior",
    "expires_at": "2026-09-01",
    "salary_min": 8000,
    "salary_max": 12000,
    "salary_currency": "PLN",
    "salary_kind": "gross",
    "salary_period": "month",
    "contract": "employment",
    "companies": {"id": "c1", "name": "Acme"},
}

APPLICATION = {
    "id": "a1",
    "status": "submitted",
    "submitted_at": "2026-07-20T09:00:00+00:00",
    "declared_salary": 9500,
    "declared_salary_kind": "gross",
    "declared_salary_period": "month",
    "declared_contract": "employment",
    "blocked_reason": None,
    "notes": "Applied through the form on their site.",
    "offers": OFFER,
    "documents": {"id": "d1", "label": "Support PL"},
}

STATS = {
    "total": 3,
    "sent": 2,
    "responded": 1,
    "response_rate": 50.0,
    "by_status": {"submitted": 2, "interview": 1},
}


@pytest.fixture
def client(monkeypatch):
    """A signed-in client whose data layer is stubbed out."""
    app.dependency_overrides[require_user] = lambda: USER

    monkeypatch.setattr(
        repo,
        "get_profile",
        lambda token: {"ghost_after_days": 21, "plan": "free", "plan_until": None},
    )
    monkeypatch.setattr(repo, "funnel_stats", lambda token: STATS)
    monkeypatch.setattr(repo, "list_applications", lambda token, status=None: [APPLICATION])
    monkeypatch.setattr(repo, "get_application", lambda token, application_id: APPLICATION)
    monkeypatch.setattr(repo, "status_history", lambda token, application_id: [])
    monkeypatch.setattr(repo, "list_documents", lambda token: [{"id": "d1", "label": "Support PL"}])
    monkeypatch.setattr(repo, "open_applications", lambda token: [])
    monkeypatch.setattr(repo, "recent_events", lambda token, limit=8: [])
    monkeypatch.setattr(repo, "list_profile_answers", lambda token: [])
    monkeypatch.setattr(repo, "all_status_events", lambda token: [])
    monkeypatch.setattr(repo, "last_moves", lambda token: {})

    # English, so the assertions below read as the strings they check. The
    # interface defaults to Polish; the cookie is the same one the account
    # page sets.
    yield TestClient(app, cookies={"lang": "en"})
    app.dependency_overrides.clear()


def test_dashboard_renders_with_nothing_to_chase(client):
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "Today" in response.text
    assert "Nothing to chase" in response.text
    # The ghosting window is stated rather than left as a mystery number.
    assert "21 days" in response.text


def test_dashboard_lists_what_needs_attention(client, monkeypatch):
    monkeypatch.setattr(
        repo,
        "open_applications",
        lambda token: [
            {
                "id": "a1",
                "status": "blocked",
                "submitted_at": None,
                "blocked_reason": "External form, CV by hand",
                "offers": {"title": "Helpdesk", "expires_at": None, "companies": {"name": "Zeta"}},
            }
        ],
    )
    response = client.get("/dashboard")
    assert "Zeta" in response.text
    assert "External form, CV by hand" in response.text
    assert 'href="/applications/a1"' in response.text


def test_dashboard_shows_recent_activity(client, monkeypatch):
    monkeypatch.setattr(
        repo,
        "recent_events",
        lambda token, limit=8: [
            {
                "from_status": "submitted",
                "to_status": "interview",
                "source": "manual",
                "note": "Call on Tuesday",
                "created_at": "2026-08-14T10:00:00+00:00",
                "applications": {"id": "a1", "offers": OFFER},
            }
        ],
    )
    response = client.get("/dashboard")
    assert "Call on Tuesday" in response.text
    assert "2026-08-14" in response.text


def test_registry_shows_the_advertised_range_next_to_what_was_declared(client):
    response = client.get("/applications")
    assert response.status_code == 200
    assert "8 000–12 000 PLN gross/month" in response.text
    assert "9 500 gross/month" in response.text


def test_application_detail_renders_both_salary_figures(client):
    response = client.get("/applications/a1")
    assert response.status_code == 200
    assert "Advertised" in response.text
    assert "8 000–12 000 PLN gross/month" in response.text
    assert "You quoted" in response.text


def test_missing_salary_figures_render_as_a_dash_not_an_error(client, monkeypatch):
    bare_offer = dict(OFFER, salary_min=None, salary_max=None)
    bare = dict(APPLICATION, offers=bare_offer, declared_salary=None)
    monkeypatch.setattr(repo, "list_applications", lambda token, status=None: [bare])
    response = client.get("/applications")
    assert response.status_code == 200
    assert "—" in response.text


def test_new_application_form_offers_the_advertised_range_fields(client):
    response = client.get("/applications/new")
    assert response.status_code == 200
    for field in ("salary_min", "salary_max", "salary_currency", "contract"):
        assert f'name="{field}"' in response.text


def test_answers_page_suggests_labels_when_empty(client):
    response = client.get("/answers")
    assert response.status_code == 200
    assert "Notice period" in response.text
    assert "Nothing here yet" in response.text


def test_answers_page_lists_saved_answers_with_a_copy_button(client, monkeypatch):
    monkeypatch.setattr(
        repo,
        "list_profile_answers",
        lambda token: [
            {"id": "p1", "label": "Notice period", "value": "One month", "sort_order": 0}
        ],
    )
    response = client.get("/answers")
    assert "One month" in response.text
    assert 'data-copy="value-p1"' in response.text


def test_duplicate_answer_label_is_explained_rather_than_thrown(client, monkeypatch):
    def refuse(token, user_id, label, value):
        raise RuntimeError("duplicate key value violates unique constraint")

    monkeypatch.setattr(repo, "create_profile_answer", refuse)
    response = client.post(
        "/answers", data={"label": "Notice period", "value": "One month"}, follow_redirects=False
    )
    assert response.status_code == 200
    assert "already have an answer" in response.text


def test_navigation_links_to_every_section(client):
    response = client.get("/dashboard")
    for path in ("/dashboard", "/applications", "/answers", "/account"):
        assert f'href="{path}"' in response.text


def test_the_registry_can_be_searched_by_company(client):
    response = client.get("/applications?q=acme")
    assert "Support specialist" in response.text


def test_a_search_that_matches_nothing_says_so_rather_than_looking_empty(client):
    response = client.get("/applications?q=zzzz")
    assert "Nothing matches" in response.text
    assert "Support specialist" not in response.text


def test_search_survives_the_status_filter(client):
    """The chips keep the query and the search box keeps the status."""
    response = client.get("/applications?q=acme&status=submitted")
    assert 'value="acme"' in response.text
    assert 'name="status" value="submitted"' in response.text


def test_the_registry_says_when_each_application_last_moved(client, monkeypatch):
    monkeypatch.setattr(repo, "last_moves", lambda token: {"a1": "2020-01-01T10:00:00+00:00"})
    response = client.get("/applications")
    assert "days ago" in response.text


def test_choosing_a_language_sets_the_cookie_the_pages_read(client):
    response = client.post("/account/preferences", data={"lang": "en"}, follow_redirects=False)
    assert response.status_code == 303
    assert "lang=en" in response.headers["set-cookie"]


def test_an_unknown_language_is_ignored_rather_than_stored(client):
    response = client.post("/account/preferences", data={"lang": "xx"}, follow_redirects=False)
    assert "lang=" not in response.headers.get("set-cookie", "")


def test_pages_fetch_nothing_from_anyone_else(client):
    """The stylesheet, the script and every icon are served from here.

    A page that pulls a font or an icon set off a CDN tells whoever hosts it
    that a job search is happening, and stops working on a train. Links the
    user typed themselves are not requests the page makes.
    """
    loaders = re.compile(r'(?:src|href)\s*=\s*"(?:https?:)?//([^/"]+)', re.IGNORECASE)
    for path in ("/dashboard", "/applications", "/applications/new", "/answers", "/account"):
        body = client.get(path).text
        outside = {host for host in loaders.findall(body) if host != "testserver"}
        assert outside == set(), f"{path} reaches out to {outside}"
        assert "@import" not in body, path


# ---------------------------------------------------------------------------
# Correcting and removing an application
# ---------------------------------------------------------------------------


def test_edit_form_arrives_filled_in_with_what_is_stored(client):
    response = client.get("/applications/a1/edit")
    assert response.status_code == 200
    assert 'value="Acme"' in response.text
    assert 'value="Support specialist"' in response.text
    assert 'value="8000"' in response.text  # not 8000.00
    assert 'value="2026-07-20"' in response.text  # the send date, not a timestamp


def test_edit_form_cannot_change_status(client):
    """Status moves only through the panel that records it in the history."""
    response = client.get("/applications/a1/edit")
    assert 'name="status"' not in response.text


def test_editing_saves_the_new_values(client, monkeypatch):
    seen = {}

    def capture(token, user_id, application_id, **fields):
        seen.update({"id": application_id, **fields})

    monkeypatch.setattr(repo, "update_application", capture)
    response = client.post(
        "/applications/a1/edit",
        data={"company_name": "Acme Poland", "title": "Support specialist", "salary_min": "9 000"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/applications/a1"
    assert seen["id"] == "a1"
    assert seen["company_name"] == "Acme Poland"
    assert seen["salary_min"] == 9000.0  # the space did not defeat it


def test_a_range_typed_back_to_front_is_swapped_not_lost(client, monkeypatch):
    seen = {}
    monkeypatch.setattr(repo, "update_application", lambda t, u, i, **f: seen.update(f))
    client.post(
        "/applications/a1/edit",
        data={"company_name": "Acme", "title": "Role", "salary_min": "12000", "salary_max": "8000"},
    )
    assert (seen["salary_min"], seen["salary_max"]) == (8000.0, 12000.0)


def test_deleting_an_application_returns_to_the_registry(client, monkeypatch):
    deleted = []
    monkeypatch.setattr(repo, "delete_application", lambda token, i: deleted.append(i))
    response = client.post("/applications/a1/delete", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/applications"
    assert deleted == ["a1"]


def test_detail_page_offers_both_editing_and_deleting(client):
    response = client.get("/applications/a1")
    assert 'href="/applications/a1/edit"' in response.text
    assert 'action="/applications/a1/delete"' in response.text


def test_an_old_application_keeps_the_date_it_was_actually_sent(client, monkeypatch):
    seen = {}
    monkeypatch.setattr(
        repo, "create_application", lambda t, u, status, **f: seen.update(f) or "a9"
    )
    client.post(
        "/applications/new",
        data={"company_name": "Acme", "title": "Role", "submitted_on": "2026-06-01"},
    )
    assert seen["submitted_at"].startswith("2026-06-01T12:00")


# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------


def test_the_account_page_states_the_plan_and_what_the_other_one_adds(client):
    response = client.get("/account")
    assert "Free" in response.text
    assert "Offers collected from forwarded mail" in response.text


def test_the_free_plan_says_there_is_no_checkout_rather_than_showing_a_dead_button(client):
    response = client.get("/account")
    assert "no checkout" in response.text
    assert 'action="/account/upgrade"' not in response.text


def test_a_paid_account_is_not_sold_to(client, monkeypatch):
    monkeypatch.setattr(
        repo,
        "get_profile",
        lambda token: {"ghost_after_days": 21, "plan": "plus", "plan_until": None},
    )
    response = client.get("/account")
    assert "Plus is active" in response.text
    assert "no checkout" not in response.text


def test_the_cv_ceiling_is_stated_before_it_is_met(client):
    response = client.get("/applications/new")
    assert "Using 1 of 2 CV versions" in response.text


def test_at_the_ceiling_the_form_is_replaced_by_the_reason(client, monkeypatch):
    monkeypatch.setattr(
        repo,
        "list_documents",
        lambda token: [{"id": "d1", "label": "Support"}, {"id": "d2", "label": "Sales"}],
    )
    response = client.get("/applications/new")
    assert "The free plan keeps 2 CV versions" in response.text
    assert 'action="/documents/new"' not in response.text


def test_a_plus_account_is_never_told_about_a_ceiling(client, monkeypatch):
    monkeypatch.setattr(
        repo,
        "get_profile",
        lambda token: {"ghost_after_days": 21, "plan": "plus", "plan_until": None},
    )
    response = client.get("/applications/new")
    assert "CV versions on the free plan" not in response.text
    assert 'action="/documents/new"' in response.text


def test_a_refused_cv_version_returns_to_the_form_saying_why(client, monkeypatch):
    def refuse(token, user_id, label, kind="cv"):
        raise repo.DocumentLimitReached

    monkeypatch.setattr(repo, "create_document", refuse)
    response = client.post("/documents/new", data={"label": "Third"}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/applications/new?cv_limit=1"


# ---------------------------------------------------------------------------
# Account
# ---------------------------------------------------------------------------


def test_account_page_offers_an_export_before_it_offers_deletion(client):
    response = client.get("/account")
    assert response.status_code == 200
    assert response.text.index("applications.csv") < response.text.index("/account/delete")


def test_applications_export_is_a_csv_with_a_header_and_the_rows(client):
    response = client.get("/account/applications.csv")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "offerly-applications.csv" in response.headers["content-disposition"]
    body = response.text
    assert body.startswith("﻿")  # so spreadsheets read the accents right
    assert "company,role,status" in body
    assert "Acme" in body


def test_answers_export_lists_the_saved_answers(client, monkeypatch):
    monkeypatch.setattr(
        repo,
        "list_profile_answers",
        lambda token: [{"id": "p1", "label": "Notice period", "value": "One month"}],
    )
    body = client.get("/account/answers.csv").text
    assert "label,answer" in body
    assert "Notice period,One month" in body


def test_account_deletion_needs_the_address_typed_correctly(client, monkeypatch):
    called = []
    monkeypatch.setattr(service, "delete_account", lambda user_id: called.append(user_id))
    response = client.post("/account/delete", data={"confirm_email": "typo@example.com"})
    assert response.status_code == 400
    assert called == []


def test_account_deletion_passes_the_id_from_the_session_not_the_form(client, monkeypatch):
    called = []
    monkeypatch.setattr(service, "delete_account", lambda user_id: called.append(user_id))
    response = client.post(
        "/account/delete",
        data={"confirm_email": "PATRYK@example.com", "user_id": "somebody-else"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert called == [USER.id]


def test_signing_out_happens_with_the_account_deletion(client, monkeypatch):
    monkeypatch.setattr(service, "delete_account", lambda user_id: None)
    response = client.post(
        "/account/delete", data={"confirm_email": USER.email}, follow_redirects=False
    )
    assert 'offerly_access=""' in response.headers.get("set-cookie", "")
