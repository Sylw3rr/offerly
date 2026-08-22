"""The scheduled run that sends reminders.

    python -m app.jobs.remind          # send
    python -m app.jobs.remind --dry    # report what it would send

Runs once a day. Nudges go out whenever something has just become urgent; the
summary goes out on Mondays. Which is which, and what counts as urgent, lives
in `app/reminders.py` — this module is the plumbing around it: who to ask
about, in which language, and writing down what was sent.

One account's problem is not everybody's. Each account is handled inside its
own try, because a run that stops at the first bounced address silently drops
everyone alphabetically after them.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, date, datetime

from app.attention import collect
from app.config import get_settings
from app.db import jobs_repo
from app.i18n import translator
from app.mail import sender
from app.plans import REMINDERS, for_profile
from app.reminders import Nudge, is_summary_day, nudges, summary, worth_sending

log = logging.getLogger(__name__)


def unsubscribe_for() -> str:
    """Where a reader who wants out is sent.

    A mailto rather than a one-click endpoint: an unauthenticated URL that
    changes an account setting is a URL anyone can guess at, and at this size a
    message that reaches a person is both honest and enough.
    """
    domain = get_settings().ingest_domain or "offerly.com.pl"
    return f"mailto:kontakt@{domain}?subject=Wypisz%20mnie%20z%20przypomnien"


def compose_nudge(t, found: Nudge) -> tuple[str, str]:
    item = found.item
    subject = t("mail.nudge.subject", company=item.company, why=item.message(t).lower())
    body = t(
        "mail.nudge.body",
        company=item.company,
        role=item.title,
        why=item.message(t),
        url=f"{get_settings().app_base_url}/applications/{item.application_id}",
    )
    return subject, body


def compose_summary(t, items) -> tuple[str, str]:
    lines = [
        t("mail.summary.line", company=i.company, role=i.title, why=i.message(t)) for i in items
    ]
    subject = t("mail.summary.subject", count=len(items))
    body = t(
        "mail.summary.body",
        lines="\n".join(lines),
        url=f"{get_settings().app_base_url}/dashboard",
    )
    return subject, body


def run_for(account: dict, *, today: date, dry: bool) -> dict[str, int]:
    """Everything owed to one account today."""
    sent = {"nudges": 0, "summary": 0}

    plan = for_profile(account)
    if plan.limit(REMINDERS) == 0:
        return sent
    if not account.get("reminders_enabled", True):
        return sent
    if not account.get("email"):
        return sent

    rows = jobs_repo.open_applications_for(account["id"])
    items = collect(
        rows,
        today=today,
        ghost_after_days=account.get("ghost_after_days") or 21,
    )
    if not worth_sending(items):
        return sent

    t = translator(account.get("lang") or "pl")
    headers = sender.unsubscribe_headers(unsubscribe_for())

    already = jobs_repo.reasons_already_sent(account["id"])
    ghost_after_days = account.get("ghost_after_days") or 21
    for found in nudges(items, already, ghost_after_days=ghost_after_days):
        subject, body = compose_nudge(t, found)
        if dry:
            log.info("would nudge %s: %s", account["email"], subject)
            sent["nudges"] += 1
            continue
        # Recorded first. A crash between sending and writing would resend
        # tomorrow; a crash between writing and sending loses one reminder,
        # and losing one is the better failure.
        if not jobs_repo.record_nudge(account["id"], found.item.application_id, found.item.kind):
            continue
        if sender.send(account["email"], subject, body, headers):
            sent["nudges"] += 1

    if is_summary_day(today):
        subject, body = compose_summary(t, summary(items))
        if dry:
            log.info("would summarise to %s: %s", account["email"], subject)
            sent["summary"] += 1
        elif sender.send(account["email"], subject, body, headers):
            sent["summary"] += 1

    return sent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry", action="store_true", help="report without sending")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    today = datetime.now(UTC).date()

    if not args.dry and not sender.available():
        log.error("no mail key configured; nothing can be sent. Use --dry to see what would go.")
        return 1

    totals = {"nudges": 0, "summary": 0, "accounts": 0, "failed": 0}
    for account in jobs_repo.accounts_to_remind():
        totals["accounts"] += 1
        try:
            result = run_for(account, today=today, dry=args.dry)
        except Exception:  # noqa: BLE001 — one account must not end the run
            log.exception("reminding %s failed", account.get("id"))
            totals["failed"] += 1
            continue
        totals["nudges"] += result["nudges"]
        totals["summary"] += result["summary"]

    log.info(
        "%s: %d accounts, %d nudges, %d summaries, %d failed",
        "dry run" if args.dry else "sent",
        totals["accounts"],
        totals["nudges"],
        totals["summary"],
        totals["failed"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
