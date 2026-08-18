"""Placing an arriving message — the part that must not guess confidently."""

from app.ingest.reading import KIND_OFFER, KIND_REPLY, KIND_UNKNOWN, Message, fold, read


def mail(sender, subject="", body="", to="abc123@in.offerly.com.pl"):
    return Message(to_address=to, from_address=sender, subject=subject, body=body)


# ---------------------------------------------------------------------------
# Whose mailbox
# ---------------------------------------------------------------------------


def test_the_token_is_read_off_the_delivery_address():
    assert mail("x@y.pl", to="a3f9c2e1b4d7@in.offerly.com.pl").token == "a3f9c2e1b4d7"


def test_the_sender_splits_into_a_person_and_a_domain():
    message = mail("Rekrutacja@Kariera.ACME.pl")
    assert message.from_domain == "kariera.acme.pl"
    assert message.from_local == "rekrutacja"


# ---------------------------------------------------------------------------
# Diacritics
# ---------------------------------------------------------------------------


def test_polish_accents_are_folded_so_one_phrase_matches_both_spellings():
    """Half of applicant tracking systems mangle the accents on the way out."""
    assert fold("nie zakwalifikował") == fold("nie zakwalifikowal")


def test_a_refusal_is_recognised_with_and_without_accents():
    with_accents = read(mail("hr@acme.pl", body="Niestety nie zakwalifikował się Pan dalej."))
    without = read(mail("hr@acme.pl", body="Niestety nie zakwalifikowal sie Pan dalej."))
    assert with_accents.status == without.status == "rejected"


# ---------------------------------------------------------------------------
# Board alerts
# ---------------------------------------------------------------------------


def test_an_alert_from_a_board_is_an_alert():
    reading = read(mail("noreply@pracuj.pl", subject="Nowe oferty pracy dla Ciebie"))
    assert reading.kind == KIND_OFFER
    assert reading.source == "pracuj_pl"
    assert reading.sure


def test_a_boards_subdomain_is_still_that_board():
    reading = read(mail("powiadomienia@notify.pracuj.pl", subject="Nowe oferty"))
    assert reading.source == "pracuj_pl"


def test_every_board_maps_onto_a_source_the_database_accepts():
    from app.ingest.reading import BOARDS

    allowed = {
        "pracuj_pl",
        "linkedin",
        "olx",
        "justjoin",
        "rocketjobs",
        "referral",
        "direct",
        "other",
    }
    assert set(BOARDS.values()) <= allowed


def test_a_board_can_also_carry_an_employers_answer():
    """Boards relay replies too; the sender alone does not settle it."""
    reading = read(
        mail(
            "noreply@pracuj.pl",
            subject="Odpowiedź na Twoją aplikację",
            body="Dziękujemy za przesłanie aplikacji.",
        )
    )
    assert reading.kind == KIND_REPLY
    assert reading.status == "acknowledged"


def test_a_board_message_that_is_neither_is_left_unplaced():
    reading = read(mail("noreply@pracuj.pl", subject="Zmiana regulaminu serwisu"))
    assert reading.kind == KIND_UNKNOWN


# ---------------------------------------------------------------------------
# What an employer said
# ---------------------------------------------------------------------------


def test_a_refusal_that_opens_by_thanking_you_is_still_a_refusal():
    """Rejections almost always thank you first — checking for thanks before
    the refusal would file every "no" as an acknowledgement."""
    reading = read(
        mail(
            "rekrutacja@acme.pl",
            subject="Twoja aplikacja",
            body="Dziękujemy za aplikację. Niestety wybraliśmy innego kandydata.",
        )
    )
    assert reading.kind == KIND_REPLY
    assert reading.status == "rejected"


def test_an_invitation_is_recognised():
    reading = read(mail("hr@acme.pl", body="Zapraszamy na rozmowę w przyszłym tygodniu."))
    assert reading.status == "interview"


def test_a_bare_acknowledgement_is_not_a_reply_from_a_person():
    reading = read(mail("hr@acme.pl", body="Potwierdzamy otrzymanie Twojego zgłoszenia."))
    assert reading.status == "acknowledged"


def test_english_wording_is_understood_too():
    reading = read(mail("careers@acme.com", body="Unfortunately we have decided not to proceed."))
    assert reading.status == "rejected"


def test_an_invitation_from_a_no_reply_address_is_flagged_rather_than_trusted():
    """A robot inviting you to an interview is worth a human's glance before
    the status moves on its own."""
    reading = read(mail("noreply@acme.pl", body="Zapraszamy na rozmowę."))
    assert reading.status == "interview"
    assert not reading.sure


def test_a_refusal_from_a_no_reply_address_is_still_trusted():
    reading = read(mail("noreply@acme.pl", body="Niestety wybraliśmy innego kandydata."))
    assert reading.sure


def test_anything_unrecognised_is_kept_rather_than_guessed_at():
    reading = read(mail("ktos@acme.pl", subject="Faktura 12/2026", body="W załączeniu."))
    assert reading.kind == KIND_UNKNOWN
    assert reading.status is None
    assert not reading.sure
