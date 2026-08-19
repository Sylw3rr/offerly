"""Looking underneath a forwarded message.

Pressing Forward in a mail client does not relay the original — it writes a new
message from you, with the old one quoted in the body. The envelope then says
`gmail.com`, which identifies nobody, and the job board that actually sent it is
three lines into the text.

Since the whole product asks people to forward their job alerts, this is the
ordinary case rather than an exotic one.
"""

import re
from dataclasses import replace

from app.ingest.reading import Message, fold

# What each mail client writes above the message it is passing on. Written
# without accents and matched against folded text, because clients disagree
# about them and `fold` preserves length, so found positions still line up.
BANNERS = (
    "---------- forwarded message ---------",
    "---------- przekazana wiadomosc ---------",
    "-------- forwarded message --------",
    "-------- wiadomosc przekazana dalej --------",
    "begin forwarded message:",
    "----- original message -----",
    "-----wiadomosc oryginalna-----",
)

SENDER = re.compile(r"^(?:from|od)\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
TOPIC = re.compile(r"^(?:subject|temat)\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
ADDRESS = re.compile(r"<\s*([^<>@\s]+@[^<>\s]+?)\s*>|([^<>@\s]+@[^<>\s]+)")

# "Fwd:", "FW:", "PD:" — the prefixes clients put on a forwarded subject.
PREFIX = re.compile(r"^\s*(?:fwd?|fw|pd|odp)\s*:\s*", re.IGNORECASE)


def _first_address(line: str) -> str:
    found = ADDRESS.search(line)
    if not found:
        return ""
    return (found.group(1) or found.group(2) or "").strip().strip(".,;")


def looks_forwarded(subject: str, body: str) -> bool:
    folded = fold(f"{subject}\n{body}")
    return any(banner in folded for banner in BANNERS)


def unwrap(message: Message) -> Message:
    """Return the message as its original sender wrote it, where that is legible.

    Only the sender and subject are replaced; the body keeps the forwarded text,
    because that is where the offers are. If the original sender cannot be read,
    the message is returned untouched rather than guessed at.
    """
    if not looks_forwarded(message.subject, message.body):
        return message

    folded = fold(message.body)
    start = min(
        (folded.find(banner) for banner in BANNERS if folded.find(banner) != -1),
        default=-1,
    )
    if start == -1:
        return message

    # The headers of the message being passed on sit just under the banner.
    head = message.body[start : start + 1200]

    sender = ""
    found = SENDER.search(head)
    if found:
        sender = _first_address(found.group(1))

    subject = message.subject
    found = TOPIC.search(head)
    if found:
        subject = found.group(1).strip()
    subject = PREFIX.sub("", subject).strip()

    if not sender:
        # Without a legible original sender there is nothing to gain and a
        # wrong attribution to lose.
        return replace(message, subject=subject)

    return replace(message, from_address=sender, subject=subject)
