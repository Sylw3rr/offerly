"""Sign-up and sign-in.

Registration is invite-only. Public sign-up must also be switched off in the
Supabase dashboard (Authentication → Sign In / Providers → disable "Allow new
users to sign up"); otherwise anyone holding the anon key — which is public by
design — could create an account directly and bypass the invite check made
here.
"""

from dataclasses import dataclass

from app.db.client import anon_client, service_client


class AuthError(Exception):
    """Sign-up or sign-in was refused."""


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
        raise AuthError("Invalid email or password.")
    return Session(
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        user_id=user.id,
        email=user.email or "",
    )


def sign_in(email: str, password: str) -> Session:
    try:
        response = anon_client().auth.sign_in_with_password({"email": email, "password": password})
    except Exception as exc:  # supabase raises provider-specific errors
        raise AuthError("Invalid email or password.") from exc
    return _session_from_supabase(response)


def sign_up(email: str, password: str, invite_code: str) -> Session:
    """Redeem an invite, create the account, then sign in.

    The invite is redeemed first and atomically: `redeem_invite` locks the row
    and increments the use count in one statement, so two people racing on the
    last remaining use cannot both succeed.
    """
    if len(password) < 10:
        raise AuthError("Password must be at least 10 characters.")

    admin = service_client()

    redeemed = admin.rpc(
        "redeem_invite", {"p_code": invite_code.strip(), "p_email": email}
    ).execute()
    if not redeemed.data:
        raise AuthError("This invite code is not valid.")

    try:
        admin.auth.admin.create_user({"email": email, "password": password, "email_confirm": True})
    except Exception as exc:
        raise AuthError("Could not create the account. Is the email already registered?") from exc

    return sign_in(email, password)
