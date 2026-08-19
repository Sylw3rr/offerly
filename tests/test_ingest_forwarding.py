"""Reading a message someone pressed Forward on.

The product asks people to forward their job alerts, so this is the ordinary
path. Pressing Forward writes a new message from the person doing it, which
means the envelope says gmail.com and the board that actually sent it is three
lines into the body.
"""

from app.ingest.forwarding import looks_forwarded, unwrap
from app.ingest.reading import KIND_OFFER, Message, read

GMAIL_FORWARD = Message(
    to_address="fe57@offerly.com.pl",
    from_address="patryk@gmail.com",
    subject="Fwd: Oferty na które czekasz - 19.08.2026",
    body=(
        "---------- Forwarded message ---------\n"
        "From: Wyszukiwane w Pracuj.pl <jobalert@wysylka.pracuj.pl>\n"
        "Date: Wed, Aug 19, 2026 at 3:58 AM\n"
        "Subject: Oferty na które czekasz - 19.08.2026\n"
        "To: patryk@gmail.com\n\n"
        "Nowe oferty pracy dopasowane do Twoich kryteriów.\n"
    ),
)

POLISH_CLIENT = Message(
    to_address="fe57@offerly.com.pl",
    from_address="patryk@gmail.com",
    subject="Fwd: Twoja aplikacja",
    body=(
        "---------- Przekazana wiadomość ---------\n"
        "Od: Rekrutacja <rekrutacja@acme.pl>\n"
        "Temat: Twoja aplikacja\n\n"
        "Niestety wybraliśmy innego kandydata.\n"
    ),
)


def test_a_forward_is_recognised():
    assert looks_forwarded(GMAIL_FORWARD.subject, GMAIL_FORWARD.body)


def test_an_ordinary_message_is_not_mistaken_for_one():
    assert not looks_forwarded("Twoja aplikacja", "Dziękujemy za zgłoszenie.")


def test_the_original_sender_replaces_the_person_who_forwarded_it():
    """Otherwise every forwarded alert looks like it came from Gmail, which
    identifies nobody."""
    unwrapped = unwrap(GMAIL_FORWARD)
    assert unwrapped.from_address == "jobalert@wysylka.pracuj.pl"
    assert unwrapped.from_domain == "wysylka.pracuj.pl"


def test_the_fwd_prefix_is_dropped_from_the_subject():
    assert unwrap(GMAIL_FORWARD).subject == "Oferty na które czekasz - 19.08.2026"


def test_a_forwarded_board_alert_is_finally_read_as_one():
    """The whole point: this arrived as unknown before the unwrapping existed."""
    reading = read(unwrap(GMAIL_FORWARD))
    assert reading.kind == KIND_OFFER
    assert reading.source == "pracuj_pl"


def test_polish_client_headers_are_understood():
    unwrapped = unwrap(POLISH_CLIENT)
    assert unwrapped.from_address == "rekrutacja@acme.pl"
    assert unwrapped.subject == "Twoja aplikacja"


def test_a_refusal_survives_being_forwarded():
    assert read(unwrap(POLISH_CLIENT)).status == "rejected"


def test_the_body_below_the_banner_is_kept():
    """It is the message, not a citation — trimming it would leave nothing."""
    assert "Nowe oferty pracy" in unwrap(GMAIL_FORWARD).body


def test_an_unreadable_original_sender_leaves_the_attribution_alone():
    """Better a message filed as unknown than one attributed to the wrong sender."""
    message = Message(
        to_address="fe57@offerly.com.pl",
        from_address="patryk@gmail.com",
        subject="Fwd: coś",
        body="---------- Forwarded message ---------\nnic tu nie ma\n",
    )
    assert unwrap(message).from_address == "patryk@gmail.com"


def test_a_sender_written_without_angle_brackets_is_still_found():
    message = Message(
        to_address="fe57@offerly.com.pl",
        from_address="patryk@gmail.com",
        subject="Fwd: x",
        body="---------- Forwarded message ---------\nFrom: noreply@olx.pl\nNowe oferty\n",
    )
    assert unwrap(message).from_address == "noreply@olx.pl"
