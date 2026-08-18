"""Deciding which application a reply belongs to.

Getting this wrong in the confident direction is the worst thing this feature
can do: moving the wrong application to "rejected" edits someone's record of
their own job search. So a match is only acted on when the evidence is strong,
and everything else is shown for a person to confirm.

Pure functions over rows, so every rule here is checked without a database.
"""

from dataclasses import dataclass
from typing import Any

from app.ingest.reading import fold

# Domains that belong to everyone and therefore identify nobody.
SHARED_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "outlook.com",
    "hotmail.com",
    "wp.pl",
    "o2.pl",
    "interia.pl",
    "onet.pl",
    "yahoo.com",
    "icloud.com",
    "proton.me",
    "protonmail.com",
}

# Words that appear in half of all company names and so cannot carry a match.
NOISE = {
    "sp",
    "z",
    "o",
    "o.o",
    "sp.",
    "z.o.o",
    "spolka",
    "group",
    "grupa",
    "polska",
    "poland",
    "sa",
    "s.a",
    "it",
    "the",
}


@dataclass(frozen=True)
class Match:
    application_id: str
    company_name: str
    how: str  # domain | name
    sure: bool


def _words(name: str) -> set[str]:
    cleaned = fold(name).replace(".", " ").replace(",", " ").replace("-", " ")
    return {word for word in cleaned.split() if len(word) > 2 and word not in NOISE}


def find(
    applications: list[dict[str, Any]],
    from_domain: str,
    subject: str,
    body: str,
) -> Match | None:
    """The application a message is about, when that can be told.

    `applications` are the rows with their offer and company joined in — the
    same shape `list_applications` returns.
    """
    domain = (from_domain or "").strip().lower()

    # A company's own mail domain is the one piece of evidence worth acting on
    # by itself — but only when it is theirs. A reply from a recruiter's Gmail
    # says nothing about which company they were writing about.
    if domain and domain not in SHARED_DOMAINS:
        by_domain = [
            a
            for a in applications
            if (((a.get("offers") or {}).get("companies") or {}).get("email_domain") or "").lower()
            in (domain, _strip_subdomain(domain))
        ]
        if len(by_domain) == 1:
            application = by_domain[0]
            return Match(
                application_id=application["id"],
                company_name=_company_name(application),
                how="domain",
                sure=True,
            )
        if len(by_domain) > 1:
            # Two applications to the same company: the message is about one of
            # them and there is nothing here to say which.
            return None

    # Otherwise look for the company's name in what was written. Enough to
    # surface a suggestion, never enough to move a status on its own.
    haystack = fold(f"{subject}\n{body}")
    hits = []
    for application in applications:
        name = _company_name(application)
        words = _words(name)
        if words and all(word in haystack for word in words):
            hits.append(application)

    if len(hits) == 1:
        return Match(
            application_id=hits[0]["id"],
            company_name=_company_name(hits[0]),
            how="name",
            sure=False,
        )
    return None


def _strip_subdomain(domain: str) -> str:
    """`kariera.acme.pl` is still Acme."""
    parts = domain.split(".")
    return ".".join(parts[-3:]) if len(parts) > 3 else ".".join(parts[-2:])


def _company_name(application: dict[str, Any]) -> str:
    return ((application.get("offers") or {}).get("companies") or {}).get("name") or ""
