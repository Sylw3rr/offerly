"""The webhook forwarded mail arrives on.

Nobody is signed in when this is called — the caller is a mail router, not a
browser — so the shared secret is the only gate, and it fails closed when
unset. Everything written here goes in as the service role, which is why the
endpoint does as little as possible: verify, identify, store, and let the rest
happen where a person can see it.
"""

import hashlib
import hmac

from fastapi import APIRouter, Header, HTTPException, Request

from app.config import get_settings
from app.db import ingest_repo
from app.ingest import matching
from app.ingest.forwarding import looks_forwarded, unwrap
from app.ingest.mime import trim_quoted, unpack
from app.ingest.reading import KIND_REPLY, Message, read

router = APIRouter(tags=["ingest"])

# A forwarded email with attachments stripped has no business being larger.
MAX_BYTES = 512 * 1024


def _authentic(body: bytes, signature: str) -> bool:
    secret = get_settings().ingest_webhook_secret
    if not secret:
        # No secret configured means no way to tell friend from stranger, and
        # an open endpoint that writes to the database is worse than a missing
        # feature.
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, (signature or "").strip().lower())


@router.post("/ingest/email")
async def receive(request: Request, x_offerly_signature: str = Header("")):
    raw = await request.body()
    if len(raw) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="too large")
    if not _authentic(raw, x_offerly_signature):
        raise HTTPException(status_code=401, detail="bad signature")

    payload = await request.json()

    # The router forwards the message as it arrived and lets Python unpack it:
    # the standard library has met more badly-formed mail than anything we
    # would write inside a mail worker. `subject` and `text` remain accepted so
    # a simpler sender, or a test, can skip the raw form.
    subject, body = payload.get("subject") or "", payload.get("text") or ""
    raw = payload.get("raw") or ""
    if raw:
        parsed_subject, parsed_body = unpack(raw)
        subject, body = parsed_subject or subject, parsed_body or body

    forwarded = looks_forwarded(subject, body)
    if not forwarded:
        # Only a reply carries a quoted thread worth dropping.
        body = trim_quoted(body)

    message = Message(
        # The envelope recipient, not the To: header — a catch-all address is
        # reached by messages addressed to somewhere else entirely.
        to_address=(payload.get("to") or "").strip(),
        from_address=(payload.get("from") or "").strip(),
        subject=subject,
        body=body,
        message_id=(payload.get("message_id") or "").strip(),
    )

    # A message someone pressed Forward on arrives from them, not from the
    # board or employer that wrote it; the real sender is inside the text.
    if forwarded:
        message = unwrap(message)

    owner = ingest_repo.owner_of(message.token)
    if owner is None:
        # An address nobody owns. Answer the same way as success: a forwarding
        # address that says "no such account" is an address anyone can test
        # names against.
        return {"status": "accepted"}

    if ingest_repo.already_seen(owner, message.message_id):
        return {"status": "duplicate"}

    reading = read(message)
    match = None
    if reading.kind == KIND_REPLY:
        match = matching.find(
            ingest_repo.open_applications_for(owner),
            message.from_domain,
            message.subject,
            message.body,
        )

    ingest_repo.store(owner, message, reading, match)

    # Only a confident reading of a confident match moves anything. Everything
    # else waits in the inbox, which is the whole point of having one.
    if reading.kind == KIND_REPLY and reading.sure and match and match.sure and reading.status:
        ingest_repo.advance(owner, match.application_id, reading.status, message.subject)

    return {"status": "accepted"}
