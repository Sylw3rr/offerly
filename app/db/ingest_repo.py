"""Data access for arriving mail.

Separate from `repositories` because it is the one place that works without a
signed-in user: the webhook is called by a mail router, so everything here runs
as the service role and takes an explicit `user_id` that came from a forwarding
token, never from the request body.
"""

from typing import Any

from app.db.client import service_client
from app.ingest.matching import Match
from app.ingest.reading import Message, Reading


def owner_of(token: str) -> str | None:
    """Whose forwarding address this is, or None if it belongs to nobody."""
    if not token:
        return None
    found = (
        service_client().table("profiles").select("id").eq("ingest_token", token).limit(1).execute()
    )
    return found.data[0]["id"] if found.data else None


def already_seen(user_id: str, message_id: str) -> bool:
    """Whether this exact message has arrived before.

    Forwarding rules loop and webhooks retry; without this, one refusal could
    move an application to `rejected` twice and write the history twice with it.
    """
    if not message_id:
        return False
    found = (
        service_client()
        .table("inbound_emails")
        .select("id")
        .eq("user_id", user_id)
        .eq("message_id", message_id)
        .limit(1)
        .execute()
    )
    return bool(found.data)


def open_applications_for(user_id: str) -> list[dict[str, Any]]:
    """Applications a reply could plausibly be about, with their companies."""
    result = (
        service_client()
        .table("applications")
        .select("id, status, offers(title, companies(name, email_domain))")
        .eq("user_id", user_id)
        .execute()
    )
    return result.data or []


def store(user_id: str, message: Message, reading: Reading, match: Match | None) -> str:
    """Keep the message whatever became of it.

    Everything is kept, including what could not be placed: an inbox that
    silently drops what it does not understand teaches nobody anything, least
    of all us.
    """
    created = (
        service_client()
        .table("inbound_emails")
        .insert(
            {
                "user_id": user_id,
                "message_id": message.message_id or None,
                "from_address": message.from_address,
                "from_domain": message.from_domain or None,
                "subject": message.subject or None,
                "body": message.body or None,
                "kind": reading.kind,
                "application_id": match.application_id if match else None,
            }
        )
        .execute()
    )
    return created.data[0]["id"]


def advance(user_id: str, application_id: str, status: str, subject: str) -> None:
    """Move an application because an employer said so.

    The history records that this came from an email rather than from a person
    — `status_events.source` has had `email_match` waiting for it since 0001 —
    so anything moved automatically can be told apart later.
    """
    admin = service_client()
    current = (
        admin.table("applications").select("status").eq("id", application_id).limit(1).execute()
    )
    if not current.data:
        return

    previous = current.data[0]["status"]
    if previous == status:
        return

    admin.table("applications").update({"status": status}).eq("id", application_id).execute()
    admin.table("status_events").insert(
        {
            "user_id": user_id,
            "application_id": application_id,
            "from_status": previous,
            "to_status": status,
            "source": "email_match",
            "note": subject[:200] if subject else None,
        }
    ).execute()
