"""What an account is allowed to do.

One module, so that "may this account do that" has a single answer. A boundary
checked in twenty places is a boundary enforced in nineteen.

This is the application's copy of the rule. The database holds its own — the
CV limit is a trigger, and the plan column cannot be written by the user at all
— because the client can reach PostgREST directly and a check that lives only
in Python is a check that can be walked around.

Where the line sits and why: docs/PRICING.md.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

FREE = "free"
PLUS = "plus"

# Things an account can be allowed to do. Only `cv_versions` is enforceable
# today; the rest name features that are still to be built, and are listed here
# so the gate exists before the call sites do.
CV_VERSIONS = "cv_versions"
OFFERS_COLLECTED = "offers_collected"  # per month, from forwarded mail
REPLY_MATCHING = "reply_matching"
REMINDERS = "reminders"
STATS_BREAKDOWN = "stats_breakdown"

UNLIMITED = None


@dataclass(frozen=True)
class Plan:
    name: str
    # None means no ceiling. Zero means the feature is off entirely.
    limits: dict[str, int | None]

    def limit(self, capability: str) -> int | None:
        return self.limits.get(capability, 0)

    def allows(self, capability: str, current: int = 0) -> bool:
        ceiling = self.limit(capability)
        if ceiling is UNLIMITED:
            return True
        return current < ceiling


PLANS = {
    FREE: Plan(
        name=FREE,
        limits={
            CV_VERSIONS: 2,
            OFFERS_COLLECTED: 10,
            REPLY_MATCHING: 0,
            REMINDERS: 0,
            STATS_BREAKDOWN: 0,
        },
    ),
    PLUS: Plan(
        name=PLUS,
        limits={
            CV_VERSIONS: UNLIMITED,
            OFFERS_COLLECTED: UNLIMITED,
            REPLY_MATCHING: UNLIMITED,
            REMINDERS: UNLIMITED,
            STATS_BREAKDOWN: UNLIMITED,
        },
    ),
}


def for_profile(profile: dict[str, Any] | None) -> Plan:
    """The plan in force for this account, right now.

    A lapsed plan is the free plan: the automation stops, and nothing else
    changes. Everything already recorded stays readable, editable and
    exportable — see docs/PRICING.md.
    """
    profile = profile or {}
    name = profile.get("plan") or FREE

    until = profile.get("plan_until")
    if name != FREE and until and _passed(until):
        return PLANS[FREE]

    return PLANS.get(name, PLANS[FREE])


def _passed(moment: str) -> bool:
    try:
        expires = datetime.fromisoformat(moment.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        # An unreadable date should not silently hand out a paid plan.
        return True
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    return expires <= datetime.now(UTC)
