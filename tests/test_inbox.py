"""The inbox: what the webhook would not decide on its own.

Everything confident enough to act on was acted on when it arrived. What is
here is what a person has to judge, so the tests are mostly about not acting
too eagerly.
"""

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import CurrentUser, require_user
from app.db import repositories as repo
from app.main import app

USER = CurrentUser(id="u1", email="patryk@example.com", access_token="token")


def arrived(**over):
    row = {
        "id": "m1",
        "received_at": "2026-08-19T14:30:00+00:00",
        "kind": "employer_reply",
        "from_address": "rekrutacja@acme.pl",
        "from_domain": "acme.pl",
        "subject": "Twoja aplikacja",
        "body": "Niestety wybraliśmy innego kandydata.",
        "handled_at": None,
        "application_id": "a1",
        "applications": {
            "id": "a1",
            "status": "submitted",
            "offers": {"title": "Helpdesk", "companies": {"name": "Acme"}},
        },
    }
    row.update(over)
    return row


@pytest.fixture
def client(monkeypatch):
    app.dependency_overrides[require_user] = lambda: USER
    moved, handled = [], []
    monkeypatch.setattr(repo, "list_inbound", lambda token, limit=60: ROWS)
    monkeypatch.setattr(repo, "get_inbound", lambda token, i: next(r for r in ROWS if r["id"] == i))
    monkeypatch.setattr(repo, "change_status", lambda t, u, a, s, note=None: moved.append((a, s)))
    monkeypatch.setattr(repo, "mark_inbound_handled", lambda t, i: handled.append(i))

    client = TestClient(app, cookies={"lang": "en"})
    client.moved, client.handled = moved, handled
    yield client
    app.dependency_overrides.clear()


ROWS = [arrived()]


def test_the_inbox_lists_what_arrived(client):
    response = client.get("/inbox")
    assert response.status_code == 200
    assert "Twoja aplikacja" in response.text
    assert "rekrutacja@acme.pl" in response.text
    assert "Acme" in response.text


def test_a_suggestion_is_offered_rather_than_applied(client):
    """It reached the inbox precisely because nothing was certain enough."""
    response = client.get("/inbox")
    assert 'action="/inbox/m1/confirm"' in response.text
    assert client.moved == []


def test_confirming_moves_the_application_and_files_the_message(client):
    response = client.post("/inbox/m1/confirm", follow_redirects=False)
    assert response.status_code == 303
    assert client.moved == [("a1", "rejected")]
    assert client.handled == ["m1"]


def test_the_status_is_worked_out_again_rather_than_taken_from_the_request(client):
    """A status arriving in a form body is a status anyone could have typed."""
    client.post("/inbox/m1/confirm", data={"status": "offer"})
    assert client.moved == [("a1", "rejected")]


def test_setting_aside_files_it_without_touching_the_application(client):
    client.post("/inbox/m1/dismiss")
    assert client.handled == ["m1"]
    assert client.moved == []


def test_a_message_matching_nothing_offers_no_confirmation(client, monkeypatch):
    monkeypatch.setattr(
        repo,
        "list_inbound",
        lambda token, limit=60: [arrived(application_id=None, applications=None)],
    )
    response = client.get("/inbox")
    assert "/confirm" not in response.text


def test_a_message_agreeing_with_the_current_status_needs_no_decision(client, monkeypatch):
    """Already rejected, and the mail says rejected: nothing to ask about."""
    monkeypatch.setattr(
        repo,
        "list_inbound",
        lambda token, limit=60: [
            arrived(
                applications={
                    "id": "a1",
                    "status": "rejected",
                    "offers": {"title": "Helpdesk", "companies": {"name": "Acme"}},
                }
            )
        ],
    )
    assert "/confirm" not in client.get("/inbox").text


def test_something_already_dealt_with_is_not_asked_about_again(client, monkeypatch):
    monkeypatch.setattr(
        repo, "list_inbound", lambda token, limit=60: [arrived(handled_at="2026-08-19T15:00:00Z")]
    )
    response = client.get("/inbox")
    assert "/confirm" not in response.text
    assert "Handled" in response.text


def test_a_board_alert_carries_no_suggestion(client, monkeypatch):
    monkeypatch.setattr(
        repo,
        "list_inbound",
        lambda token, limit=60: [
            arrived(
                kind="offer_alert",
                from_address="jobalert@wysylka.pracuj.pl",
                subject="Nowe oferty pracy",
                body="Znaleźliśmy 12 ofert",
                application_id=None,
                applications=None,
            )
        ],
    )
    response = client.get("/inbox")
    assert "Board alert" in response.text
    assert "/confirm" not in response.text


def test_confirming_something_that_matched_nothing_changes_nothing(client, monkeypatch):
    monkeypatch.setattr(
        repo, "get_inbound", lambda token, i: arrived(application_id=None, applications=None)
    )
    client.post("/inbox/m1/confirm")
    assert client.moved == []


def test_an_empty_inbox_explains_how_to_fill_it(client, monkeypatch):
    monkeypatch.setattr(repo, "list_inbound", lambda token, limit=60: [])
    response = client.get("/inbox")
    assert "Nothing has arrived yet" in response.text
    assert "Forward a board alert" in response.text
