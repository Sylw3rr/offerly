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

    @property
    def first_name(self) -> str:
        """Something to greet with until there is a real name to use.

        `patryk.sylwerski@…` becomes Patryk. Not always right, but friendlier
        than an email address in a headline, and the visitor can see where it
        came from.
        """
        local = self.email.split("@")[0]
        part = local.replace("_", ".").split(".")[0]
        return part.capitalize() if part else self.email


def set_session_cookies(response: Response, session: Session) -> None:
    settings = get_settings()
    # Taken from the address rather than from a separate environment flag:
    # APP_BASE_URL has to be right anyway for password recovery to work, and a
    # deployment where someone forgot to also set APP_ENV would otherwise send
    # session cookies without the Secure attribute over a public connection.
    secure = settings.app_base_url.startswith("https://")
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

    Access tokens expire after an hour. When one has, the refresh token is
    used to obtain a new pair; the replacement is stashed on `request.state`
    so the middleware can write the cookies back. Without this the user is
    silently signed out mid-session.
    """
    from app.db.client import anon_client

    token = request.cookies.get(ACCESS_COOKIE)
    if token:
        try:
            response = anon_client().auth.get_user(token)
            user = getattr(response, "user", None)
            if user is not None:
                return CurrentUser(id=user.id, email=user.email or "", access_token=token)
        except Exception:
            pass  # expired or invalid — fall through to refresh

    refresh_token = request.cookies.get(REFRESH_COOKIE)
    if not refresh_token:
        return None

    try:
        refreshed = anon_client().auth.refresh_session(refresh_token)
    except Exception:
        return None

    session = getattr(refreshed, "session", None)
    user = getattr(refreshed, "user", None)
    if session is None or user is None:
        return None

    request.state.refreshed_session = Session(
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        user_id=user.id,
        email=user.email or "",
    )
    return CurrentUser(id=user.id, email=user.email or "", access_token=session.access_token)


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
