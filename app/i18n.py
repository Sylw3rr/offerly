"""Interface language: `t('key')` in every template.

Which language: the `lang` cookie, then Accept-Language, then Polish. Polish is
the default because that is the job market this was built for — pracuj.pl, OLX,
umowa zlecenie, klauzula RODO.

A key with no translation renders as the key itself, so a missing string is
visible on the page rather than silently blank.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from fastapi import Request

LOCALES_DIR = Path(__file__).resolve().parent / "locales"
SUPPORTED = ("pl", "en")
DEFAULT_LANG = "pl"
LANG_COOKIE = "lang"


@lru_cache
def _catalog(lang: str) -> dict[str, str]:
    path = LOCALES_DIR / f"{lang}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def pick_lang(request: Request) -> str:
    cookie = request.cookies.get(LANG_COOKIE)
    if cookie in SUPPORTED:
        return cookie
    header = request.headers.get("accept-language", "")
    for part in header.split(","):
        code = part.split(";")[0].strip()[:2].lower()
        if code in SUPPORTED:
            return code
    return DEFAULT_LANG


def translator(lang: str):
    primary, fallback = _catalog(lang), _catalog(DEFAULT_LANG)

    def t(key: str, **kwargs) -> str:
        text = primary.get(key) or fallback.get(key) or key
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, IndexError):
                return text
        return text

    return t


def template_globals(request: Request) -> dict[str, object]:
    """Merge into every TemplateResponse context: `{**template_globals(request)}`."""
    lang = pick_lang(request)
    return {"lang": lang, "t": translator(lang)}
