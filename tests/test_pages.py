"""Every signed-in page renders.

The templates are where this project breaks quietly: a renamed column or a
mistyped attribute produces a blank cell rather than an error, and nothing
notices until the page is opened by hand. These tests sign in a fake user and
feed each page the shape the repositories return, so a rendering mistake fails
here instead of in the browser.
"""

import pytest
from fastapi.testclient import TestClient

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

    monkeypatch.setattr(repo, "get_profile", lambda token: {"ghost_after_days": 21})
    monkeypatch.setattr(repo, "funnel_stats", lambda token: STATS)
    monkeypatch.setattr(repo, "list_applications", lambda token, status=None: [APPLICATION])
    monkeypatch.setattr(repo, "get_application", lambda token, application_id: APPLICATION)
    monkeypatch.setattr(repo, "status_history", lambda token, application_id: [])
    monkeypatch.setattr(repo, "list_documents", lambda token: [{"id": "d1", "label": "Support PL"}])
    monkeypatch.setattr(repo, "open_applications", lambda token: [])
    monkeypatch.setattr(repo, "recent_events", lambda token, limit=8: [])
    monkeypatch.setattr(repo, "list_profile_answers", lambda token: [])

    yield TestClient(app)
    app.dependency_overrides.clear()


def test_dashboard_renders_with_nothing_to_chase(client):
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "Needs attention" in response.text
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
    assert "Declared" in response.text


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
    assert "No answers yet" in response.text


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
    assert 'data-answer="p1"' in response.text


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
    for path in ("/dashboard", "/applications", "/answers"):
        assert f'href="{path}"' in response.text
