"""The public page.

It is the only page a stranger sees, so what matters is that it renders in both
languages, promises nothing the product does not do, and offers a way in for
people who already have an account.
"""

import re

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import CurrentUser
from app.i18n import LANG_COOKIE
from app.main import app


@pytest.fixture
def fresh():
    """A client of its own.

    The language is a cookie, and a shared client carries it from one test into
    the next — which is correct behaviour and useless for testing it.
    """
    return TestClient(app)


def test_the_landing_is_the_front_page(fresh):
    response = fresh.get("/")
    assert response.status_code == 200
    assert "Wysyłasz. Czekasz." in response.text


def test_every_section_the_design_calls_for_is_present(fresh):
    text = fresh.get("/").text
    for section in (
        "problem",
        "jak",
        "funkcje",
        "statystyki",
        "prywatnosc",
        "cennik",
        "faq",
        "kod",
    ):
        assert f'id="{section}"' in text, section


def test_no_translation_key_leaks_onto_the_page(fresh):
    """A missing key renders as the key itself — the point of the fallback, and
    exactly what must never reach a stranger."""
    text = fresh.get("/").text
    leaked = [k for k in re.findall(r"landing\.[a-z_.0-9]+", text) if not k.endswith(".js")]
    assert leaked == []


def test_the_page_reads_polish_by_default(fresh):
    assert 'lang="pl"' in fresh.get("/").text


def test_english_is_a_click_away(fresh):
    response = fresh.get("/?lang=en")
    assert "You send. You wait." in response.text


def test_the_choice_sticks_in_the_same_cookie_the_account_page_uses(fresh):
    response = fresh.get("/?lang=en")
    assert f"{LANG_COOKIE}=en" in response.headers.get("set-cookie", "")
    # And the next page, asked for without the parameter, stays English.
    assert "You send. You wait." in fresh.get("/").text


def test_an_unknown_language_is_ignored(fresh):
    response = fresh.get("/?lang=de")
    assert "lang=de" not in response.headers.get("set-cookie", "")
    assert 'lang="pl"' in response.text


def test_someone_with_an_account_can_get_in_from_here(fresh):
    """The design had no way in at all — every visitor was assumed to be new."""
    assert 'href="/login"' in fresh.get("/").text


def test_a_signed_in_visitor_goes_straight_to_the_application(fresh, monkeypatch):
    import app.main as main

    monkeypatch.setattr(
        main,
        "get_current_user",
        lambda request: CurrentUser(id="u1", email="a@b.pl", access_token="t"),
    )
    response = fresh.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"


def test_the_page_fetches_nothing_from_anyone_else(fresh):
    """The same promise the application makes, on the page most tempted by a
    webfont or an analytics tag."""
    text = fresh.get("/").text
    hosts = {
        host
        for host in re.findall(r'(?:src|href)\s*=\s*"(?:https?:)?//([^/"]+)', text)
        if host != "testserver"
    }
    assert hosts <= {"github.com"}, hosts
    assert "@import" not in text


def test_the_invitation_is_a_message_not_a_form(fresh):
    """No address is collected before there is somewhere rate-limited to keep
    one, so the call to action writes an email instead of posting."""
    text = fresh.get("/").text
    assert "mailto:kontakt@" in text
    assert 'type="email"' not in text


def test_the_two_paid_features_are_marked_as_paid(fresh):
    assert fresh.get("/").text.count("w planie Plus") == 2


def test_the_pricing_names_no_amount_that_cannot_be_paid(fresh):
    """There is no checkout, so no figure belongs on a public page.

    Matched as an amount rather than as the two letters: "zł" is a substring of
    ordinary Polish words like "poszło", which is what the first version of
    this test tripped over.
    """
    amounts = re.findall(r"\d[\d\s,.–-]*\s*(?:zł|PLN|EUR|USD|€|\$)", fresh.get("/").text)
    assert amounts == []


def test_the_heading_reads_whole_even_though_the_brand_is_lit_separately(fresh):
    """The brand is wrapped in a span so it can shimmer. Splitting a sentence to
    style one word is how a sentence loses a word."""
    import re

    for query, expected in (
        ("/", "Wysyłasz. Czekasz. Offerly pamięta za Ciebie."),
        ("/?lang=en", "You send. You wait. Offerly remembers for you."),
    ):
        html = fresh.get(query).text
        heading = re.search(r'<h1 class="l-h1"[^>]*>(.*?)</h1>', html, re.S).group(1)
        assert re.sub(r"<[^>]+>", "", heading).split() == expected.split(), query


def test_the_lit_brand_is_marked_up_once(fresh):
    assert fresh.get("/").text.count('class="l-shine"') == 1


def test_a_heading_without_the_brand_still_renders(fresh, monkeypatch):
    """`split` on a word that is not there returns the whole string, and the
    loop that adds the span simply does not run. Worth pinning: the failure
    mode would be a blank hero, on the only page a stranger sees."""
    import app.i18n as i18n

    real = i18n.translator

    def without_brand(lang):
        inner = real(lang)
        return lambda key, **kw: "Nic tu nie ma." if key == "landing.h1" else inner(key, **kw)

    monkeypatch.setattr(i18n, "translator", without_brand)
    html = fresh.get("/").text
    assert "Nic tu nie ma." in html
    assert 'class="l-shine"' not in html
