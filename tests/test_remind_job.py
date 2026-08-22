"""The scheduled run, on stubs.

Nothing here touches a database or a mail provider. What is being checked is
the set of decisions the job makes before it sends anything: who is skipped,
what is written down, and what happens when a send fails — because the ways
this feature goes wrong are all quiet ones.
"""

from datetime import date

import pytest

from app.jobs import remind

MONDAY = date(2026, 8, 24)
TUESDAY = date(2026, 8, 25)


def account(**over):
    row = {
        "id": "u1",
        "email": "patryk@example.com",
        "display_name": "Patryk",
        "ghost_after_days": 21,
        "plan": "plus",
        "plan_until": None,
        "reminders_enabled": True,
        "lang": "pl",
    }
    row.update(over)
    return row


def application(**over):
    row = {
        "id": "a1",
        "status": "submitted",
        # 21 days before MONDAY, 22 before TUESDAY: silence that has just
        # crossed the default ghosting window, which is what a nudge is for.
        "submitted_at": "2026-08-03T09:00:00+00:00",
        "blocked_reason": None,
        "offers": {
            "title": "Specjalista ds. IT",
            "expires_at": None,
            "companies": {"name": "Nordflow"},
        },
    }
    row.update(over)
    return row


@pytest.fixture
def wired(monkeypatch):
    """The job with its database and its mailbox replaced."""
    state = {"sent": [], "recorded": [], "already": set(), "rows": [application()]}

    monkeypatch.setattr(remind.jobs_repo, "open_applications_for", lambda uid: state["rows"])
    monkeypatch.setattr(remind.jobs_repo, "reasons_already_sent", lambda uid: state["already"])
    monkeypatch.setattr(
        remind.jobs_repo,
        "record_nudge",
        lambda uid, aid, kind: state["recorded"].append((aid, kind)) is None,
    )
    monkeypatch.setattr(
        remind.sender,
        "send",
        lambda to, subject, text, headers=None: state["sent"].append((to, subject, text)) is None,
    )
    monkeypatch.setattr(remind.sender, "available", lambda: True)
    return state


def test_stale_silence_is_left_for_the_monday_summary(wired):
    """The first real run mailed sixty times because every old application
    still counted as news. Nothing here should nudge about last spring."""
    wired["rows"] = [application(submitted_at="2026-01-10T09:00:00+00:00")]
    assert remind.run_for(account(), today=TUESDAY, dry=False)["nudges"] == 0
    assert wired["sent"] == []


def test_a_silent_application_earns_a_nudge(wired):
    result = remind.run_for(account(), today=TUESDAY, dry=False)
    assert result["nudges"] == 1
    assert "Nordflow" in wired["sent"][0][1]


def test_the_same_reason_is_not_sent_again(wired):
    wired["already"] = {("a1", "silent")}
    assert remind.run_for(account(), today=TUESDAY, dry=False)["nudges"] == 0
    assert wired["sent"] == []


def test_a_free_account_gets_nothing(wired):
    """Reminders are a Plus feature, and plans.py is the one place that says so."""
    assert remind.run_for(account(plan="free"), today=TUESDAY, dry=False)["nudges"] == 0
    assert wired["sent"] == []


def test_an_account_that_switched_them_off_gets_nothing(wired):
    assert remind.run_for(account(reminders_enabled=False), today=MONDAY, dry=False) == {
        "nudges": 0,
        "summary": 0,
    }
    assert wired["sent"] == []


def test_an_account_with_no_address_is_skipped(wired):
    assert remind.run_for(account(email=None), today=TUESDAY, dry=False)["nudges"] == 0


def test_a_quiet_account_is_not_mailed_on_monday(wired):
    """No summary when there is nothing to summarise."""
    wired["rows"] = []
    assert remind.run_for(account(), today=MONDAY, dry=False)["summary"] == 0
    assert wired["sent"] == []


def test_monday_adds_the_summary(wired):
    result = remind.run_for(account(), today=MONDAY, dry=False)
    assert result["summary"] == 1
    subjects = [subject for _, subject, _ in wired["sent"]]
    assert any("tydzień" in s for s in subjects), subjects


def test_no_summary_on_a_tuesday(wired):
    assert remind.run_for(account(), today=TUESDAY, dry=False)["summary"] == 0


def test_the_reason_is_written_down_before_it_is_sent(wired):
    """A crash between the two loses one reminder. The other order sends it
    again tomorrow, which is the failure this feature exists to avoid."""
    remind.run_for(account(), today=TUESDAY, dry=False)
    assert wired["recorded"] == [("a1", "silent")]


def test_a_reason_already_recorded_is_not_sent(wired, monkeypatch):
    """`record_nudge` returning False means another run got there first."""
    monkeypatch.setattr(remind.jobs_repo, "record_nudge", lambda uid, aid, kind: False)
    assert remind.run_for(account(), today=TUESDAY, dry=False)["nudges"] == 0
    assert wired["sent"] == []


def test_a_dry_run_writes_nothing_and_sends_nothing(wired):
    result = remind.run_for(account(), today=MONDAY, dry=True)
    assert result["nudges"] == 1
    assert wired["sent"] == []
    assert wired["recorded"] == []


def test_the_mail_is_written_in_the_readers_language(wired):
    remind.run_for(account(lang="en"), today=MONDAY, dry=False)
    body = wired["sent"][-1][2]
    assert "This week" in body or "Mondays" in body


def test_every_mail_offers_a_way_out(wired):
    """A reader who wants out should not have to sign in to find the switch."""
    remind.run_for(account(), today=TUESDAY, dry=False)
    assert "mailto:kontakt@" in remind.unsubscribe_for()
    assert "List-Unsubscribe" in remind.sender.unsubscribe_headers(remind.unsubscribe_for())


def test_the_body_links_to_the_application(wired):
    remind.run_for(account(), today=TUESDAY, dry=False)
    assert "/applications/a1" in wired["sent"][0][2]


def test_one_account_failing_does_not_end_the_run(monkeypatch):
    monkeypatch.setattr(remind.sender, "available", lambda: True)
    monkeypatch.setattr(
        remind.jobs_repo, "accounts_to_remind", lambda: [account(id="u1"), account(id="u2")]
    )

    seen = []

    def explode_for_the_first(user_id):
        seen.append(user_id)
        if user_id == "u1":
            raise RuntimeError("their mailbox is on fire")
        return []

    monkeypatch.setattr(remind.jobs_repo, "open_applications_for", explode_for_the_first)
    assert remind.main([]) == 0
    assert seen == ["u1", "u2"]


def test_the_command_refuses_to_run_without_a_key(monkeypatch):
    """Better a non-zero exit in a scheduler's log than a silent nightly no-op."""
    monkeypatch.setattr(remind.sender, "available", lambda: False)
    assert remind.main([]) == 1


def test_a_dry_run_works_without_a_key(monkeypatch):
    monkeypatch.setattr(remind.sender, "available", lambda: False)
    monkeypatch.setattr(remind.jobs_repo, "accounts_to_remind", lambda: [])
    assert remind.main(["--dry"]) == 0
