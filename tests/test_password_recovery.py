"""Password recovery, which has to work for people who are already locked out."""

from fastapi.testclient import TestClient

from app.auth import service
from app.main import app

client = TestClient(app, cookies={"lang": "en"})


def test_sign_in_page_links_to_recovery():
    assert 'href="/forgot-password"' in client.get("/login").text


def test_recovery_form_renders():
    response = client.get("/forgot-password")
    assert response.status_code == 200
    assert 'name="email"' in response.text


def test_the_same_answer_comes_back_whether_or_not_the_address_is_registered(monkeypatch):
    """Otherwise the form becomes a way to ask who has an account here."""
    monkeypatch.setattr(service, "send_password_reset", lambda email, redirect_to: None)

    known = client.post("/forgot-password", data={"email": "patryk@example.com"})
    unknown = client.post("/forgot-password", data={"email": "nobody@example.com"})

    assert known.status_code == unknown.status_code == 200
    assert known.text == unknown.text
    assert "If that address has an account" in known.text


def test_a_failure_from_the_provider_is_swallowed_rather_than_shown(monkeypatch):
    """A rate-limit error shown for one address and not another leaks the same
    fact the identical wording is there to hide."""

    class Exploding:
        class auth:
            @staticmethod
            def reset_password_email(email, options):
                raise RuntimeError("rate limited")

    monkeypatch.setattr("app.auth.service.new_anon_client", lambda: Exploding)
    service.send_password_reset("patryk@example.com", "http://localhost/reset-password")


def test_the_link_points_back_at_this_installation(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        service, "send_password_reset", lambda email, redirect_to: seen.update(url=redirect_to)
    )
    client.post("/forgot-password", data={"email": "patryk@example.com"})
    assert seen["url"].endswith("/reset-password")


def test_reset_page_without_a_token_explains_itself_instead_of_showing_a_dead_form():
    response = client.get("/reset-password")
    assert response.status_code == 200
    assert "Open the link from the email again" in response.text
    assert 'name="password"' not in response.text


def test_reset_page_with_a_token_shows_the_form():
    response = client.get("/reset-password?token_hash=abc123&type=recovery")
    assert 'value="abc123"' in response.text
    assert 'name="password"' in response.text


def test_mismatched_passwords_are_caught_before_the_token_is_spent(monkeypatch):
    called = []
    monkeypatch.setattr(service, "reset_password", lambda *a: called.append(a))
    response = client.post(
        "/reset-password",
        data={"token_hash": "abc", "password": "correct-horse", "password_again": "typo-typo-typo"},
    )
    assert response.status_code == 400
    assert "do not match" in response.text
    assert called == []


def test_an_expired_link_says_so(monkeypatch):
    def refuse(token_hash, password):
        raise service.AuthError("auth.error_link_expired")

    monkeypatch.setattr(service, "reset_password", refuse)
    response = client.post(
        "/reset-password",
        data={"token_hash": "old", "password": "correct-horse", "password_again": "correct-horse"},
    )
    assert response.status_code == 400
    assert "expired" in response.text


def test_a_successful_reset_signs_the_person_in(monkeypatch):
    monkeypatch.setattr(
        service,
        "reset_password",
        lambda token_hash, password: service.Session(
            access_token="new-access",
            refresh_token="new-refresh",
            user_id="u1",
            email="patryk@example.com",
        ),
    )
    response = client.post(
        "/reset-password",
        data={"token_hash": "ok", "password": "correct-horse", "password_again": "correct-horse"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert "offerly_access=new-access" in response.headers["set-cookie"]


def test_a_short_password_is_refused_without_touching_the_network():
    try:
        service.reset_password("token", "short")
    except service.AuthError as exc:
        assert str(exc) == "auth.error_short_password"
    else:  # pragma: no cover - the guard is the point of the test
        raise AssertionError("a five-character password was accepted")
