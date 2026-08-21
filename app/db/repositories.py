"""Data access.

Every function takes the signed-in user's access token and goes through
`user_client`, so row level security applies to each query. `user_id` is still
written on insert because the policies check it — the database is the guard,
these values are what it checks against.
"""

from datetime import UTC, datetime
from typing import Any

from app import funnel
from app.attention import RELEVANT_STATUSES
from app.db.client import user_client


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


class DocumentLimitReached(Exception):
    """The account is at its plan's ceiling for CV versions."""


def create_document(token: str, user_id: str, label: str, kind: str = "cv") -> str:
    """Add a CV version, unless the plan's ceiling has been reached.

    The database refuses this too — the limit is a trigger, because the client
    can reach PostgREST directly. Catching it here is about wording, not about
    enforcement.
    """
    client = user_client(token)
    try:
        created = (
            client.table("documents")
            .insert({"user_id": user_id, "label": label.strip(), "kind": kind})
            .execute()
        )
    except Exception as exc:
        if "document_limit_reached" in str(exc):
            raise DocumentLimitReached from exc
        raise
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
        "salary_min, salary_max, salary_currency, salary_kind, salary_period, contract,"
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


def _offer_payload(fields: dict[str, Any]) -> dict[str, Any]:
    """The offer's own columns, normalised the same way new or edited."""
    return {
        "title": fields["title"].strip(),
        "source": fields["source"],
        "url": fields["url"] or None,
        "location": fields["location"] or None,
        "mode": fields["mode"] or None,
        "level": fields["level"] or None,
        "expires_at": fields["expires_at"] or None,
        "salary_min": fields["salary_min"],
        "salary_max": fields["salary_max"],
        "salary_currency": (fields["salary_currency"] or "PLN").upper()[:3],
        "salary_kind": fields["salary_kind"] or None,
        "salary_period": fields["salary_period"] or None,
        "contract": fields["contract"] or None,
    }


def _application_payload(fields: dict[str, Any]) -> dict[str, Any]:
    """The application's own columns. Status is not among them — it moves only
    through `change_status`, so the history stays a true account."""
    return {
        "cv_document_id": fields["cv_document_id"] or None,
        "declared_salary": fields["declared_salary"],
        "declared_salary_kind": fields["declared_salary_kind"] or None,
        "declared_salary_period": fields["declared_salary_period"] or None,
        "declared_contract": fields["declared_contract"] or None,
        "blocked_reason": fields["blocked_reason"] or None,
        "notes": fields["notes"] or None,
    }


def create_application(token: str, user_id: str, *, status: str, **fields: Any) -> str:
    """Create the offer and the application together.

    The common case is recording something already sent, so both rows are
    written in one step rather than making the user create an offer first.
    """
    client = user_client(token)
    company_id = find_or_create_company(token, user_id, fields["company_name"])

    offer = (
        client.table("offers")
        .insert(
            {
                "user_id": user_id,
                "company_id": company_id,
                "status": "applied",
                **_offer_payload(fields),
            }
        )
        .execute()
    )
    offer_id = offer.data[0]["id"]

    # A given date wins: someone entering last month's applications needs them
    # dated last month, or every one of them looks unanswered at once.
    submitted_at = fields.get("submitted_at")
    if not submitted_at and status not in {"draft", "blocked"}:
        submitted_at = _now()

    application = (
        client.table("applications")
        .insert(
            {
                "user_id": user_id,
                "offer_id": offer_id,
                "status": status,
                "submitted_at": submitted_at,
                **_application_payload(fields),
            }
        )
        .execute()
    )
    application_id = application.data[0]["id"]

    _record_status(client, user_id, application_id, None, status, "manual", None)
    return application_id


def update_application(token: str, user_id: str, application_id: str, **fields: Any) -> None:
    """Correct the details of an application and the offer behind it.

    A typo in a company name is not an event in the search, so nothing is
    written to the history here. Status is untouched for the same reason.
    """
    client = user_client(token)

    current = (
        client.table("applications").select("offer_id").eq("id", application_id).limit(1).execute()
    )
    if not current.data:
        raise ValueError("Application not found")

    company_id = find_or_create_company(token, user_id, fields["company_name"])
    client.table("offers").update({"company_id": company_id, **_offer_payload(fields)}).eq(
        "id", current.data[0]["offer_id"]
    ).execute()

    client.table("applications").update(
        {"submitted_at": fields.get("submitted_at") or None, **_application_payload(fields)}
    ).eq("id", application_id).execute()


def set_offer_url(token: str, application_id: str, url: str | None) -> None:
    """Attach the advertisement to an application, or clear it.

    Its own function rather than a trip through the edit form: the link is the
    one detail people fill in later, standing at the page wondering where the
    offer was, and a whole form is too much ceremony for one paste.
    """
    client = user_client(token)
    current = (
        client.table("applications").select("offer_id").eq("id", application_id).limit(1).execute()
    )
    if not current.data:
        return
    client.table("offers").update({"url": url or None}).eq(
        "id", current.data[0]["offer_id"]
    ).execute()


def delete_application(token: str, application_id: str) -> None:
    """Remove an application, its offer and its history.

    Deleting the offer cascades to both, so nothing is left orphaned. The
    company row stays: it may be attached to other applications, and an empty
    company is harmless.
    """
    client = user_client(token)
    current = (
        client.table("applications").select("offer_id").eq("id", application_id).limit(1).execute()
    )
    if not current.data:
        return
    client.table("offers").delete().eq("id", current.data[0]["offer_id"]).execute()


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
# Profile
# ---------------------------------------------------------------------------

# Used when the profile row cannot be read; keep in step with the column
# default in 0001_initial_schema.sql.
DEFAULT_GHOST_AFTER_DAYS = 21


def get_profile(token: str) -> dict[str, Any]:
    """The signed-in user's settings row, with defaults if it is missing."""
    client = user_client(token)
    result = (
        client.table("profiles")
        .select("display_name, ghost_after_days, plan, plan_until, ingest_token")
        .limit(1)
        .execute()
    )
    if result.data:
        return result.data[0]
    return {
        "display_name": None,
        "ghost_after_days": DEFAULT_GHOST_AFTER_DAYS,
        "plan": "free",
        "plan_until": None,
        "ingest_token": None,
    }


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


def open_applications(token: str) -> list[dict[str, Any]]:
    """Applications still in play — the input to `app.attention`."""
    client = user_client(token)
    result = (
        client.table("applications")
        .select(
            "id, status, submitted_at, blocked_reason,offers(title, expires_at, companies(name))"
        )
        .in_("status", sorted(RELEVANT_STATUSES))
        .execute()
    )
    return result.data or []


def all_status_events(token: str) -> list[dict[str, Any]]:
    """Every transition, for the funnel. Two columns, so it stays cheap."""
    client = user_client(token)
    result = client.table("status_events").select("application_id, to_status").execute()
    return result.data or []


def current_statuses(token: str) -> dict[str, str]:
    """Where every application sits now, keyed by id."""
    client = user_client(token)
    result = client.table("applications").select("id, status").execute()
    return {row["id"]: row["status"] for row in (result.data or [])}


def last_moves(token: str) -> dict[str, str]:
    """When each application last changed status, newest first per application."""
    client = user_client(token)
    result = (
        client.table("status_events")
        .select("application_id, created_at")
        .order("created_at", desc=True)
        .execute()
    )
    moves: dict[str, str] = {}
    for row in result.data or []:
        moves.setdefault(row["application_id"], row["created_at"])
    return moves


def recent_events(token: str, limit: int = 8) -> list[dict[str, Any]]:
    """The last few status changes, across every application."""
    client = user_client(token)
    result = (
        client.table("status_events")
        .select(
            "from_status, to_status, source, note, created_at,"
            "applications(id, offers(title, companies(name)))"
        )
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


# ---------------------------------------------------------------------------
# The inbox — what arrived by mail
# ---------------------------------------------------------------------------


def list_inbound(token: str, limit: int = 60) -> list[dict[str, Any]]:
    """Arrived mail, newest first, with whatever it was matched to."""
    client = user_client(token)
    result = (
        client.table("inbound_emails")
        .select(
            "id, received_at, kind, from_address, from_domain, subject, body,"
            "handled_at, application_id,"
            "applications(id, status, offers(title, companies(name)))"
        )
        .order("received_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


def mark_inbound_handled(token: str, inbound_id: str) -> None:
    """Put a message aside without acting on it."""
    client = user_client(token)
    client.table("inbound_emails").update({"handled_at": _now()}).eq("id", inbound_id).execute()


def get_inbound(token: str, inbound_id: str) -> dict[str, Any] | None:
    client = user_client(token)
    result = (
        client.table("inbound_emails")
        .select("id, from_address, subject, body, application_id, handled_at")
        .eq("id", inbound_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


# ---------------------------------------------------------------------------
# Profile answers — the paste buffer for recruitment forms
# ---------------------------------------------------------------------------


def list_profile_answers(token: str) -> list[dict[str, Any]]:
    client = user_client(token)
    result = (
        client.table("profile_answers")
        .select("id, label, value, sort_order")
        .order("sort_order")
        .order("label")
        .execute()
    )
    return result.data or []


def create_profile_answer(token: str, user_id: str, label: str, value: str) -> str:
    """Add an answer, placing it after the existing ones."""
    client = user_client(token)
    last = (
        client.table("profile_answers")
        .select("sort_order")
        .order("sort_order", desc=True)
        .limit(1)
        .execute()
    )
    next_order = (last.data[0]["sort_order"] + 1) if last.data else 0

    created = (
        client.table("profile_answers")
        .insert(
            {
                "user_id": user_id,
                "label": label.strip(),
                "value": value.strip(),
                "sort_order": next_order,
            }
        )
        .execute()
    )
    return created.data[0]["id"]


def update_profile_answer(token: str, answer_id: str, label: str, value: str) -> None:
    client = user_client(token)
    client.table("profile_answers").update({"label": label.strip(), "value": value.strip()}).eq(
        "id", answer_id
    ).execute()


def delete_profile_answer(token: str, answer_id: str) -> None:
    client = user_client(token)
    client.table("profile_answers").delete().eq("id", answer_id).execute()


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


def funnel_stats(token: str) -> dict[str, Any]:
    """The headline numbers, counted from the status history.

    The arithmetic lives in `app.funnel` so the tiles, the funnel bars and the
    flow chart cannot drift apart. They did: counting by current status dropped
    every application that drew a reply and was then refused, which understated
    the one number this product exists to report.
    """
    return funnel.headline(all_status_events(token), current_statuses(token))


def offers_from_message(token: str, inbound_id: str) -> list[dict[str, Any]]:
    """The adverts one alert produced, newest board order preserved."""
    result = (
        user_client(token)
        .table("offers")
        .select(
            "id, title, url, location, status, salary_min, salary_max, "
            "salary_currency, salary_kind, salary_period, companies(name)"
        )
        .eq("collected_from", inbound_id)
        .order("created_at")
        .execute()
    )
    return result.data or []


def collected_offers(token: str, inbound_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    """Every collected advert for these messages, grouped by the message.

    One query for the whole page: the inbox lists up to sixty messages, and
    asking per message is how a list view becomes sixty round trips.
    """
    if not inbound_ids:
        return {}
    result = (
        user_client(token)
        .table("offers")
        .select(
            "id, title, url, location, status, collected_from, salary_min, salary_max, "
            "salary_currency, salary_kind, salary_period, companies(name)"
        )
        .in_("collected_from", inbound_ids)
        .order("created_at")
        .execute()
    )
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in result.data or []:
        grouped.setdefault(row["collected_from"], []).append(row)
    return grouped


def triage_offer(token: str, offer_id: str, keep: bool, reason: str | None = None) -> None:
    """Shortlist an advert or discard it.

    The two outcomes the schema has always named. Discarding keeps the row and
    the reason rather than deleting it: the same advert arrives again next
    week, and knowing it was already turned down is the point.
    """
    user_client(token).table("offers").update(
        {
            "status": "shortlisted" if keep else "discarded",
            "discard_reason": None if keep else (reason or None),
            "updated_at": _now(),
        }
    ).eq("id", offer_id).execute()
