"""Keeping an extractor honest.

A model asked to pull offers out of an alert is doing extraction, not writing:
every field it returns should already be sitting in the message. So we check
that it is. A title, company or city that does not appear in the source is
dropped, and an offer left without a title is dropped whole.

This is cheap — string comparisons against a few kilobytes — and it removes the
failure that actually matters here. A model that invents a plausible salary
does not produce an obvious error; it produces a number someone negotiates
against six weeks later, believing an employer said it.

The same guard is why the offer's link never comes from the model. It is found
by pattern in `offers.py` and matched here: the URL is the dedupe key and the
"open the advert" button, and both have to be exactly right.
"""

from __future__ import annotations

import re

# Whitespace differs between a wrapped text part and what a model echoes back;
# nothing else is allowed to differ.
SPACES = re.compile(r"\s+")


def flatten(text: str) -> str:
    """Collapse runs of whitespace so wrapping cannot fail a true match."""
    return SPACES.sub(" ", (text or "").replace(" ", " ")).strip()


def present(value: str | None, haystack: str) -> bool:
    """Whether the model's text really is in the message.

    Case-sensitive on purpose. A model that returns "BACKUP S.C." for "Backup
    S.C." is rewriting rather than copying, and a model that rewrites the parts
    we can check is a model to distrust on the parts we cannot.
    """
    if not value:
        return False
    return flatten(value) in haystack


def digits(value: float | int | None) -> str | None:
    """The way an amount would be written without its grouping."""
    if value is None:
        return None
    whole = int(value)
    return str(whole) if whole == value else str(value)


def amount_present(value: float | int | None, haystack: str) -> bool:
    """Whether a number the model reported is really quoted in the message.

    Adverts group thousands with spaces or dots ("6 000", "6.000"), so the
    haystack is compared with its separators removed as well as intact.
    """
    if value is None:
        return True  # Nothing claimed, nothing to disprove.
    wanted = digits(value)
    if wanted is None:
        return False
    stripped = haystack.replace(" ", "").replace(".", "").replace(",", "")
    return wanted in haystack or wanted in stripped
