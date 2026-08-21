"""Reading adverts out of an alert, and refusing to believe things.

The fixture reproduces the structure of a real pracuj.pl alert — the repeated
link before every field, the salary line that only appears for some adverts,
the "more offers" search link between sections, the promoted row marked with a
leading "!", and a footer full of links that are not adverts. The content is
invented: which searches somebody has saved is their business.
"""

import pathlib
from dataclasses import replace

from app.ai import offer_reader
from app.ingest.offers import Salary, clean_url, extract, ground, identify

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "pracuj_alert.txt"
ALERT = FIXTURE.read_text(encoding="utf-8")


def parsed():
    return extract(ALERT, "pracuj_pl")


def by_title(title):
    return next(offer for offer in parsed() if offer.title == title)


# ── the rules ────────────────────────────────────────────────────────


def test_every_advert_is_found_and_nothing_else_is():
    assert {offer.title for offer in parsed()} == {
        "Monter instalacji",
        "Analityk / Analityczka danych",
        "Koordynator/Koordynatorka zmiany",
    }


def test_the_same_advert_in_two_sections_is_one_row():
    """The digest lists it once and the recommendations list it again; the
    board's id is the same both times, which is the whole reason to key on it."""
    monter = [offer for offer in parsed() if offer.title == "Monter instalacji"]
    assert len(monter) == 1


def test_the_more_offers_link_is_not_an_advert():
    """It points at a search. Nothing in the listing may be attributed to it."""
    assert all("kw=przyklad" not in offer.url for offer in parsed())
    assert all(offer.title != "Zobacz oferty, które mogły Ci umknąć" for offer in parsed())


def test_the_footer_produces_nothing():
    for offer in parsed():
        assert "play.google.com" not in offer.url
        assert "facebook.com" not in offer.url


def test_a_promoted_row_keeps_its_title_without_the_marker():
    assert by_title("Koordynator/Koordynatorka zmiany").company == "Zakład Przykładowy w Gliwicach"


def test_a_salary_line_does_not_shift_the_company_and_city():
    """The bug real data found: only some adverts carry a salary line, so
    counting fields off by position put money where the company belongs."""
    analityk = by_title("Analityk / Analityczka danych")
    assert analityk.company == "Firma Testowa S.C."
    assert analityk.location == "Mysłowice"


def test_a_quoted_range_is_read_with_its_units():
    assert by_title("Analityk / Analityczka danych").salary == Salary(
        minimum=6000.0, maximum=10000.0, currency="PLN", kind="gross", period="month"
    )


def test_an_advert_without_a_quoted_salary_reports_none():
    assert by_title("Monter instalacji").salary is None


def test_the_delivery_tracking_does_not_follow_the_offer_into_the_database():
    for offer in parsed():
        assert "sendid" not in offer.url
        assert "utm_" not in offer.url


def test_the_identifier_survives_the_tracking_being_different():
    """The same advert arrives under two campaigns in this very fixture."""
    assert by_title("Monter instalacji").external_id == "pracuj:1000000001"


def test_a_board_with_no_parser_yields_nothing_rather_than_a_guess():
    assert extract(ALERT, "olx") == []
    assert extract(ALERT, None) == []


def test_clean_url_keeps_a_query_that_is_not_tracking():
    assert clean_url("https://x.pl/a?id=7&utm_source=ja&sendid=1") == "https://x.pl/a?id=7"


def test_identify_falls_back_to_the_address_for_an_unknown_board():
    assert identify("https://praca.example/oferta/xyz?utm_source=a") == (
        "https://praca.example/oferta/xyz"
    )


# ── grounding ────────────────────────────────────────────────────────


def test_grounding_leaves_a_truthful_reading_alone():
    assert ground(parsed(), ALERT) == parsed()


def test_an_invented_company_is_dropped_but_the_advert_is_kept():
    tampered = replace(by_title("Monter instalacji"), company="Firma, Której Nie Ma")
    (kept,) = ground([tampered], ALERT)
    assert kept.company is None
    assert kept.title == "Monter instalacji"


def test_an_invented_salary_is_dropped():
    tampered = replace(
        by_title("Monter instalacji"),
        salary=Salary(minimum=99000.0, maximum=None, currency="PLN", kind="gross", period="month"),
    )
    (kept,) = ground([tampered], ALERT)
    assert kept.salary is None


def test_a_quoted_salary_survives_being_checked():
    """The guard must not throw away the money that really is in the message."""
    (kept,) = ground([by_title("Analityk / Analityczka danych")], ALERT)
    assert kept.salary is not None
    assert kept.salary.minimum == 6000.0


def test_an_advert_whose_title_is_not_in_the_message_is_dropped_whole():
    tampered = replace(by_title("Monter instalacji"), title="Senior Rust Engineer")
    assert ground([tampered], ALERT) == []


def test_an_advert_pointing_at_a_link_the_message_never_had_is_dropped():
    tampered = replace(by_title("Monter instalacji"), url="https://evil.example/oferta,oferta,1")
    assert ground([tampered], ALERT) == []


# ── the model path ───────────────────────────────────────────────────


def test_without_a_key_the_rules_still_answer(monkeypatch):
    monkeypatch.setattr(offer_reader.gemini, "available", lambda: False)
    assert len(offer_reader.read_offers(ALERT, "pracuj_pl")) == 3


def test_the_model_covers_a_board_the_rules_do_not_know(monkeypatch):
    """The point of adding it: OLX has no parser, so the rules return nothing."""
    monkeypatch.setattr(offer_reader.gemini, "available", lambda: True)
    monkeypatch.setattr(
        offer_reader.gemini,
        "structured",
        lambda prompt, schema: {
            "offers": [
                {
                    "url": (
                        "https://www.pracuj.pl/praca/monter-instalacji-przykladowo"
                        ",oferta,1000000001?sendid=aaaa-bbbb&utm_medium=email"
                    ),
                    "title": "Monter instalacji",
                    "company": "Przykładowa Spółka sp. z o.o.",
                    "location": "Luboń",
                }
            ]
        },
    )
    (found,) = offer_reader.read_offers(ALERT, "olx")
    assert found.external_id == "pracuj:1000000001"
    assert found.company == "Przykładowa Spółka sp. z o.o."
    # The stored address is ours, not the one the model echoed back.
    assert "sendid" not in found.url


def test_a_model_row_pointing_nowhere_in_the_message_is_dropped(monkeypatch):
    monkeypatch.setattr(offer_reader.gemini, "available", lambda: True)
    monkeypatch.setattr(
        offer_reader.gemini,
        "structured",
        lambda prompt, schema: {
            "offers": [{"url": "https://elsewhere.example/job/1", "title": "Monter instalacji"}]
        },
    )
    assert offer_reader.read_offers(ALERT, "olx") == []


def test_a_model_that_invents_a_salary_has_it_removed(monkeypatch):
    monkeypatch.setattr(offer_reader.gemini, "available", lambda: True)
    monkeypatch.setattr(
        offer_reader.gemini,
        "structured",
        lambda prompt, schema: {
            "offers": [
                {
                    "url": (
                        "https://www.pracuj.pl/praca/monter-instalacji-przykladowo"
                        ",oferta,1000000001?sendid=aaaa-bbbb&utm_medium=email"
                    ),
                    "title": "Monter instalacji",
                    "salary_min": 25000,
                    "salary_period": "month",
                    "salary_kind": "gross",
                }
            ]
        },
    )
    (found,) = offer_reader.read_offers(ALERT, "olx")
    assert found.salary is None


def test_a_failed_call_leaves_the_rules_answer_standing(monkeypatch):
    monkeypatch.setattr(offer_reader.gemini, "available", lambda: True)
    monkeypatch.setattr(offer_reader.gemini, "structured", lambda prompt, schema: None)
    assert len(offer_reader.read_offers(ALERT, "pracuj_pl")) == 3


def test_the_rules_win_where_they_exist(monkeypatch):
    """A board we parse ourselves is not re-decided by the model: the rules
    cannot be wrong about a format they were written against."""
    monkeypatch.setattr(offer_reader.gemini, "available", lambda: True)
    monkeypatch.setattr(
        offer_reader.gemini,
        "structured",
        lambda prompt, schema: {
            "offers": [
                {
                    "url": (
                        "https://www.pracuj.pl/praca/monter-instalacji-przykladowo"
                        ",oferta,1000000001?sendid=aaaa-bbbb&utm_medium=email"
                    ),
                    "title": "Monter instalacji",
                    "company": "Coś Zupełnie Innego",
                }
            ]
        },
    )
    monter = next(
        offer
        for offer in offer_reader.read_offers(ALERT, "pracuj_pl")
        if offer.external_id == "pracuj:1000000001"
    )
    assert monter.company == "Przykładowa Spółka sp. z o.o."
