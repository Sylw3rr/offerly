"""Working out what an arriving message is.

Rules rather than a model, for now. Most of this is decidable from the sender
and a handful of phrases, it costs nothing, it runs in tests without a network,
and it is honest about not knowing — anything it cannot place is kept as
`unknown` and shown to the person rather than guessed at.

A model can be dropped in later behind `read` without touching anything that
calls it; the cost of asking one is about 0.05 gr per message, so the reason to
start here is not the bill but the certainty.
"""

from dataclasses import dataclass

# Boards whose alerts we recognise, mapped to the `offer_source` enum.
BOARDS = {
    "pracuj.pl": "pracuj_pl",
    "praca.pl": "other",
    "olx.pl": "olx",
    "linkedin.com": "linkedin",
    "justjoin.it": "justjoin",
    "rocketjobs.pl": "rocketjobs",
    "nofluffjobs.com": "other",
    "indeed.com": "other",
    "theprotocol.it": "other",
}

# Senders that are never a person: no-reply addresses on a board's domain.
ROBOT_LOCALS = ("noreply", "no-reply", "no_reply", "powiadomienia", "alerty", "jobs-noreply")

KIND_OFFER = "offer_alert"
KIND_REPLY = "employer_reply"
KIND_UNKNOWN = "unknown"

# Phrases that place a reply, Polish first because that is the market this was
# built for. Order matters: a refusal often thanks you for applying, so the
# refusal has to be looked for before the acknowledgement.
REFUSAL = (
    "nie zakwalifikowal",
    "nie zostal zakwalifikowany",
    "rozpatrzona negatywnie",
    "decyzja jest negatywna",
    "nie bedziemy kontynuowac",
    "nie spelnia wymagan",
    "wybralismy innego kandydata",
    "zdecydowalismy sie na innego",
    "nie przechodzi do kolejnego etapu",
    "unfortunately",
    "we have decided not to",
    "not selected",
    "other candidates",
)

INVITATION = (
    "zapraszamy na rozmowe",
    "zapraszamy na spotkanie",
    "zaproszenie na rozmowe",
    "proponujemy termin",
    "chcielibysmy porozmawiac",
    "umowic sie na rozmowe",
    "rozmowa kwalifikacyjna",
    "invite you to an interview",
    "schedule a call",
    "next step",
)

ACKNOWLEDGEMENT = (
    "potwierdzamy otrzymanie",
    "otrzymalismy twoja aplikacje",
    "otrzymalismy zgloszenie",
    "dziekujemy za przeslanie",
    "dziekujemy za aplikacje",
    "twoja aplikacja zostala przyjeta",
    "we received your application",
    "thank you for applying",
)

# Reading these together is what distinguishes a board's alert from a person.
ALERT_MARKERS = (
    "nowe oferty",
    "oferty dla ciebie",
    "znalezlismy",
    "pasujace oferty",
    "nowe ogloszenia",
    "new jobs",
    "jobs for you",
    "recommended for you",
)


@dataclass(frozen=True)
class Message:
    """A message as the webhook receives it, before anything is decided."""

    to_address: str
    from_address: str
    subject: str = ""
    body: str = ""
    message_id: str = ""

    @property
    def from_domain(self) -> str:
        _, _, domain = self.from_address.partition("@")
        return domain.strip().lower()

    @property
    def from_local(self) -> str:
        local, _, _ = self.from_address.partition("@")
        return local.strip().lower()

    @property
    def token(self) -> str:
        """The part of the delivery address that says whose mailbox this is."""
        local, _, _ = self.to_address.partition("@")
        return local.strip().lower()


@dataclass(frozen=True)
class Reading:
    kind: str
    source: str | None = None  # the offer_source enum, when a board sent it
    status: str | None = None  # what the reply suggests the application became
    sure: bool = False  # false means show it, do not act on it


def fold(text: str) -> str:
    """Lower-case and strip Polish diacritics, so one phrase matches both ways.

    Employers write "zakwalifikował" and "zakwalifikowal" with equal
    conviction, and half of applicant tracking systems mangle the accents on
    the way out.
    """
    swaps = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")
    return text.translate(swaps).lower()


def _base_domain(domain: str) -> str:
    """`powiadomienia.pracuj.pl` and `pracuj.pl` are the same sender."""
    for board in BOARDS:
        if domain == board or domain.endswith("." + board):
            return board
    return domain


def looks_like_a_board(message: Message) -> str | None:
    """The `offer_source` this came from, if a board sent it."""
    return BOARDS.get(_base_domain(message.from_domain))


def read(message: Message) -> Reading:
    """Place a message, or admit that it cannot be placed."""
    haystack = fold(f"{message.subject}\n{message.body}")
    board = looks_like_a_board(message)

    if board is not None:
        # A board also sends "your application was forwarded" mail. Only treat
        # it as an alert when it reads like one.
        if any(marker in haystack for marker in ALERT_MARKERS):
            return Reading(kind=KIND_OFFER, source=board, sure=True)
        status = _reply_status(haystack)
        if status:
            return Reading(kind=KIND_REPLY, source=board, status=status, sure=True)
        return Reading(kind=KIND_UNKNOWN, source=board)

    status = _reply_status(haystack)
    if status:
        # A real person or their tracking system, on a company's own domain.
        robot = any(message.from_local.startswith(local) for local in ROBOT_LOCALS)
        return Reading(kind=KIND_REPLY, status=status, sure=not robot or status != "interview")

    return Reading(kind=KIND_UNKNOWN)


def _reply_status(haystack: str) -> str | None:
    """What an employer's message says happened.

    Refusals are looked for first: a rejection almost always opens by thanking
    you for your application, so checking for thanks first would file every "no"
    as an acknowledgement.
    """
    if any(phrase in haystack for phrase in REFUSAL):
        return "rejected"
    if any(phrase in haystack for phrase in INVITATION):
        return "interview"
    if any(phrase in haystack for phrase in ACKNOWLEDGEMENT):
        return "acknowledged"
    return None
