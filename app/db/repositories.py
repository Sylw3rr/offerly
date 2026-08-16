"""Data access.

Every function takes the signed-in user's access token and goes through
`user_client`, so row level security applies to each query. `user_id` is still
written on insert because the policies check it — the database is the guard,
these values are what it checks against.
"""

from datetime import UTC, datetime
from typing import Any

from app.db.client import user_client

# Statuses that mean the application is finished, one way or another.
TERMINAL_STATUSES = {"offer", "rejected", "withdrawn"}

# Statuses that count as "the employer engaged".
RESPONDED_STATUSES = {"replied", "interview", "offer"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


# ---------------------------------------------------------------------------
# Companies
# ---------------------------------------------------------------------------


def find_or_create_company(token: str, user_id: str, name: str) -> str:
    """Return the id of the user's company with this name, creating it if new."""
    client = user_client(token)
    name = name.strip()

    existing = client.table("companies").select("id").eq("name", name).limit(1).execute()
    if existing.data:
        return existing.data[0]["id"]

    created = client.table("companies").insert({"user_id": user_id, "name": name}).execute()
    return created.data[0]["id"]


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


def list_documents(token: str) -> list[dict[str, Any]]:
    client = user_client(token)
    result = (
        client.table("documents")
        .select("id, label, kind")
        .eq("is_active", True)
        .order("label")
        .execute()
    )
    return result.data or []


def create_document(token: str, user_id: str, label: str, kind: str = "cv") -> str:
    client = user_client(token)
    created = (
        client.table("documents")
        .insert({"user_id": user_id, "label": label.strip(), "kind": kind})
        .execute()
    )
    return created.data[0]["id"]


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------


def list_applications(token: str, status: str | None = None) -> list[dict[str, Any]]:
    """Applications with their offer, company and CV joined in."""
    client = user_client(token)
    query = client.table("applications").select(
        "id, status, submitted_at, declared_salary, declared_salary_kind,"
        "declared_salary_period, blocked_reason, notes,"
        "offers(id, title, source, url, location, mode, level, expires_at,"
        "companies(id, name)),"
        "documents!applications_cv_document_id_fkey(id, label)"
    )
    if status:
        query = query.eq("status", status)
    result = query.order("created_at", desc=True).execute()
    return result.data or []


def get_application(token: str, application_id: str) -> dict[str, Any] | None:
    client = user_client(token)
    result = (
        client.table("applications")
        .select(
            "*, offers(*, companies(id, name)),"
            "documents!applications_cv_document_id_fkey(id, label)"
        )
        .eq("id", application_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def create_application(
    token: str,
    user_id: str,
    *,
    company_name: str,
    title: str,
    source: str,
    url: str | None,
    location: str | None,
    mode: str | None,
    level: str | None,
    expires_at: str | None,
    cv_document_id: str | None,
    declared_salary: float | None,
    declared_salary_kind: str | None,
    declared_salary_period: str | None,
    declared_contract: str | None,
    status: str,
    blocked_reason: str | None,
    notes: str | None,
) -> str:
    """Create the offer and the application together.

    The common case is recording something already sent, so both rows are
    written in one step rather than making the user create an offer first.
    """
    client = user_client(token)
    company_id = find_or_create_company(token, user_id, company_name)

    offer = (
        client.table("offers")
        .insert(
            {
                "user_id": user_id,
                "company_id": company_id,
                "title": title.strip(),
                "source": source,
                "url": url or None,
                "location": location or None,
                "mode": mode or None,
                "level": level or None,
                "expires_at": expires_at or None,
                "status": "applied",
            }
        )
        .execute()
    )
    offer_id = offer.data[0]["id"]

    submitted_at = _now() if status not in {"draft", "blocked"} else None

    application = (
        client.table("applications")
        .insert(
            {
                "user_id": user_id,
                "offer_id": offer_id,
                "cv_document_id": cv_document_id or None,
                "status": status,
                "submitted_at": submitted_at,
                "declared_salary": declared_salary,
                "declared_salary_kind": declared_salary_kind or None,
                "declared_salary_period": declared_salary_period or None,
                "declared_contract": declared_contract or None,
                "blocked_reason": blocked_reason or None,
                "notes": notes or None,
            }
        )
        .execute()
    )
    application_id = application.data[0]["id"]

    _record_status(client, user_id, application_id, None, status, "manual", None)
    return application_id


def change_status(
    token: str,
    user_id: str,
    application_id: str,
    new_status: str,
    note: str | None = None,
) -> None:
    """Move an application to a new status and append to its history."""
    client = user_client(token)

    current = (
        client.table("applications")
        .select("status, submitted_at")
        .eq("id", application_id)
        .limit(1)
        .execute()
    )
    if not current.data:
        raise ValueError("Application not found")

    old_status = current.data[0]["status"]
    if old_status == new_status:
        return

    patch: dict[str, Any] = {"status": new_status}
    # Stamp the send date the first time it actually goes out.
    if new_status == "submitted" and not current.data[0]["submitted_at"]:
        patch["submitted_at"] = _now()

    client.table("applications").update(patch).eq("id", application_id).execute()
    _record_status(client, user_id, application_id, old_status, new_status, "manual", note)


def _record_status(
    client,
    user_id: str,
    application_id: str,
    from_status: str | None,
    to_status: str,
    source: str,
    note: str | None,
) -> None:
    client.table("status_events").insert(
        {
            "user_id": user_id,
            "application_id": application_id,
            "from_status": from_status,
            "to_status": to_status,
            "source": source,
            "note": note,
        }
    ).execute()


def status_history(token: str, application_id: str) -> list[dict[str, Any]]:
    client = user_client(token)
    result = (
        client.table("status_events")
        .select("from_status, to_status, source, note, created_at")
        .eq("application_id", application_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


def funnel_stats(token: str) -> dict[str, Any]:
    """Counts per status, plus the response rate.

    Response rate deliberately counts only applications that were actually
    sent — drafts and blocked ones would otherwise depress a number meant to
    say something about the applications, not the backlog.
    """
    client = user_client(token)
    result = client.table("applications").select("status, cv_document_id").execute()
    rows = result.data or []

    by_status: dict[str, int] = {}
    for row in rows:
        by_status[row["status"]] = by_status.get(row["status"], 0) + 1

    sent = [r for r in rows if r["status"] not in {"draft", "blocked"}]
    responded = [r for r in sent if r["status"] in RESPONDED_STATUSES]

    return {
        "total": len(rows),
        "sent": len(sent),
        "responded": len(responded),
        "response_rate": round(100 * len(responded) / len(sent), 1) if sent else None,
        "by_status": by_status,
    }
