"""Deciding what is worth a mail.

The failure this guards against is not "no mail arrived". It is the opposite:
the same reminder every morning until the reader builds a filter for it, at
which point the feature is worse than nothing because it also hides the mails
that mattered.
"""

from datetime import date

from app.attention import Item
from app.reminders import is_summary_day, nudges, summary, worth_sending


def item(application_id="a1", kind="silent", days=21, company="Nordflow"):
    return Item(
        application_id=application_id,
        company=company,
        title="Specjalista ds. sprzedaży B2B",
        status="submitted",
        kind=kind,
        days=days,
    )


def test_an_urgent_item_nobody_has_been_told_about_is_a_nudge():
    assert [n.item for n in nudges([item()], set())] == [item()]


def test_the_same_reason_is_never_sent_twice():
    """The point of the whole module. A deadline does not become more urgent by
    being mentioned again tomorrow, and a daily repeat is how mail gets
    filtered."""
    assert nudges([item()], {("a1", "silent")}) == []


def test_a_new_reason_on_the_same_application_is_a_new_nudge():
    """A deadline that was approaching and is now missed is genuinely news."""
    sent = {("a1", "closing")}
    assert [n.item.kind for n in nudges([item(kind="missed", days=3)], sent)] == ["missed"]


def test_a_blocked_application_is_never_mailed_about():
    """It is blocked because the reader marked it blocked. Mailing them about
    something they just typed is noise."""
    assert nudges([item(kind="blocked", days=None)], set()) == []


def test_a_blocked_application_still_reaches_the_weekly_summary():
    """A half-finished form is exactly what a weekly look is for."""
    blocked = item(kind="blocked", days=None)
    assert summary([blocked]) == [blocked]


def test_every_urgent_kind_is_worth_a_mail():
    """Each with a `days` that means "this just happened" for that kind: for
    silence it counts up from the ghosting window, for a missed deadline it
    counts from the day it passed."""
    for kind, days in (("missed", 1), ("closing", 2), ("silent", 22)):
        assert nudges([item(kind=kind, days=days)], set()), kind


def test_nudges_keep_the_order_they_arrived_in():
    """The attention list is already sorted by how soon something stops being
    possible; a mail that gets cut short should lose the least urgent end."""
    ordered = [
        item(application_id="a1", kind="missed", days=1),
        item(application_id="a2", kind="silent", days=22),
    ]
    assert [n.item.application_id for n in nudges(ordered, set())] == ["a1", "a2"]


def test_the_dedupe_key_is_the_application_and_the_reason():
    assert nudges([item()], set())[0].key == ("a1", "silent")


def test_two_applications_with_the_same_reason_are_separate_nudges():
    pair = [item(application_id="a1"), item(application_id="a2", company="Kaskada")]
    assert len(nudges(pair, set())) == 2


def test_the_summary_goes_out_on_monday():
    assert is_summary_day(date(2026, 8, 24))  # a Monday


def test_the_summary_does_not_go_out_on_other_days():
    for day in range(25, 31):  # Tuesday to Sunday
        assert not is_summary_day(date(2026, 8, day)), day


def test_a_quiet_week_produces_no_mail():
    """A summary that reports nothing is a summary people unsubscribe from."""
    assert not worth_sending([])


def test_a_week_with_something_in_it_does():
    assert worth_sending([item()])


# ── the backlog ──────────────────────────────────────────────────────
#
# What the first run against a real register did: sixty applications, most
# quiet for months, every one of them a mail. The dedupe rule was working —
# it stops one thing being said twice, not sixty things being said at once.


def test_something_quiet_for_months_is_not_news():
    """122 days of silence with a 21-day window crossed the line 101 days ago.
    The reader knows. It belongs in Monday's list, not in their morning."""
    assert nudges([item(kind="silent", days=122)], set(), ghost_after_days=21) == []


def test_silence_that_has_just_begun_is_news():
    assert nudges([item(kind="silent", days=22)], set(), ghost_after_days=21)


def test_the_window_gives_a_missed_night_some_slack():
    """A scheduler that skips a run must not lose the nudge for good."""
    assert nudges([item(kind="silent", days=24)], set(), ghost_after_days=21)


def test_the_window_follows_the_accounts_own_ghosting_setting():
    """Someone who calls it ghosting after 60 days should not be told at 21."""
    assert nudges([item(kind="silent", days=22)], set(), ghost_after_days=60) == []
    assert nudges([item(kind="silent", days=61)], set(), ghost_after_days=60)


def test_a_long_missed_deadline_is_not_news_either():
    assert nudges([item(kind="missed", days=90)], set()) == []


def test_a_deadline_missed_yesterday_is():
    assert nudges([item(kind="missed", days=1)], set())


def test_a_closing_offer_is_always_fresh():
    """It is urgent now and only for a week, so it cannot pile up."""
    for days in (0, 3, 7):
        assert nudges([item(kind="closing", days=days)], set()), days


def test_a_first_run_on_a_long_backlog_stays_quiet():
    """The regression this whole section exists for: a register full of old
    silence produces almost nothing, not one mail per row."""
    backlog = [item(application_id=f"a{n}", kind="silent", days=30 + n * 5) for n in range(60)]
    assert len(nudges(backlog, set(), ghost_after_days=21)) <= 4


def test_a_run_is_capped_even_if_everything_is_genuinely_fresh():
    """A backstop under the freshness rule, not a substitute for it."""
    fresh = [item(application_id=f"a{n}", kind="silent", days=22) for n in range(20)]
    assert len(nudges(fresh, set(), ghost_after_days=21)) == 4


def test_the_cap_keeps_the_most_urgent_end():
    ordered = [item(application_id=f"a{n}", kind="closing", days=n) for n in range(10)]
    kept = [n.item.application_id for n in nudges(ordered, set())]
    assert kept == ["a0", "a1", "a2", "a3"]


def test_the_summary_is_not_capped_or_filtered():
    """Monday is where the backlog belongs, in full."""
    backlog = [item(application_id=f"a{n}", kind="silent", days=200) for n in range(60)]
    assert len(summary(backlog)) == 60
