"""Sign-up and sign-in.

Registration is invite-only. Public sign-up must also be switched off in the
Supabase dashboard (Authentication → Sign In / Providers → disable "Allow new
users to sign up"); otherwise anyone holding the anon key — which is public by
design — could create an account directly and bypass the invite check made
here.
"""

from dataclasses import dataclass

from app.db.client import new_anon_client, service_client


class AuthError(Exception):
    """Sign-up or sign-in was refused.

    Carries a translation key rather than a sentence: the service layer has no
    request and therefore no language. The route turns it into words. A key
    with no entry renders as itself, so a missed one is visible, not blank.
    """


@dataclass(frozen=True)
class Session:
    access_token: str
    refresh_token: str
    user_id: str
    email: str


def _session_from_supabase(response) -> Session:
    session = getattr(response, "session", None)
    user = getattr(response, "user", None)
    if session is None or user is None:
        raise AuthError("auth.error_bad_credentials")
    return Session(
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        user_id=user.id,
        email=user.email or "",
    )


def sign_in(email: str, password: str) -> Session:
    try:
        response = new_anon_client().auth.sign_in_with_password(
            {"email": email, "password": password}
        )
    except Exception as exc:  # supabase raises provider-specific errors
        raise AuthError("auth.error_bad_credentials") from exc
    return _session_from_supabase(response)


def sign_up(email: str, password: str, invite_code: str) -> Session:
    """Redeem an invite, create the account, then sign in.

    The invite is redeemed first and atomically: `redeem_invite` locks the row
    and increments the use count in one statement, so two people racing on the
    last remaining use cannot both succeed.
    """
    if len(password) < 10:
        raise AuthError("auth.error_short_password")

    admin = service_client()

    redeemed = admin.rpc(
        "redeem_invite", {"p_code": invite_code.strip(), "p_email": email}
    ).execute()
    if not redeemed.data:
        raise AuthError("auth.error_bad_invite")

    try:
        admin.auth.admin.create_user({"email": email, "password": password, "email_confirm": True})
    except Exception as exc:
        raise AuthError("auth.error_signup_failed") from exc

    return sign_in(email, password)


# ---------------------------------------------------------------------------
# Password recovery
# ---------------------------------------------------------------------------

MIN_PASSWORD_LENGTH = 10


def send_password_reset(email: str, redirect_to: str) -> None:
    """Ask Supabase to email a recovery link. Never reports whether it existed.

    Failures are swallowed on purpose: an error shown for one address and a
    success for another turns this form into a way to test who has an account
    here. Since this holds a job search, that is worth protecting.
    """
    try:
        new_anon_client().auth.reset_password_email(email, {"redirect_to": redirect_to})
    except Exception:
        pass


def reset_password(token_hash: str, new_password: str) -> Session:
    """Redeem a recovery token and set a new password.

    The link carries a token hash rather than a session in the URL fragment,
    so the exchange happens here rather than in the browser — see
    docs/SETUP.md for the email template this expects.
    """
    if len(new_password) < MIN_PASSWORD_LENGTH:
        raise AuthError("auth.error_short_password")

    client = new_anon_client()
    try:
        verified = client.auth.verify_otp({"token_hash": token_hash, "type": "recovery"})
    except Exception as exc:
        raise AuthError("auth.error_link_expired") from exc

    if getattr(verified, "session", None) is None:
        raise AuthError("auth.error_link_expired")

    try:
        client.auth.update_user({"password": new_password})
    except Exception as exc:
        raise AuthError("auth.error_password_refused") from exc

    return _session_from_supabase(verified)


# ---------------------------------------------------------------------------
# Closing an account
# ---------------------------------------------------------------------------


def delete_account(user_id: str) -> None:
    """Delete the account and everything belonging to it.

    Every user-owned table references `auth.users` with `on delete cascade`,
    so removing the auth user removes the rows with it — no sweep to forget.
    The id comes from the verified session and never from request input.
    """
    service_client().auth.admin.delete_user(user_id)
