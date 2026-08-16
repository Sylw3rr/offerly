"""Session cookies and the current-user dependency."""

from dataclasses import dataclass

from fastapi import Request, Response
from fastapi.responses import RedirectResponse

from app.auth.service import Session
from app.config import get_settings

ACCESS_COOKIE = "offerly_access"
REFRESH_COOKIE = "offerly_refresh"


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str
    access_token: str


def set_session_cookies(response: Response, session: Session) -> None:
    settings = get_settings()
    secure = settings.app_env != "development"
    common = {
        "httponly": True,  # not readable from JavaScript
        "secure": secure,  # HTTPS only outside local development
        "samesite": "lax",  # blocks cross-site form posts
        "path": "/",
    }
    response.set_cookie(ACCESS_COOKIE, session.access_token, max_age=60 * 60, **common)
    response.set_cookie(REFRESH_COOKIE, session.refresh_token, max_age=60 * 60 * 24 * 30, **common)


def clear_session_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/")


def get_current_user(request: Request) -> CurrentUser | None:
    """Resolve the signed-in user, or None.

    The token is verified by Supabase rather than decoded here: a locally
    decoded JWT would tell us what the token claims, not whether it is still
    valid.
    """
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        return None

    from app.db.client import anon_client

    try:
        response = anon_client().auth.get_user(token)
    except Exception:
        return None

    user = getattr(response, "user", None)
    if user is None:
        return None
    return CurrentUser(id=user.id, email=user.email or "", access_token=token)


def require_user(request: Request) -> CurrentUser:
    """Dependency for protected routes. Redirects to sign-in when absent."""
    user = get_current_user(request)
    if user is None:
        raise _RedirectToLogin()
    return user


class _RedirectToLogin(Exception):
    """Raised by require_user; converted to a redirect by the exception handler."""


def redirect_to_login() -> RedirectResponse:
    return RedirectResponse("/login", status_code=303)
