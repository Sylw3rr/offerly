"""The flow chart: what carried on, and where the rest stopped."""

from app import sankey


def events(*pairs):
    return [{"application_id": app_id, "to_status": status} for app_id, status in pairs]


def nodes_by_key(chart):
    return {node.key: node for node in chart.nodes}


def test_an_empty_search_draws_nothing_rather_than_dividing_by_zero():
    chart = sankey.build([], {})
    assert chart.empty
    assert chart.nodes == []
    assert chart.links == []


def test_everything_starts_in_saved():
    chart = sankey.build(
        events(("a1", "draft"), ("a2", "submitted")), {"a1": "draft", "a2": "submitted"}
    )
    assert nodes_by_key(chart)["saved"].value == 2


def test_an_application_with_no_history_is_still_counted():
    """A row written straight into the table should not vanish from the chart."""
    chart = sankey.build([], {"a1": "draft"})
    assert nodes_by_key(chart)["saved"].value == 1


def test_what_never_went_out_branches_off_named_by_its_status():
    chart = sankey.build(
        events(("a1", "submitted"), ("a2", "draft"), ("a3", "blocked")),
        {"a1": "submitted", "a2": "draft", "a3": "blocked"},
    )
    keys = nodes_by_key(chart)
    assert keys["saved"].value == 3
    assert keys["sent"].value == 1
    assert keys["saved-draft"].value == 1
    assert keys["saved-blocked"].value == 1


def test_reaching_an_interview_counts_even_after_a_rejection():
    """The whole reason for reading the history rather than the current status."""
    chart = sankey.build(
        events(("a1", "submitted"), ("a1", "replied"), ("a1", "interview"), ("a1", "rejected")),
        {"a1": "rejected"},
    )
    keys = nodes_by_key(chart)
    assert keys["sent"].value == 1
    assert keys["replied"].value == 1
    assert keys["interview"].value == 1


def test_an_automated_acknowledgement_is_not_an_answer():
    chart = sankey.build(
        events(("a1", "submitted"), ("a1", "acknowledged")),
        {"a1": "acknowledged"},
    )
    keys = nodes_by_key(chart)
    assert keys["sent"].value == 1
    assert "replied" not in keys or keys["replied"].value == 0


def test_silence_is_told_apart_from_a_refusal():
    chart = sankey.build(
        events(("a1", "submitted"), ("a2", "submitted"), ("a2", "ghosted")),
        {"a1": "submitted", "a2": "ghosted"},
    )
    keys = nodes_by_key(chart)
    assert keys["sent-waiting"].value == 1
    assert keys["sent-ghosted"].value == 1


def test_every_ribbon_is_a_closed_path_the_browser_can_draw():
    chart = sankey.build(
        events(("a1", "submitted"), ("a1", "replied"), ("a2", "draft")),
        {"a1": "replied", "a2": "draft"},
    )
    assert chart.links
    for link in chart.links:
        assert link.path.startswith("M")
        assert link.path.endswith("Z")
        assert "C" in link.path


def test_the_last_column_leaves_room_for_its_own_label():
    """Drawing the final stage and then clipping its name off the edge is the
    same as not drawing it."""
    chart = sankey.build(
        events(("a1", "submitted"), ("a1", "replied"), ("a1", "interview"), ("a1", "offer")),
        {"a1": "offer"},
    )
    last = max(node.x for node in chart.nodes)
    assert last + sankey.NODE_WIDTH + sankey.LABEL_SPACE <= chart.width + 1


def test_nodes_stay_inside_the_canvas():
    chart = sankey.build(
        events(*[(f"a{i}", "submitted") for i in range(40)]),
        {f"a{i}": "submitted" for i in range(40)},
    )
    for node in chart.nodes:
        assert node.y >= 0
        assert node.y + node.height <= chart.height
        assert node.x + 13 <= chart.width


def test_a_stage_nobody_reached_ends_the_chart_rather_than_drawing_slivers():
    chart = sankey.build(events(("a1", "submitted")), {"a1": "submitted"})
    keys = nodes_by_key(chart)
    assert "interview" not in keys
    assert "offer" not in keys


def test_the_flow_that_carries_on_is_marked_apart_from_the_flow_that_stops():
    chart = sankey.build(
        events(("a1", "submitted"), ("a2", "draft")),
        {"a1": "submitted", "a2": "draft"},
    )
    assert any(link.family == "spine" for link in chart.links)
    assert any(link.family != "spine" for link in chart.links)


def test_endings_are_coloured_by_family_and_named_by_themselves():
    """Colour groups the outcome; the label says which one it is."""
    chart = sankey.build(
        events(("a1", "draft"), ("a2", "blocked"), ("a3", "submitted"), ("a3", "ghosted")),
        {"a1": "draft", "a2": "blocked", "a3": "ghosted"},
    )
    keys = nodes_by_key(chart)
    assert keys["saved-draft"].family == keys["saved-blocked"].family == "stopped"
    assert keys["saved-draft"].label_key != keys["saved-blocked"].label_key
    assert keys["sent-ghosted"].family == "silence"


def test_a_branch_label_sits_level_with_its_own_band():
    """The complaint that started this: a name floating above a stack does not
    say which ribbon it belongs to."""
    chart = sankey.build(events(("a1", "draft")), {"a1": "draft"})
    branch = nodes_by_key(chart)["saved-draft"]
    assert branch.label_y == branch.y + branch.height / 2


def test_stage_names_sit_above_their_column():
    chart = sankey.build(events(("a1", "submitted")), {"a1": "submitted"})
    stage = nodes_by_key(chart)["saved"]
    assert stage.label_y < stage.y


def test_deep_stacks_grow_the_canvas_rather_than_spilling_out_of_it():
    """Every ending at once: the bands plus the gaps between them must still
    fit inside the frame."""
    endings = ["rejected", "ghosted", "withdrawn", "draft", "blocked"]
    e, statuses = [], {}
    for ending in endings:
        for n in range(4):
            key = f"{ending}{n}"
            e += events((key, "submitted"), (key, ending))
            statuses[key] = ending
    chart = sankey.build(e, statuses)
    for node in chart.nodes:
        assert node.y + node.height <= chart.height, node.key


def test_the_legend_lists_only_the_families_actually_drawn():
    chart = sankey.build(events(("a1", "submitted")), {"a1": "submitted"})
    assert "refused" not in chart.families
