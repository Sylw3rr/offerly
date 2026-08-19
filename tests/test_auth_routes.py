"""Routing and access-control behaviour that must hold without a database."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, cookies={"lang": "en"})


def test_home_shows_the_landing_to_a_visitor():
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 200
    assert "Offerly" in response.text


def test_every_signed_in_page_is_closed_to_anonymous_visitors():
    for path in ("/dashboard", "/applications", "/applications/new", "/answers"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 303, path
        assert response.headers["location"] == "/login", path


def test_login_page_renders():
    response = client.get("/login")
    assert response.status_code == 200
    assert "Sign in" in response.text


def test_signup_page_states_it_is_invite_only():
    response = client.get("/signup")
    assert response.status_code == 200
    assert "Invite code" in response.text


def test_logout_clears_session_and_redirects():
    response = client.post("/logout", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_garbage_access_cookie_is_not_treated_as_a_session():
    """A forged cookie must not grant access — the token is verified, not trusted.

    Since `/` became the landing, the proof moved to a page that requires one.
    """
    response = client.get(
        "/dashboard", cookies={"offerly_access": "not-a-real-token"}, follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_session_cookies_are_marked_secure_when_the_app_answers_over_https(monkeypatch):
    """Read off the address rather than a separate flag: a deployment where
    someone set APP_BASE_URL but forgot APP_ENV would otherwise hand out
    session cookies without the Secure attribute."""
    from app.auth import dependencies, service
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "app_base_url", "https://offerly.com.pl", raising=False)
    monkeypatch.setattr(
        service,
        "sign_in",
        lambda email, password: service.Session(
            access_token="a", refresh_token="r", user_id="u1", email=email
        ),
    )
    response = TestClient(app).post(
        "/login", data={"email": "a@b.pl", "password": "x"}, follow_redirects=False
    )
    assert "Secure" in response.headers["set-cookie"]
    assert dependencies.ACCESS_COOKIE in response.headers["set-cookie"]


def test_session_cookies_are_not_secure_on_a_local_http_address(monkeypatch):
    """Otherwise the browser drops them and nobody can sign in locally."""
    from app.auth import service
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "app_base_url", "http://127.0.0.1:8000", raising=False)
    monkeypatch.setattr(
        service,
        "sign_in",
        lambda email, password: service.Session(
            access_token="a", refresh_token="r", user_id="u1", email=email
        ),
    )
    response = TestClient(app).post(
        "/login", data={"email": "a@b.pl", "password": "x"}, follow_redirects=False
    )
    assert "Secure" not in response.headers["set-cookie"]
