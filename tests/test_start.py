"""The page a new account lands on.

Everything else assumes somebody who knows what Offerly is. This is the ten
minutes before that, and the thing it has to get right is the step people
actually fail on: Gmail will not forward to an unverified address, and the code
it sends to verify one arrives here rather than anywhere the reader is looking.
"""

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import CurrentUser, require_user
from app.db import repositories as repo
from app.main import app

USER = CurrentUser(id="u1", email="patryk@example.com", access_token="token")


@pytest.fixture
def client(monkeypatch):
    app.dependency_overrides[require_user] = lambda: USER
    state = {"arrived": 0}
    monkeypatch.setattr(
        repo,
        "get_profile",
        lambda token: {"ingest_token": "abc123", "plan": "free", "plan_until": None},
    )
    monkeypatch.setattr(repo, "inbound_count", lambda token: state["arrived"])
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "ingest_domain", "offerly.com.pl", raising=False)

    client = TestClient(app, cookies={"lang": "pl"})
    client.state = state
    yield client
    app.dependency_overrides.clear()


def test_signing_up_lands_on_the_setup_page_not_an_empty_dashboard():
    """A new account has nothing to look at and exactly one thing to do."""
    from app.web import routes_auth

    source = routes_auth.__file__
    with open(source, encoding="utf-8") as handle:
        text = handle.read()
    signup = text.split("def signup(")[1].split("def ")[0]
    assert 'RedirectResponse("/start"' in signup


def test_the_address_is_shown_and_can_be_copied(client):
    page = client.get("/start").text
    assert "abc123@offerly.com.pl" in page
    assert 'data-copy="start-address"' in page


def test_the_gmail_verification_trap_is_called_out(client):
    """The one step people fail at. If this page says nothing else useful, it
    has to say this."""
    page = client.get("/start").text
    assert "kod" in page.lower()
    assert "/inbox" in page


def test_a_paste_ready_filter_is_offered_for_the_boards(client):
    page = client.get("/start").text
    assert "from:(pracuj.pl OR linkedin.com" in page
    assert 'data-copy="start-boards"' in page


def test_the_reply_filter_is_narrow_and_says_so(client):
    """This reads somebody's private mailbox. A wide net would break the
    promise the landing page makes about it."""
    page = client.get("/start").text
    assert "{rekrutacj" in page
    assert "sieć, nie gwarancja" in page


def test_nothing_arrived_is_the_starting_state(client):
    assert "Nic jeszcze nie przyszło" in client.get("/start").text


def test_the_page_reports_success_once_mail_actually_arrives(client):
    """Observed, not asked. A checkbox would only record what somebody
    believed while they were reading the page."""
    client.state["arrived"] = 3
    page = client.get("/start").text
    assert "Działa" in page
    assert "Nic jeszcze nie przyszło" not in page


def test_there_is_something_to_do_while_waiting(client):
    """A page whose only instruction is "wait" is a page people close."""
    page = client.get("/start").text
    assert "/applications/new" in page
    assert "/answers" in page


def test_a_server_with_no_ingest_domain_says_so_rather_than_showing_half_an_address(
    client, monkeypatch
):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "ingest_domain", "", raising=False)
    page = client.get("/start").text
    assert "nie jest jeszcze skonfigurowany" in page
    assert 'data-copy="start-address"' not in page


def test_the_page_is_closed_to_anonymous_visitors():
    app.dependency_overrides.clear()
    response = TestClient(app).get("/start", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_the_empty_dashboard_points_at_the_setup(client, monkeypatch):
    """Where a returning account with nothing recorded actually lands."""
    from app.web.templates import TEMPLATE_DIR

    dashboard = (TEMPLATE_DIR / "dashboard.html").read_text(encoding="utf-8")
    assert 'href="/start"' in dashboard
