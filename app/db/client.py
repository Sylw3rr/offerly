"""Supabase client construction.

Three ways to reach the database, deliberately kept apart:

- `anon_client()`    — unauthenticated; used for sign-in only.
- `user_client(tok)` — acts as the signed-in user, so row level security applies.
- `service_client()` — bypasses row level security. Server-side only.

Confining these to one module keeps the number of places that can hold the
service key small enough to audit by eye.
"""

from functools import lru_cache

from app.config import get_settings
from supabase import Client, create_client


@lru_cache
def anon_client() -> Client:
    """Shared, unauthenticated. Only for calls that pass their token explicitly.

    This one is cached, so it is global to the process. Anything that signs a
    session *into* the client — signing in, recovering a password — must use
    `new_anon_client` instead, or two visitors would be sharing one session
    store.
    """
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_anon_key)


def new_anon_client() -> Client:
    """An unauthenticated client of one's own, for flows that hold a session."""
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_anon_key)


def user_client(access_token: str) -> Client:
    """A client whose database calls run as the signed-in user.

    The access token is attached to PostgREST requests, so every policy is
    evaluated against that user. This is the client the application should
    use for anything touching user data.
    """
    settings = get_settings()
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    client.postgrest.auth(access_token)
    return client


@lru_cache
def service_client() -> Client:
    """A client that bypasses row level security.

    Only for operations that legitimately act across users: redeeming invite
    codes, creating accounts, scheduled maintenance. Never expose the
    underlying key, and never build one of these from request input.
    """
    settings = get_settings()
    if not settings.supabase_service_key:
        raise RuntimeError("SUPABASE_SERVICE_KEY is not configured")
    return create_client(settings.supabase_url, settings.supabase_service_key)
