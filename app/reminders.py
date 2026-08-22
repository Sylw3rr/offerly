"""What is worth an email, and what is worth only a mention on Monday.

Two different things, and the difference is the whole design:

- A **nudge** is sent when something has just become urgent. It goes out once
  per application per reason and never again. If someone ignores "this closes
  in three days", that is an answer, and repeating it daily is how a product
  gets filtered into a folder nobody opens.
- The **Monday summary** is the routine. It repeats by design, it lists
  everything currently waiting, and it is the only recurring mail Offerly
  sends.

Nothing here sends anything or touches a database. It takes the attention list
that already drives the dashboard, plus a record of what has gone out before,
and returns what should go out now — so the rules are testable without a
mailbox, and readable in one place instead of being spread across a query, a
scheduler and a template.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.attention import Item

# Reasons worth interrupting someone's day for. `blocked` is deliberately not
# among them: an application is blocked because the person marked it blocked,
# and mailing them about a thing they just typed is noise. It still appears in
# the Monday summary, where the point is the whole picture rather than news.
WORTH_A_MAIL = frozenset({"missed", "closing", "silent"})

MONDAY = 0

# How recently something has to have become urgent to be worth interrupting
# someone for. Three days rather than one so a scheduler that misses a night
# does not lose the nudge entirely.
#
# This exists because of what the first real run did: sixty applications, most
# of them silent for months, all crossed their threshold long ago, and every
# one of them produced a mail. The dedupe rule was right and still gave the
# wrong answer — it stops a thing being said twice, not sixty things being said
# at once. An application quiet for 122 days did not just become quiet, and the
# reader already knows. That belongs in Monday's list.
FRESH_FOR_DAYS = 3

# A backstop under the freshness rule, not a substitute for it. If some future
# kind gets the arithmetic wrong, the blast radius is four mails rather than a
# domain's reputation.
MOST_PER_RUN = 4


@dataclass(frozen=True)
class Nudge:
    """One thing to tell someone about, and the reason it is being told.

    The reason travels with it because that is the dedupe key: the same
    application can legitimately earn a second mail when a deadline it was
    merely approaching turns into one it has missed.
    """

    item: Item

    @property
    def key(self) -> tuple[str, str]:
        return (self.item.application_id, self.item.kind)


def became_urgent_days_ago(item: Item, ghost_after_days: int) -> int:
    """How long ago this crossed the line, in days.

    Each reason has its own line. Silence begins at the account's ghosting
    window, so an application quiet for 30 days with a 21-day window crossed it
    nine days ago. A missed deadline crossed on the day it passed. Something
    closing has not crossed anything — it is urgent now, and only stays that
    way for a week, so it cannot pile up.
    """
    days = item.days or 0
    if item.kind == "silent":
        # Not clamped at zero: a negative answer means it has not crossed at
        # all, and the caller's range check reads that as "not urgent" rather
        # than as "urgent this very moment".
        return days - ghost_after_days
    if item.kind == "missed":
        return days
    return 0


def nudges(
    items: list[Item], already_sent: set[tuple[str, str]], *, ghost_after_days: int = 21
) -> list[Nudge]:
    """The urgent items nobody has been told about yet, that only just became so.

    Ordered the way the attention list is ordered — soonest to stop being
    possible first — so the cap takes the least urgent end.
    """
    fresh = [
        Nudge(item)
        for item in items
        if item.kind in WORTH_A_MAIL
        and (item.application_id, item.kind) not in already_sent
        and 0 <= became_urgent_days_ago(item, ghost_after_days) <= FRESH_FOR_DAYS
    ]
    return fresh[:MOST_PER_RUN]


def is_summary_day(today: date) -> bool:
    """Monday, as the landing page promises."""
    return today.weekday() == MONDAY


def summary(items: list[Item]) -> list[Item]:
    """Everything currently waiting, for the weekly mail.

    Includes `blocked`, which no nudge covers: a form left half-finished in
    March is exactly the thing a weekly look is for.
    """
    return list(items)


def worth_sending(items: list[Item]) -> bool:
    """Whether there is anything to say at all.

    A summary that reports nothing is a summary people unsubscribe from. If the
    week is quiet, the week is quiet and no mail goes out.
    """
    return bool(items)
