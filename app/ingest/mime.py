"""Getting a subject and a readable body out of a raw message.

The mail router forwards the message exactly as it arrived and lets this do the
unpacking. Python's `email` module is in the standard library and has spent
twenty years meeting badly-formed mail; a JavaScript equivalent inside the
router would be a dependency, a build step, and a second place for the parsing
to be wrong.
"""

import re
from email import message_from_bytes, policy
from email.message import EmailMessage

TAGS = re.compile(r"<[^>]+>")
SPACES = re.compile(r"[ \t\r\f\v]+")
BLANK_LINES = re.compile(r"\n{3,}")

# Everything after one of these is the quoted message underneath a reply, and
# quoting the whole thread back makes every phrase match every message.
QUOTE_MARKERS = (
    "\n-----original message-----",
    "\n----- original message -----",
    "\nod: ",
    "\nwiadomość napisana przez",
    "\nwiadomosc napisana przez",
    "\non wrote:",
    "\n> ",
)


def strip_html(html: str) -> str:
    """Enough of the text to match phrases against — not a rendering."""
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>", "\n", text)
    text = TAGS.sub(" ", text)
    for entity, character in (
        ("&nbsp;", " "),
        ("&amp;", "&"),
        ("&lt;", "<"),
        ("&gt;", ">"),
        ("&quot;", '"'),
        ("&#39;", "'"),
    ):
        text = text.replace(entity, character)
    return text


def tidy(text: str) -> str:
    text = SPACES.sub(" ", text.replace("\r\n", "\n").replace("\r", "\n"))
    text = "\n".join(line.strip() for line in text.split("\n"))
    return BLANK_LINES.sub("\n\n", text).strip()


def trim_quoted(text: str) -> str:
    """Drop the thread quoted underneath a reply.

    A rejection that quotes your original application would otherwise contain
    both "we regret" and whatever you wrote, and the phrase matching would have
    to guess which one it is answering.
    """
    lowered = text.lower()
    cut = len(text)
    for marker in QUOTE_MARKERS:
        found = lowered.find(marker)
        if found != -1:
            cut = min(cut, found)
    return text[:cut].strip()


def unpack(raw: str) -> tuple[str, str]:
    """Return the subject and the readable body of a raw message."""
    if not raw.strip():
        return "", ""

    # Parsed from bytes, never from a string. Given a message that declares
    # 8bit transfer encoding, `message_from_string` hands back every non-ASCII
    # character as a six-character backslash-u escape rather than the letter —
    # which would have mangled every Polish word in everything this receives.
    message: EmailMessage = message_from_bytes(
        raw.encode("utf-8", "surrogateescape"), policy=policy.default
    )
    subject = str(message.get("Subject") or "").strip()

    body = ""
    try:
        part = message.get_body(preferencelist=("plain", "html"))
    except Exception:
        part = None

    if part is not None:
        try:
            content = part.get_content()
        except Exception:
            content = ""
        if part.get_content_type() == "text/html":
            content = strip_html(content)
        body = content
    elif not message.is_multipart():
        payload = message.get_payload(decode=True)
        if isinstance(payload, bytes):
            body = payload.decode(message.get_content_charset() or "utf-8", errors="replace")
        else:
            body = str(payload or "")
        if message.get_content_type() == "text/html":
            body = strip_html(body)

    # Quotes are trimmed later, by the caller — a forwarded message keeps
    # everything below the banner, because that is the message.
    return subject, tidy(body)
