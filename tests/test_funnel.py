"""The funnel counts how far things got, not where they ended up."""

from app import funnel


def events(*pairs):
    return [{"application_id": app_id, "to_status": status} for app_id, status in pairs]


def by_key(bars):
    return {bar["key"]: bar["value"] for bar in bars}


def test_an_application_that_was_rejected_after_an_interview_still_had_one():
    """The whole point: counting current statuses would erase the interview."""
    bars = by_key(
        funnel.build(events(("a1", "submitted"), ("a1", "interview"), ("a1", "rejected")))
    )
    assert bars["saved"] == 1
    assert bars["sent"] == 1
    assert bars["interview"] == 1
    assert bars["offer"] == 0


def test_each_stage_includes_everything_that_went_further():
    bars = by_key(
        funnel.build(
            events(
                ("a1", "submitted"),
                ("a2", "submitted"),
                ("a2", "replied"),
                ("a3", "submitted"),
                ("a3", "interview"),
                ("a3", "offer"),
            )
        )
    )
    assert bars["sent"] == 3
    assert bars["replied"] == 2
    assert bars["interview"] == 1
    assert bars["offer"] == 1


def test_a_draft_is_saved_but_not_sent():
    bars = by_key(funnel.build(events(("a1", "draft"))))
    assert bars["saved"] == 1
    assert bars["sent"] == 0


def test_percentages_are_of_everything_saved():
    bars = funnel.build(events(("a1", "submitted"), ("a2", "draft")))
    percent = {bar["key"]: bar["percent"] for bar in bars}
    assert percent["saved"] == 100
    assert percent["sent"] == 50


def test_an_empty_history_produces_bars_rather_than_a_crash():
    bars = funnel.build([])
    assert [bar["value"] for bar in bars] == [0, 0, 0, 0, 0, 0]
    assert [bar["percent"] for bar in bars] == [0, 0, 0, 0, 0, 0]


def test_every_bar_carries_a_fill_so_the_template_never_prints_none():
    for bar in funnel.build(events(("a1", "submitted"))):
        assert bar["fill"].startswith("var(--")


# ---------------------------------------------------------------------------
# The headline numbers
# ---------------------------------------------------------------------------


def test_a_reply_followed_by_a_refusal_still_counts_as_a_reply():
    """The tiles and the flow chart sat side by side disagreeing about this."""
    numbers = funnel.headline(
        events(("a1", "submitted"), ("a1", "replied"), ("a1", "rejected")),
        {"a1": "rejected"},
    )
    assert numbers["sent"] == 1
    assert numbers["responded"] == 1
    assert numbers["response_rate"] == 100.0


def test_something_withdrawn_before_it_was_sent_was_not_sent():
    numbers = funnel.headline(events(("a1", "withdrawn")), {"a1": "withdrawn"})
    assert numbers["sent"] == 0
    assert numbers["total"] == 1


def test_drafts_do_not_drag_the_response_rate_down():
    numbers = funnel.headline(
        events(("a1", "submitted"), ("a1", "replied"), ("a2", "draft")),
        {"a1": "replied", "a2": "draft"},
    )
    assert numbers["sent"] == 1
    assert numbers["response_rate"] == 100.0


def test_an_acknowledgement_is_not_a_reply():
    numbers = funnel.headline(
        events(("a1", "submitted"), ("a1", "acknowledged")), {"a1": "acknowledged"}
    )
    assert numbers["responded"] == 0


def test_nothing_sent_leaves_the_rate_unstated_rather_than_zero():
    numbers = funnel.headline(events(("a1", "draft")), {"a1": "draft"})
    assert numbers["response_rate"] is None


def test_the_counts_by_status_describe_where_things_sit_now():
    numbers = funnel.headline(events(("a1", "submitted"), ("a1", "rejected")), {"a1": "rejected"})
    assert numbers["by_status"] == {"rejected": 1}
