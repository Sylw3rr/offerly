"""The search drawn as a flow.

A funnel of bars says how many reached each stage. It does not say where the
rest went, and where the rest went is the useful part: an application that
stopped at "sent" because nobody answered is a different problem from one that
stopped because you were rejected, and different again from a form you never
finished.

So each stage keeps what carried on and branches off what fell out, labelled by
what actually happened to it.

Geometry is computed here rather than by a charting library. The page fetches
nothing from anywhere else, and a Sankey of five stages is arithmetic — cheaper
than a dependency, and far cheaper than a request that tells someone else a job
search is happening. It also means the layout is testable without a browser.
"""

from dataclasses import dataclass, field
from typing import Any

from app.funnel import RANK

# The stages the eye follows, left to right, with the rank each one needs.
# `acknowledged` is deliberately not a stage: an automated "we got it" is not
# an answer, so those applications sit in "sent" until a human replies.
STAGES = [
    ("saved", 0),
    ("sent", 1),
    ("replied", 3),
    ("interview", 4),
    ("offer", 5),
]

# Where an application rests when it stops. Anything else is still in motion
# and comes to rest as "waiting".
ENDINGS = ("rejected", "ghosted", "withdrawn", "draft", "blocked")

# Six endings would need six hues, and only a few categorical hues survive the
# colourblind-separation check together — so endings are coloured by family and
# named by their own label. Colour groups, text specifies; nothing here is
# distinguished by colour alone.
FAMILIES = {
    "waiting": "silence",
    "ghosted": "silence",
    "rejected": "refused",
    "draft": "stopped",
    "blocked": "stopped",
    "withdrawn": "stopped",
}

NODE_WIDTH = 13
GAP = 24  # between stacked bands in a column
PAD_TOP = 30
PAD_BOTTOM = 22
# Labels sit to the right of their node, so the last column needs somewhere to
# put its own — without this the final stage is drawn and its name is not.
LABEL_SPACE = 132
# A band thin enough to vanish is worse than one drawn slightly too thick.
MIN_BAND = 3.0


@dataclass
class Node:
    key: str
    label_key: str
    value: int
    x: float
    y: float
    height: float
    family: str  # spine | silence | refused | stopped
    heading: bool  # a stage name above its column, or a label beside its band

    @property
    def label_y(self) -> float:
        """Stage names sit above the column; branch names sit beside the band.

        Putting a branch's name level with the band it belongs to is what makes
        it obvious which ribbon is being named.
        """
        return self.y - 11 if self.heading else self.y + self.height / 2


@dataclass
class Link:
    path: str
    value: int
    family: str


@dataclass
class Chart:
    nodes: list[Node] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    width: int = 0
    height: float = 0
    total: int = 0

    @property
    def empty(self) -> bool:
        return self.total == 0

    @property
    def families(self) -> list[str]:
        """Which families are on screen, in the order met — for the legend."""
        seen: list[str] = []
        for node in self.nodes:
            if node.family not in seen:
                seen.append(node.family)
        return seen


def furthest_reached(events: list[dict[str, Any]]) -> dict[str, int]:
    """How far each application ever got, from its whole history."""
    furthest: dict[str, int] = {}
    for event in events:
        application_id = event.get("application_id")
        if not application_id:
            continue
        rank = RANK.get(event.get("to_status") or "", 0)
        furthest[application_id] = max(furthest.get(application_id, 0), rank)
    return furthest


def _ribbon(x0: float, y0: float, x1: float, y1: float, thickness: float) -> str:
    """A band from one node's edge to another's, curved through the middle."""
    mid = (x0 + x1) / 2
    return (
        f"M{x0:.1f},{y0:.1f} "
        f"C{mid:.1f},{y0:.1f} {mid:.1f},{y1:.1f} {x1:.1f},{y1:.1f} "
        f"L{x1:.1f},{y1 + thickness:.1f} "
        f"C{mid:.1f},{y1 + thickness:.1f} {mid:.1f},{y0 + thickness:.1f} "
        f"{x0:.1f},{y0 + thickness:.1f} Z"
    )


def _plan(
    events: list[dict[str, Any]], statuses: dict[str, str]
) -> tuple[list[tuple[str, int]], dict[int, list[tuple[str, int]]], int]:
    """Count everything before drawing anything.

    Two passes rather than one, so the scale can allow for the space the gaps
    between bands take. Doing it in a single pass is what pushed the lower bands
    off the bottom of the canvas.
    """
    furthest = furthest_reached(events)
    for application_id in statuses:
        furthest.setdefault(application_id, 0)

    total = len(furthest)
    stages: list[tuple[str, int]] = []
    drops: dict[int, list[tuple[str, int]]] = {}
    carrying = set(furthest)

    for index, (key, needed) in enumerate(STAGES):
        advanced = {a for a in carrying if furthest[a] >= needed}
        if not advanced and index > 0:
            break
        stages.append((key, len(advanced)))

        if index + 1 >= len(STAGES):
            break

        _, next_needed = STAGES[index + 1]
        stalled = [a for a in advanced if furthest[a] < next_needed]
        grouped: dict[str, int] = {}
        for application_id in stalled:
            ending = statuses.get(application_id, "")
            ending = ending if ending in ENDINGS else "waiting"
            grouped[ending] = grouped.get(ending, 0) + 1

        if grouped:
            drops[index] = sorted(grouped.items(), key=lambda pair: -pair[1])
        carrying = advanced - set(stalled)
        if not carrying:
            break

    return stages, drops, total


def build(
    events: list[dict[str, Any]],
    statuses: dict[str, str],
    *,
    width: int = 900,
    height: int = 360,
) -> Chart:
    """Turn the status history into nodes and ribbons ready to draw."""
    stages, drops, total = _plan(events, statuses)
    chart = Chart(width=width, height=height, total=total)
    if total == 0:
        return chart

    column_gap = (width - NODE_WIDTH - LABEL_SPACE) / (len(STAGES) - 1)
    # The deepest stack decides how much room the gaps need, so that the bands
    # still add up to the canvas once they are spaced apart.
    deepest = max((len(group) for group in drops.values()), default=0)
    usable = height - PAD_TOP - PAD_BOTTOM - deepest * GAP
    scale = max(usable, 40) / total

    previous: Node | None = None
    lowest = 0.0

    for index, (key, value) in enumerate(stages):
        x = index * column_gap
        main = Node(
            key=key,
            label_key=f"flow.{key}",
            value=value,
            x=x,
            y=PAD_TOP,
            height=max(value * scale, MIN_BAND),
            family="spine",
            heading=True,
        )
        chart.nodes.append(main)
        lowest = max(lowest, main.y + main.height)

        if previous is not None:
            chart.links.append(
                Link(
                    path=_ribbon(previous.x + NODE_WIDTH, previous.y, x, main.y, main.height),
                    value=value,
                    family="spine",
                )
            )

        leaving = sum(count for _, count in drops.get(index, []))
        source_y = main.y + max(value - leaving, 0) * scale
        target_y = PAD_TOP + max(value - leaving, 0) * scale + GAP

        for ending, count in drops.get(index, []):
            thickness = max(count * scale, MIN_BAND)
            family = FAMILIES.get(ending, "stopped")
            leaf = Node(
                key=f"{key}-{ending}",
                label_key=f"flow.end.{ending}",
                value=count,
                x=x + column_gap,
                y=target_y,
                height=thickness,
                family=family,
                heading=False,
            )
            chart.nodes.append(leaf)
            chart.links.append(
                Link(
                    path=_ribbon(main.x + NODE_WIDTH, source_y, leaf.x, leaf.y, thickness),
                    value=count,
                    family=family,
                )
            )
            source_y += thickness
            target_y += thickness + GAP
            lowest = max(lowest, leaf.y + leaf.height)

        previous = main

    # Whatever the content came to, the frame contains it. Clamping a thin band
    # to a readable minimum can push the stack past the nominal height, and
    # growing the canvas beats clipping the answer.
    chart.height = max(height, lowest + PAD_BOTTOM)
    return chart
