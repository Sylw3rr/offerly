"""Sending mail.

The first thing Offerly does that leaves the building. Two rules follow from
that, and both are enforced here rather than trusted to the caller:

- Without a key configured, nothing is sent and nothing raises. A development
  machine and a test run must never be able to mail a real person, and the way
  to guarantee that is for the absence of configuration to be the off switch.
- A failure to send is reported, not thrown. These calls happen inside a
  scheduled job looping over accounts; one account's bounced address must not
  end the run for everybody after them in the list.

Plain HTTP over httpx, as with `app/ai/gemini.py`. Resend's API is one POST and
a vendor SDK would bring its own transport and retry policy for no gain.
"""

from __future__ import annotations

import logging

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)

ENDPOINT = "https://api.resend.com/emails"
TIMEOUT = httpx.Timeout(15.0, connect=5.0)


def available() -> bool:
    settings = get_settings()
    return bool(settings.resend_api_key and settings.mail_from)


def send(to: str, subject: str, text: str, headers: dict[str, str] | None = None) -> bool:
    """Send one message. True if it was accepted, False if it was not.

    Plain text only, on purpose. Nothing here needs a layout, an HTML mail is a
    tracking pixel waiting to be added by someone in a hurry, and the promise
    on the landing page is that Offerly does not report on a job search.
    """
    settings = get_settings()
    if not available():
        log.info("mail not configured; would have sent %r to %s", subject, to)
        return False

    payload = {
        "from": settings.mail_from,
        "to": [to],
        "subject": subject,
        "text": text,
    }
    if headers:
        payload["headers"] = headers

    try:
        response = httpx.post(
            ENDPOINT,
            json=payload,
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
    except httpx.HTTPError as failure:
        log.warning("sending %r to %s failed: %s", subject, to, failure)
        return False

    return True


def unsubscribe_headers(url: str) -> dict[str, str]:
    """The headers that put a one-click unsubscribe in the mail client itself.

    Worth setting even though the account page has a switch: a reader who wants
    out wants out now, and making them sign in to find a checkbox is how a
    product earns a spam complaint instead of an unsubscribe.
    """
    return {
        "List-Unsubscribe": f"<{url}>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }
