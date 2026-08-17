"""Language selection, and the guarantee that both catalogues stay in step."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app import i18n
from app.main import app

LOCALES = Path(__file__).resolve().parents[1] / "app" / "locales"


def catalogue(lang):
    return json.loads((LOCALES / f"{lang}.json").read_text(encoding="utf-8"))


def test_both_catalogues_hold_exactly_the_same_keys():
    """A key present in one language and missing in the other renders as the
    key itself on someone's screen. Cheaper to fail here."""
    assert set(catalogue("pl")) == set(catalogue("en"))


def test_no_translation_is_left_empty():
    for lang in i18n.SUPPORTED:
        blanks = [key for key, text in catalogue(lang).items() if not text.strip()]
        assert blanks == [], f"{lang} has empty strings: {blanks}"


def test_placeholders_match_between_languages():
    """`{days}` in one language and `{count}` in the other silently drops the
    number — `str.format` raises, and the translator swallows it."""
    import re

    pl, en = catalogue("pl"), catalogue("en")
    for key in pl:
        assert set(re.findall(r"{(\w+)}", pl[key])) == set(re.findall(r"{(\w+)}", en[key])), key


def test_polish_is_the_default_because_that_is_the_job_market():
    assert i18n.DEFAULT_LANG == "pl"


def test_the_sign_in_page_speaks_polish_without_being_asked():
    response = TestClient(app).get("/login")
    assert "Dobrze, że wracasz" in response.text


def test_the_cookie_decides_the_language():
    response = TestClient(app, cookies={"lang": "en"}).get("/login")
    assert "Good to see you back" in response.text


def test_the_browser_is_asked_before_falling_back():
    response = TestClient(app).get("/login", headers={"accept-language": "en-GB,en;q=0.9"})
    assert "Good to see you back" in response.text


def test_an_unsupported_language_falls_back_rather_than_breaking():
    response = TestClient(app, cookies={"lang": "de"}).get("/login")
    assert response.status_code == 200
    assert "Dobrze, że wracasz" in response.text


def test_a_missing_key_renders_as_itself_so_the_gap_is_visible():
    t = i18n.translator("pl")
    assert t("no.such.key") == "no.such.key"
