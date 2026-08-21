"""Data access for arriving mail.

Separate from `repositories` because it is the one place that works without a
signed-in user: the webhook is called by a mail router, so everything here runs
as the service role and takes an explicit `user_id` that came from a forwarding
token, never from the request body.
"""

from datetime import UTC, datetime
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


def known_external_ids(user_id: str, external_ids: list[str]) -> set[str]:
    """Which of these adverts this account has already collected.

    Asked before inserting rather than relying on the unique index to reject
    duplicates: a digest repeats most of yesterday's list, so the common case
    is that almost everything is already known, and finding out by way of a
    failed insert per row is a poor way to learn it.
    """
    if not external_ids:
        return set()
    found = (
        service_client()
        .table("offers")
        .select("external_id")
        .eq("user_id", user_id)
        .in_("external_id", external_ids)
        .execute()
    )
    return {row["external_id"] for row in found.data or []}


def collected_this_month(user_id: str) -> int:
    """How many adverts have been collected for this account since the 1st.

    The free plan allows a taste of this and the paid one does not meter it;
    either way the number is counted here rather than inferred from the offers
    table as a whole, because a person who enters adverts by hand is not
    spending anything.
    """
    since = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    found = (
        service_client()
        .table("offers")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .not_.is_("collected_from", "null")
        .gte("created_at", since.isoformat())
        .execute()
    )
    return found.count or 0


def _company_for(user_id: str, name: str | None) -> str | None:
    """The account's company with this name, created if it is new.

    Runs as the service role because nobody is signed in when mail arrives, so
    `user_id` is passed explicitly and filtered on explicitly — the row level
    security that would normally do it is not in force here.
    """
    if not name or not name.strip():
        return None
    name = name.strip()
    admin = service_client()

    existing = (
        admin.table("companies")
        .select("id")
        .eq("user_id", user_id)
        .eq("name", name)
        .limit(1)
        .execute()
    )
    if existing.data:
        return existing.data[0]["id"]

    created = admin.table("companies").insert({"user_id": user_id, "name": name}).execute()
    return created.data[0]["id"] if created.data else None


def save_offers(user_id: str, inbound_id: str, offers, source: str | None, ceiling=None) -> int:
    """Store the adverts an alert listed. Returns how many were new.

    Everything lands as `status = 'new'`, which the schema has always meant as
    "arrived, not yet triaged" — the person decides what is worth applying to.
    Nothing here creates an application: an advert someone has not looked at is
    not a job they applied for, and counting it as one would put a number in
    the funnel that never happened.
    """
    seen = known_external_ids(user_id, [offer.external_id for offer in offers])
    fresh = [offer for offer in offers if offer.external_id not in seen]
    if not fresh:
        return 0

    if ceiling is not None:
        room = max(0, ceiling - collected_this_month(user_id))
        fresh = fresh[:room]
        if not fresh:
            return 0

    rows = []
    for offer in fresh:
        money = offer.salary
        rows.append(
            {
                "user_id": user_id,
                "company_id": _company_for(user_id, offer.company),
                "title": offer.title,
                "source": source or "other",
                "url": offer.url or None,
                "location": offer.location,
                "external_id": offer.external_id,
                "collected_from": inbound_id,
                "status": "new",
                "salary_min": money.minimum if money else None,
                "salary_max": money.maximum if money else None,
                "salary_currency": (money.currency if money else None) or "PLN",
                "salary_kind": money.kind if money else None,
                "salary_period": money.period if money else None,
            }
        )

    created = service_client().table("offers").insert(rows).execute()
    return len(created.data or [])


def profile_of(user_id: str) -> dict[str, Any] | None:
    """The account's plan row, for a worker that has no signed-in user."""
    found = (
        service_client()
        .table("profiles")
        .select("plan, plan_until")
        .eq("id", user_id)
        .limit(1)
        .execute()
    )
    return found.data[0] if found.data else None
