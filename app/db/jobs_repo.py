"""Data access for scheduled work.

Like `ingest_repo`, everything here runs as the service role: a cron job has no
signed-in user, so `user_id` is passed explicitly and filtered on explicitly
rather than being enforced by row level security.
"""

from datetime import UTC, datetime
from typing import Any

from app.attention import RELEVANT_STATUSES
from app.db.client import service_client


def accounts_to_remind() -> list[dict[str, Any]]:
    """Every account that might be owed a reminder.

    The address comes from `auth.users`, which is the only place it lives —
    `profiles` deliberately does not copy it, so there is one row to change when
    somebody changes their email.
    """
    admin = service_client()
    profiles = (
        admin.table("profiles")
        .select("id, display_name, ghost_after_days, plan, plan_until, reminders_enabled, lang")
        .eq("reminders_enabled", True)
        .execute()
    )
    accounts = []
    for row in profiles.data or []:
        user = admin.auth.admin.get_user_by_id(row["id"])
        email = getattr(getattr(user, "user", None), "email", None)
        accounts.append({**row, "email": email})
    return accounts


def open_applications_for(user_id: str) -> list[dict[str, Any]]:
    """The rows the attention list is built from, shaped as the dashboard has them."""
    result = (
        service_client()
        .table("applications")
        .select(
            "id, status, submitted_at, blocked_reason, offers(title, expires_at, companies(name))"
        )
        .eq("user_id", user_id)
        .in_("status", sorted(RELEVANT_STATUSES))
        .execute()
    )
    return result.data or []


def reasons_already_sent(user_id: str) -> set[tuple[str, str]]:
    """What this account has been mailed about, as (application, reason)."""
    result = (
        service_client()
        .table("reminders")
        .select("application_id, kind")
        .eq("user_id", user_id)
        .not_.is_("sent_at", "null")
        .execute()
    )
    return {(row["application_id"], row["kind"]) for row in result.data or [] if row["kind"]}


def record_nudge(user_id: str, application_id: str, kind: str) -> bool:
    """Write down that this reason is being sent. False if it already was.

    The unique index added in 0009 is what makes this safe: two copies of the
    job racing each other both call this, and exactly one insert survives.
    """
    now = datetime.now(UTC).isoformat()
    try:
        service_client().table("reminders").insert(
            {
                "user_id": user_id,
                "application_id": application_id,
                "kind": kind,
                "due_at": now,
                "sent_at": now,
                "title": kind,
            }
        ).execute()
    except Exception:
        # A duplicate key is the index doing its job, not a failure.
        return False
    return True
