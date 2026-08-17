"""The funnel: how far applications actually got.

Read from the status history rather than from current statuses. An application
that reached an interview and was then rejected still reached an interview —
counting only where things sit today would quietly erase every stage that did
not end well, which is most of them.

Pure functions over event rows, so the arithmetic can be checked without a
database.
"""

from typing import Any

# How far each status counts as having got. Statuses that end an application
# without advancing it — rejected, ghosted, withdrawn — carry no rank: they say
# where it stopped, not how far it went.
RANK = {
    "draft": 0,
    "blocked": 0,
    "submitted": 1,
    "acknowledged": 2,
    "replied": 3,
    "interview": 4,
    "offer": 5,
}

# The bars, in order, with the rank each one needs.
STAGES = [
    ("saved", 0),
    ("sent", 1),
    ("acknowledged", 2),
    ("replied", 3),
    ("interview", 4),
    ("offer", 5),
]

# Pale to bright as the stage gets rarer — the same accent, turned up.
FILLS = [
    "var(--n-700)",
    "var(--a-700)",
    "var(--a-600)",
    "var(--a-500)",
    "var(--accent)",
    "var(--accent)",
]


def build(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Turn status events into the bars the dashboard draws."""
    furthest: dict[str, int] = {}
    for event in events:
        application_id = event.get("application_id")
        if not application_id:
            continue
        rank = RANK.get(event.get("to_status") or "", 0)
        furthest[application_id] = max(furthest.get(application_id, 0), rank)

    total = len(furthest)
    bars = []
    for index, (key, needed) in enumerate(STAGES):
        value = sum(1 for rank in furthest.values() if rank >= needed)
        bars.append(
            {
                "key": key,
                "value": value,
                "percent": round(100 * value / total) if total else 0,
                "fill": FILLS[index],
            }
        )
    return bars
