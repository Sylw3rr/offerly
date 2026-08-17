"""What an account is allowed to do, and what happens when a plan runs out."""

from datetime import UTC, datetime, timedelta

from app import plans


def profile(plan="free", plan_until=None):
    return {"plan": plan, "plan_until": plan_until}


def iso(days_from_now):
    return (datetime.now(UTC) + timedelta(days=days_from_now)).isoformat()


def test_a_new_account_is_on_the_free_plan():
    assert plans.for_profile(profile()).name == plans.FREE


def test_a_missing_profile_is_free_rather_than_an_error():
    assert plans.for_profile(None).name == plans.FREE
    assert plans.for_profile({}).name == plans.FREE


def test_a_granted_plan_with_no_end_date_stays_in_force():
    assert plans.for_profile(profile("plus")).name == plans.PLUS


def test_a_plan_that_has_not_lapsed_yet_is_in_force():
    assert plans.for_profile(profile("plus", iso(30))).name == plans.PLUS


def test_a_lapsed_plan_becomes_the_free_plan():
    """Nothing is taken away — the automation stops and the data stays."""
    assert plans.for_profile(profile("plus", iso(-1))).name == plans.FREE


def test_an_unreadable_end_date_does_not_hand_out_a_paid_plan():
    assert plans.for_profile(profile("plus", "not-a-date")).name == plans.FREE


def test_an_unknown_plan_name_falls_back_to_free():
    assert plans.for_profile(profile("enterprise")).name == plans.FREE


# ---------------------------------------------------------------------------
# The ceilings themselves
# ---------------------------------------------------------------------------


def test_free_keeps_two_cv_versions():
    free = plans.PLANS[plans.FREE]
    assert free.allows(plans.CV_VERSIONS, current=0)
    assert free.allows(plans.CV_VERSIONS, current=1)
    assert not free.allows(plans.CV_VERSIONS, current=2)


def test_plus_has_no_ceiling_on_cv_versions():
    plus = plans.PLANS[plans.PLUS]
    assert plus.limit(plans.CV_VERSIONS) is plans.UNLIMITED
    assert plus.allows(plans.CV_VERSIONS, current=99)


def test_free_gets_a_monthly_taste_of_collected_offers_rather_than_none():
    """A wall with nothing behind it teaches nobody what they are missing."""
    assert plans.PLANS[plans.FREE].limit(plans.OFFERS_COLLECTED) == 10


def test_the_features_that_cost_the_server_money_are_off_on_free():
    free = plans.PLANS[plans.FREE]
    for capability in (plans.REPLY_MATCHING, plans.REMINDERS, plans.STATS_BREAKDOWN):
        assert not free.allows(capability), capability


def test_an_unknown_capability_is_refused_rather_than_allowed():
    """A feature added without a line in the table should be closed, not open."""
    assert not plans.PLANS[plans.PLUS].allows("something_new")
