"""The search drawn as a flow.

A funnel of bars says how many reached each stage. It does not say where the
rest went, and where the rest went is the useful part: an application that
stopped at "sent" because nobody answered is a different problem from one that
stopped because you were rejected, and a different one again from a form you
never finished.

So each stage keeps what carried on and shows what fell out, labelled by what
actually happened to it.

Geometry is computed here rather than by a charting library. The page fetches
nothing from anywhere else, and a Sankey of five stages is a few hundred lines
of arithmetic — cheaper than a dependency and far cheaper than a CDN request
that tells someone else a job search is happening.
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

# Where an application rests when it stops. Anything not named here is still in
# motion and drops out as "waiting".
ENDINGS = ("rejected", "ghosted", "withdrawn", "draft", "blocked")

NODE_WIDTH = 13
GAP = 16  # between stacked nodes in a column
PAD_TOP = 26
PAD_BOTTOM = 34
# Labels sit to the right of their node, so the last column needs somewhere to
# put its own — without this the final stage is drawn and its name is not.
LABEL_SPACE = 132


@dataclass
class Node:
    key: str
    label_key: str
    value: int
    x: float
    y: float
    height: float
    carries_on: bool  # part of the main flow, or somewhere it stopped


@dataclass
class Link:
    path: str
    value: int
    carries_on: bool


@dataclass
class Chart:
    nodes: list[Node] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    width: int = 0
    height: int = 0
    total: int = 0

    @property
    def empty(self) -> bool:
        return self.total == 0


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


def build(
    events: list[dict[str, Any]],
    statuses: dict[str, str],
    *,
    width: int = 900,
    height: int = 330,
) -> Chart:
    """Turn the status history into nodes and ribbons ready to draw.

    `events` is every transition ever recorded; `statuses` is where each
    application sits today, which is what names the places it stopped.
    """
    furthest = furthest_reached(events)
    # An application with no events at all still exists and still counts.
    for application_id in statuses:
        furthest.setdefault(application_id, 0)

    total = len(furthest)
    chart = Chart(width=width, height=height, total=total)
    if total == 0:
        return chart

    columns = len(STAGES)
    column_gap = (width - NODE_WIDTH - LABEL_SPACE) / (columns - 1)
    usable = height - PAD_TOP - PAD_BOTTOM
    scale = usable / total

    # Whoever is still on the main line when the column is drawn.
    carrying = set(furthest)

    for index, (key, needed) in enumerate(STAGES):
        x = index * column_gap
        advanced = {a for a in carrying if furthest[a] >= needed}
        if not advanced and index > 0:
            break

        # The main node keeps the top of the column; anything that stopped
        # here hangs below it, which is what makes the losses read as losses.
        main = Node(
            key=key,
            label_key=f"flow.{key}",
            value=len(advanced),
            x=x,
            y=PAD_TOP,
            height=max(len(advanced) * scale, 2),
            carries_on=True,
        )
        chart.nodes.append(main)

        if index > 0:
            previous = chart.nodes[_previous_main(chart.nodes)]
            chart.links.append(
                Link(
                    path=_ribbon(
                        previous.x + NODE_WIDTH,
                        previous.y,
                        x,
                        main.y,
                        main.height,
                    ),
                    value=main.value,
                    carries_on=True,
                )
            )

        if index + 1 >= columns:
            break

        # Everything that reached this stage and went no further, named by
        # where it came to rest.
        _, next_needed = STAGES[index + 1]
        stalled = [a for a in advanced if furthest[a] < next_needed]
        by_ending: dict[str, list[str]] = {}
        for application_id in stalled:
            ending = statuses.get(application_id, "")
            ending = ending if ending in ENDINGS else "waiting"
            by_ending.setdefault(ending, []).append(application_id)

        source_y = main.y + max(len(advanced) - len(stalled), 0) * scale
        target_y = PAD_TOP + max(len(advanced) - len(stalled), 0) * scale + GAP

        for ending, group in sorted(by_ending.items(), key=lambda pair: -len(pair[1])):
            thickness = max(len(group) * scale, 2)
            leaf = Node(
                key=f"{key}-{ending}",
                label_key=f"flow.end.{ending}",
                value=len(group),
                x=x + column_gap,
                y=target_y,
                height=thickness,
                carries_on=False,
            )
            chart.nodes.append(leaf)
            chart.links.append(
                Link(
                    path=_ribbon(main.x + NODE_WIDTH, source_y, leaf.x, leaf.y, thickness),
                    value=len(group),
                    carries_on=False,
                )
            )
            source_y += thickness
            target_y += thickness + GAP

        carrying = advanced - set(stalled)
        if not carrying:
            break

    return chart


def _previous_main(nodes: list[Node]) -> int:
    """The index of the main node before the one just appended."""
    for index in range(len(nodes) - 2, -1, -1):
        if nodes[index].carries_on:
            return index
    return 0
