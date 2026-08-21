"""Pulling the offers out of an alert with a model.

Why a model at all, when `app/ingest/offers.py` already reads pracuj.pl by
rule: because there are a dozen boards and each writes its alerts differently,
and each of them redesigns without telling us. A rule per board is a rule to
maintain per board, and a board nobody has written a rule for yields nothing at
all — which is the honest outcome, and a poor one for the person waiting on it.

What the model is and is not trusted with:

- It reads titles, companies, cities and quoted salaries out of the text.
  Every one of those is checked back against the message before it is stored,
  so the worst a wrong answer can do is lose a field.
- It never supplies the link. Links are found by pattern, because the URL is
  the dedupe key and the button that opens the advert, and "nearly right" is
  useless for both.
- It never decides whether something is an offer alert in the first place.
  That is `reading.py`, by sender and phrase, before this is reached.

The rules stay in place underneath: when there is no key configured, when the
call fails, or when the model returns nothing usable, a board we do have a
parser for is still parsed. Adding the model took nothing away.
"""

from __future__ import annotations

from app.ai import gemini
from app.ingest.offers import (
    LINK,
    ParsedOffer,
    Salary,
    clean_url,
    extract,
    ground,
    identify,
)

# Asking for the link back is how each row is tied to an address we found
# ourselves — the model copies one of the URLs already in the text, and we
# match it rather than trust it.
SCHEMA = {
    "type": "object",
    "properties": {
        "offers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "title": {"type": "string"},
                    "company": {"type": "string"},
                    "location": {"type": "string"},
                    "salary_min": {"type": "number"},
                    "salary_max": {"type": "number"},
                    "salary_currency": {"type": "string"},
                    "salary_kind": {"type": "string", "enum": ["gross", "net"]},
                    "salary_period": {"type": "string", "enum": ["hour", "month", "year"]},
                },
                "required": ["url", "title"],
            },
        }
    },
    "required": ["offers"],
}

PROMPT = """You are reading a job board's alert email and listing the job adverts in it.

Copy values exactly as they appear in the message. Do not translate, tidy,
expand abbreviations, or fix capitalisation. If a field is not stated for an
advert, leave it out rather than inferring it.

Rules:
- One entry per advert. The same advert listed twice is one entry.
- `url` must be copied character for character from the message.
- Ignore links that are not adverts: "more offers" searches, the unsubscribe
  link, app store links, social media, and the footer.
- Only report a salary the advert actually quotes. Never estimate one.
- `salary_kind` is "gross" for brutto and "net" for netto.
- `salary_period` is "hour" for godzina, "month" for miesiąc, "year" for rok.

The message follows.

---
{body}
---"""

# A digest is a few kilobytes; anything far larger is not an alert and is not
# worth paying to find out about.
MAX_CHARS = 40_000


def read_offers(body: str, source: str | None) -> list[ParsedOffer]:
    """The offers in an alert, from the model where possible and the rules
    otherwise. Everything returned has been checked against the message."""
    by_rule = ground(extract(body, source), body)

    if not gemini.available() or not body:
        return by_rule

    answer = gemini.structured(PROMPT.format(body=body[:MAX_CHARS]), SCHEMA)
    if not isinstance(answer, dict):
        return by_rule

    by_model = ground(_as_offers(answer.get("offers") or [], body), body)

    # The rules win where they exist: they cannot be wrong about a board they
    # were written for, and they cost nothing. The model covers the rest.
    if by_rule:
        known = {offer.external_id for offer in by_rule}
        return by_rule + [offer for offer in by_model if offer.external_id not in known]
    return by_model


def _as_offers(rows: list[dict], body: str) -> list[ParsedOffer]:
    """Turn the model's rows into offers, taking the address from the message.

    The URL the model echoed is used only to find which of the links actually
    present in the text it meant; the stored address is that link, cleaned.
    """
    links = {link: clean_url(link) for link in LINK.findall(body)}
    offers = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        echoed = (row.get("url") or "").strip()
        matched = _match_link(echoed, links)
        if matched is None or not (row.get("title") or "").strip():
            continue

        offers.append(
            ParsedOffer(
                external_id=identify(matched),
                title=row["title"].strip(),
                url=matched,
                company=(row.get("company") or "").strip() or None,
                location=(row.get("location") or "").strip() or None,
                salary=_as_salary(row),
            )
        )
    return offers


def _match_link(echoed: str, links: dict[str, str]) -> str | None:
    """The real link the model was pointing at, or None if it pointed nowhere.

    Matching on the part before the query: the model routinely drops or
    reorders tracking parameters when copying a long URL, and that is the part
    we throw away anyway.
    """
    if not echoed:
        return None
    wanted, _, _ = echoed.partition("?")
    for original, cleaned in links.items():
        if original.partition("?")[0] == wanted:
            return cleaned
    return None


def _as_salary(row: dict) -> Salary | None:
    low, high = row.get("salary_min"), row.get("salary_max")
    if low is None and high is None:
        return None
    return Salary(
        minimum=low,
        maximum=high,
        currency=(row.get("salary_currency") or "PLN").upper()[:3],
        kind=row.get("salary_kind"),
        period=row.get("salary_period"),
    )
