"""The rules that decide what gets chased, tested without a database."""

from datetime import date

from app import attention
from app.i18n import translator

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


def english(item):
    return item.message(translator("en"))


def polish(item):
    return item.message(translator("pl"))


def test_silence_counts_from_the_send_date():
    items = collect(row(submitted_at="2026-07-20T09:00:00+00:00"))
    assert [i.kind for i in items] == ["silent"]
    assert items[0].days == 27


def test_recent_application_is_not_chased_yet():
    assert collect(row(submitted_at="2026-08-10T09:00:00+00:00")) == []


def test_ghost_window_is_the_users_own_setting():
    recent = row(submitted_at="2026-08-10T09:00:00+00:00")
    assert collect(recent, ghost_after_days=5) != []


def test_draft_with_a_closing_date_is_flagged_before_it_closes():
    items = collect(row(status="draft", expires_at="2026-08-18"))
    assert items[0].kind == "closing"
    assert items[0].days == 2


def test_distant_closing_date_is_left_alone():
    assert collect(row(status="draft", expires_at="2026-10-01")) == []


def test_offer_that_closed_before_it_was_sent_is_the_loudest_item():
    missed = row("a1", status="draft", expires_at="2026-08-10", company="Zeta")
    blocked = row("a2", status="blocked", blocked_reason="External form", company="Acme")
    items = collect(missed, blocked)
    assert [i.kind for i in items] == ["missed", "blocked"]
    assert items[0].days == 6


def test_blocked_application_says_what_is_blocking_it_in_the_users_own_words():
    items = collect(row(status="blocked", blocked_reason="Upload the CV by hand"))
    assert english(items[0]) == "Upload the CV by hand"
    assert polish(items[0]) == "Upload the CV by hand"


def test_blocked_without_a_reason_falls_back_to_the_catalogue():
    items = collect(row(status="blocked"))
    assert items[0].kind == "blocked"
    assert english(items[0]) == "Waiting on a manual step"
    assert polish(items[0]) == "Czeka na ręczny krok"


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


# ---------------------------------------------------------------------------
# Wording
# ---------------------------------------------------------------------------


def test_the_nudge_is_phrased_in_the_readers_language():
    items = collect(row(submitted_at="2026-07-20T09:00:00+00:00"))
    assert english(items[0]) == "No answer for 27 days"
    assert polish(items[0]) == "Bez odpowiedzi od 27 dni"


def test_a_deadline_today_is_not_reported_as_zero_days():
    items = collect(row(status="draft", expires_at="2026-08-16"))
    assert english(items[0]) == "Closes today"
    assert polish(items[0]) == "Zamyka się dziś"


def test_one_day_reads_as_a_day_in_both_languages():
    items = collect(row(status="draft", expires_at="2026-08-17"))
    assert english(items[0]) == "Closes in one day"
    assert polish(items[0]) == "Zamyka się za jeden dzień"


def test_a_missed_deadline_says_how_long_ago():
    items = collect(row(status="draft", expires_at="2026-08-10"))
    assert english(items[0]) == "Closed 6 days ago, never sent"
    assert polish(items[0]) == "Zamknęła się 6 dni temu, nic nie poszło"
