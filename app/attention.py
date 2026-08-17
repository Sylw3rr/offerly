"""What needs the user's attention today.

A job search fails quietly: an offer closes while the application is still a
draft, an employer never answers and the thread is forgotten, an external form
is left half-done. This module turns the registry into a short list of things
worth doing, ordered by how soon they stop being possible.

The logic is pure — rows and a date in, items out — so it can be tested without
a database, and so the rules are readable in one place rather than spread over a
query and a template.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

# The ball is with the employer. Silence here is what eventually becomes a
# ghosting, so these are the applications worth chasing.
WAITING_STATUSES = frozenset({"submitted", "acknowledged"})

# The ball is with the user: nothing has been sent yet.
PENDING_STATUSES = frozenset({"draft", "blocked"})

# Statuses worth loading at all. Terminal ones need no nudge.
RELEVANT_STATUSES = WAITING_STATUSES | PENDING_STATUSES

# How far ahead a closing date starts to matter.
CLOSING_SOON_DAYS = 7

# Lower sorts first: a deadline that has passed outranks one approaching,
# which outranks silence, which outranks a task with no clock on it.
_PRIORITY = {"missed": 0, "closing": 1, "silent": 2, "blocked": 3}


@dataclass(frozen=True)
class Item:
    """One nudge: what it is about, and how long the clock has been running.

    The wording is deliberately not built here. This module knows a deadline
    passed six days ago; it does not know which language the reader wants that
    in, and a sentence assembled in Python is a sentence no catalogue can
    translate.
    """

    application_id: str
    company: str
    title: str
    status: str
    kind: str  # missed | closing | silent | blocked
    days: int | None = None
    text: str | None = None  # the user's own words, for a blocked application

    @property
    def priority(self) -> int:
        return _PRIORITY[self.kind]

    def message(self, t) -> str:
        """Phrase the nudge using the caller's catalogue."""
        if self.kind == "blocked":
            return self.text or t("attention.blocked_default")
        if self.kind == "closing" and self.days == 0:
            return t("attention.closing_today")

        count = self.days or 0
        days = t("days.one") if count == 1 else t("days.many", days=count)
        return t(f"attention.{self.kind}", days=days)


def collect(
    rows: list[dict[str, Any]],
    *,
    today: date,
    ghost_after_days: int,
) -> list[Item]:
    """Build the attention list from open applications.

    At most one item per application: an application that is both blocked and
    about to close should say the urgent thing, not both. The status badge is
    rendered alongside, so nothing is actually hidden.
    """
    items: list[Item] = []
    for row in rows:
        candidates = _candidates(row, today=today, ghost_after_days=ghost_after_days)
        if candidates:
            items.append(min(candidates, key=lambda item: item.priority))

    items.sort(key=lambda item: (item.priority, item.company.lower()))
    return items


def _candidates(row: dict[str, Any], *, today: date, ghost_after_days: int) -> list[Item]:
    offer = row.get("offers") or {}
    company = (offer.get("companies") or {}).get("name") or "—"
    status = row.get("status") or ""

    def item(kind: str, days: int | None = None, text: str | None = None) -> Item:
        return Item(
            application_id=row["id"],
            company=company,
            title=offer.get("title") or "—",
            status=status,
            kind=kind,
            days=days,
            text=text,
        )

    found: list[Item] = []

    if status in PENDING_STATUSES:
        closes = _as_date(offer.get("expires_at"))
        if closes is not None:
            days_left = (closes - today).days
            if days_left < 0:
                found.append(item("missed", days=-days_left))
            elif days_left <= CLOSING_SOON_DAYS:
                found.append(item("closing", days=days_left))

    if status == "blocked":
        found.append(item("blocked", text=row.get("blocked_reason")))

    if status in WAITING_STATUSES:
        sent = _as_date(row.get("submitted_at"))
        if sent is not None:
            silent_for = (today - sent).days
            if silent_for >= ghost_after_days:
                found.append(item("silent", days=silent_for))

    return found


def _as_date(value: str | None) -> date | None:
    """Read a date out of a date or timestamp column, tolerating either."""
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None
