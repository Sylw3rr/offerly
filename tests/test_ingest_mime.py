"""Unpacking a raw message, which is how mail actually arrives."""

from app.ingest.mime import strip_html, trim_quoted, unpack

PLAIN = """From: Rekrutacja <rekrutacja@acme.pl>
To: fe57@offerly.com.pl
Subject: Twoja aplikacja
Content-Type: text/plain; charset="utf-8"
Content-Transfer-Encoding: 8bit

Dziękujemy za aplikację.
Niestety wybraliśmy innego kandydata.
"""

ENCODED_SUBJECT = """From: hr@acme.pl
Subject: =?UTF-8?Q?Zaproszenie_na_rozmow=C4=99?=
Content-Type: text/plain; charset="utf-8"

Zapraszamy na rozmowę.
"""

MULTIPART = """From: hr@acme.pl
Subject: Oferta
Content-Type: multipart/alternative; boundary="sep"

--sep
Content-Type: text/plain; charset="utf-8"

Wersja tekstowa wiadomości.
--sep
Content-Type: text/html; charset="utf-8"

<html><body><p>Wersja <b>HTML</b></p></body></html>
--sep--
"""

HTML_ONLY = """From: noreply@pracuj.pl
Subject: Nowe oferty
Content-Type: text/html; charset="utf-8"

<html><head><style>p{color:red}</style></head>
<body><p>Znaleźliśmy 12 ofert</p><div>dla Ciebie</div></body></html>
"""


def test_a_plain_message_gives_its_subject_and_body():
    subject, body = unpack(PLAIN)
    assert subject == "Twoja aplikacja"
    assert "wybraliśmy innego kandydata" in body


def test_an_encoded_subject_is_decoded():
    """Polish subjects arrive base64'd or quoted-printable more often than not."""
    subject, _ = unpack(ENCODED_SUBJECT)
    assert subject == "Zaproszenie na rozmowę"


def test_the_plain_part_is_preferred_over_the_html_one():
    _, body = unpack(MULTIPART)
    assert "Wersja tekstowa" in body
    assert "HTML" not in body


def test_an_html_only_message_is_flattened_into_something_matchable():
    subject, body = unpack(HTML_ONLY)
    assert subject == "Nowe oferty"
    assert "Znaleźliśmy 12 ofert" in body
    assert "dla Ciebie" in body
    assert "<" not in body


def test_styles_and_scripts_do_not_leak_into_the_text():
    assert "color" not in strip_html("<style>p{color:red}</style><p>widoczne</p>")


def test_entities_come_back_as_characters():
    assert "Kowalski & Syn" in strip_html("<p>Kowalski &amp; Syn</p>")


def test_the_quoted_thread_underneath_a_reply_is_dropped():
    """A rejection quoting your own application would otherwise contain both
    the refusal and whatever you originally wrote."""
    text = "Niestety odmawiamy.\n\n-----Original Message-----\nZapraszamy na rozmowę!"
    assert "Zapraszamy" not in trim_quoted(text)


def test_a_polish_quote_header_also_ends_the_message():
    text = "Odmowa.\nOd: Patryk\nZapraszamy na rozmowę"
    assert "Zapraszamy" not in trim_quoted(text)


def test_an_empty_message_does_not_raise():
    assert unpack("") == ("", "")
    assert unpack("   ") == ("", "")


def test_a_message_without_a_body_still_yields_its_subject():
    subject, body = unpack("From: a@b.pl\nSubject: Sam temat\n\n")
    assert subject == "Sam temat"
    assert body == ""
