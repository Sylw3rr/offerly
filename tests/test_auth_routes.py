"""Routing and access-control behaviour that must hold without a database."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_home_redirects_anonymous_visitor_to_login():
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


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
    """A forged cookie must not grant access — the token is verified, not trusted."""
    response = client.get(
        "/", cookies={"offerly_access": "not-a-real-token"}, follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
