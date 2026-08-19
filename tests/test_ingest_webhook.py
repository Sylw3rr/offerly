"""The webhook: the one endpoint nobody signs in to.

The shared secret is the only gate, so most of what matters here is what
happens when it is wrong, missing, or nearly right.
"""

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import ingest_repo
from app.main import app
from app.web import routes_ingest

SECRET = "test-secret"


def sign(payload: dict) -> tuple[bytes, str]:
    raw = json.dumps(payload).encode()
    return raw, hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()


@pytest.fixture
def client(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "ingest_webhook_secret", SECRET, raising=False)

    stored, advanced = [], []
    monkeypatch.setattr(ingest_repo, "owner_of", lambda token: "u1" if token == "abc123" else None)
    monkeypatch.setattr(ingest_repo, "already_seen", lambda user_id, message_id: False)
    monkeypatch.setattr(ingest_repo, "open_applications_for", lambda user_id: APPLICATIONS)
    monkeypatch.setattr(
        ingest_repo, "store", lambda u, m, r, match: stored.append((m, r, match)) or "e1"
    )
    monkeypatch.setattr(ingest_repo, "advance", lambda u, a, s, subject: advanced.append((a, s)))

    client = TestClient(app)
    client.stored, client.advanced = stored, advanced
    return client


APPLICATIONS = [
    {
        "id": "a1",
        "status": "submitted",
        "offers": {"title": "Rola", "companies": {"name": "Acme", "email_domain": "acme.pl"}},
    }
]


def post(client, payload, signature=None):
    raw, good = sign(payload)
    return client.post(
        "/ingest/email",
        content=raw,
        headers={
            "X-Offerly-Signature": good if signature is None else signature,
            "Content-Type": "application/json",
        },
    )


def message(**over):
    base = {
        "to": "abc123@in.offerly.com.pl",
        "from": "rekrutacja@acme.pl",
        "subject": "Twoja aplikacja",
        "text": "Niestety wybraliśmy innego kandydata.",
        "message_id": "<1@acme.pl>",
    }
    base.update(over)
    return base


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


def test_a_wrong_signature_is_refused(client):
    assert post(client, message(), signature="deadbeef").status_code == 401
    assert client.stored == []


def test_a_missing_signature_is_refused(client):
    assert post(client, message(), signature="").status_code == 401


def test_without_a_configured_secret_the_endpoint_refuses_everything(client, monkeypatch):
    """An open endpoint that writes to the database is worse than a missing
    feature, so it fails closed rather than open."""
    monkeypatch.setattr(get_settings(), "ingest_webhook_secret", "", raising=False)
    assert post(client, message()).status_code == 401


def test_an_oversized_body_is_refused_before_it_is_parsed(client):
    payload = message(text="x" * (routes_ingest.MAX_BYTES + 10))
    assert post(client, payload).status_code == 413


# ---------------------------------------------------------------------------
# Whose mail
# ---------------------------------------------------------------------------


def test_an_unknown_address_is_answered_exactly_like_a_known_one(client):
    """Otherwise the endpoint becomes a way to test which addresses exist."""
    known = post(client, message())
    unknown = post(client, message(to="nobody@in.offerly.com.pl"))
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()


def test_mail_for_nobody_is_not_stored(client):
    post(client, message(to="nobody@in.offerly.com.pl"))
    assert client.stored == []


def test_the_same_message_twice_is_only_acted_on_once(client, monkeypatch):
    """Forwarding rules loop and webhooks retry; a refusal counted twice would
    write the history twice."""
    monkeypatch.setattr(ingest_repo, "already_seen", lambda user_id, message_id: True)
    response = post(client, message())
    assert response.json()["status"] == "duplicate"
    assert client.advanced == []


# ---------------------------------------------------------------------------
# What it does with it
# ---------------------------------------------------------------------------


def test_a_confident_refusal_from_the_companys_domain_moves_the_application(client):
    post(client, message())
    assert client.advanced == [("a1", "rejected")]


def test_a_suggestion_is_stored_but_never_acted_on(client):
    """Matched only by name, from a personal address: worth showing, not worth
    editing someone's record over."""
    post(client, message(**{"from": "rekruter@gmail.com", "text": "Acme: niestety odmawiamy."}))
    assert client.advanced == []
    assert client.stored


def test_an_unplaceable_message_is_still_kept(client):
    post(client, message(subject="Faktura", text="W załączeniu.", message_id="<2@acme.pl>"))
    assert client.stored
    assert client.advanced == []


def test_a_board_alert_does_not_move_any_application(client):
    post(client, message(**{"from": "noreply@pracuj.pl", "subject": "Nowe oferty pracy"}))
    assert client.advanced == []


# ---------------------------------------------------------------------------
# Forwarded mail — the ordinary path, since the product asks people to forward
# ---------------------------------------------------------------------------


def test_a_forwarded_board_alert_is_credited_to_the_board(client):
    """Arrives from the person's own Gmail; the board is inside the text."""
    post(
        client,
        message(
            **{
                "from": "patryk@gmail.com",
                "subject": "Fwd: Oferty na ktore czekasz",
                "text": (
                    "---------- Forwarded message ---------\n"
                    "From: Pracuj.pl <jobalert@wysylka.pracuj.pl>\n"
                    "Subject: Oferty na ktore czekasz\n\n"
                    "Nowe oferty pracy dla Ciebie.\n"
                ),
                "message_id": "<fwd-1@mail.gmail.com>",
            }
        ),
    )
    seen, reading, _ = client.stored[-1]
    assert seen.from_domain == "wysylka.pracuj.pl"
    assert reading.kind == "offer_alert"
    assert reading.source == "pracuj_pl"


def test_a_forwarded_refusal_still_reaches_the_right_application(client):
    post(
        client,
        message(
            **{
                "from": "patryk@gmail.com",
                "subject": "Fwd: Twoja aplikacja",
                "text": (
                    "---------- Przekazana wiadomosc ---------\n"
                    "Od: Rekrutacja <rekrutacja@acme.pl>\n"
                    "Temat: Twoja aplikacja\n\n"
                    "Niestety wybralismy innego kandydata.\n"
                ),
                "message_id": "<fwd-2@mail.gmail.com>",
            }
        ),
    )
    assert client.advanced == [("a1", "rejected")]


def test_a_reply_still_has_its_quoted_thread_trimmed(client):
    """Unwrapping forwards must not stop replies being trimmed: a rejection
    quoting your own application would otherwise match both ways."""
    post(
        client,
        message(
            text=(
                "Niestety wybralismy innego kandydata.\n"
                "-----Original Message-----\n"
                "Zapraszamy na rozmowe!\n"
            ),
            message_id="<reply-1@acme.pl>",
        ),
    )
    seen, reading, _ = client.stored[-1]
    assert "Zapraszamy" not in seen.body
    assert reading.status == "rejected"
