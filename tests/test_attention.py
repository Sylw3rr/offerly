"""The rules that decide what gets chased, tested without a database."""

from datetime import date

from app import attention

TODAY = date(2026, 8, 16)


def row(
    application_id="a1",
    status="submitted",
    submitted_at=None,
    blocked_reason=None,
    expires_at=None,
    company="Acme",
    title="Support specialist",
):
    return {
        "id": application_id,
        "status": status,
        "submitted_at": submitted_at,
        "blocked_reason": blocked_reason,
        "offers": {
            "title": title,
            "expires_at": expires_at,
            "companies": {"name": company},
        },
    }


def collect(*rows, ghost_after_days=21):
    return attention.collect(list(rows), today=TODAY, ghost_after_days=ghost_after_days)


def test_silence_counts_from_the_send_date():
    items = collect(row(submitted_at="2026-07-20T09:00:00+00:00"))
    assert [i.kind for i in items] == ["silent"]
    assert "27 days" in items[0].message


def test_recent_application_is_not_chased_yet():
    assert collect(row(submitted_at="2026-08-10T09:00:00+00:00")) == []


def test_ghost_window_is_the_users_own_setting():
    recent = row(submitted_at="2026-08-10T09:00:00+00:00")
    assert collect(recent, ghost_after_days=5) != []


def test_draft_with_a_closing_date_is_flagged_before_it_closes():
    items = collect(row(status="draft", expires_at="2026-08-18"))
    assert items[0].kind == "closing"
    assert items[0].message == "Closes in 2 days"


def test_distant_closing_date_is_left_alone():
    assert collect(row(status="draft", expires_at="2026-10-01")) == []


def test_offer_that_closed_before_it_was_sent_is_the_loudest_item():
    missed = row("a1", status="draft", expires_at="2026-08-10", company="Zeta")
    blocked = row("a2", status="blocked", blocked_reason="External form", company="Acme")
    items = collect(missed, blocked)
    assert [i.kind for i in items] == ["missed", "blocked"]
    assert "6 days ago" in items[0].message


def test_blocked_application_says_what_is_blocking_it():
    items = collect(row(status="blocked", blocked_reason="Upload the CV by hand"))
    assert items[0].message == "Upload the CV by hand"


def test_blocked_without_a_reason_still_appears():
    items = collect(row(status="blocked"))
    assert items[0].kind == "blocked"


def test_one_item_per_application_even_when_two_rules_match():
    """Blocked *and* about to close: say the thing with the deadline on it."""
    items = collect(row(status="blocked", blocked_reason="Phone call", expires_at="2026-08-17"))
    assert len(items) == 1
    assert items[0].kind == "closing"
    assert items[0].status == "blocked"  # the badge still shows the rest


def test_finished_applications_never_appear():
    for status in ("offer", "rejected", "withdrawn", "ghosted"):
        assert status not in attention.RELEVANT_STATUSES


def test_a_missing_offer_or_company_does_not_crash_the_list():
    orphan = {"id": "a1", "status": "blocked", "offers": None}
    items = collect(orphan)
    assert items[0].company == "—"


def test_singular_day_reads_as_a_day():
    items = collect(row(status="draft", expires_at="2026-08-17"))
    assert items[0].message == "Closes in 1 day"
