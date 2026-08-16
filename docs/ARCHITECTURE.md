# Architecture decisions

Short records of the choices that shape this project, and why they were made.
Written so that a future reader — including the author — can tell which decisions
are load-bearing and which are incidental.

---

## 1. Tenant isolation belongs in the database

**Decision.** Every user-owned table is protected by PostgreSQL Row Level Security.
Policies restrict rows to `auth.uid()`. The application never filters by user id as
its only line of defence.

**Why.** Filtering in application code means one forgotten `WHERE` clause leaks
another person's data. Row Level Security moves the guarantee into the database:
the query is refused regardless of what the application asked for. For a tool
holding job-search history — employers, salaries, rejections — that difference
matters.

**Cost.** Every table needs an explicit policy. Anything using the service-role key
bypasses RLS, so that key stays server-side and its uses are deliberately few.

---

## 2. No mailbox credentials — ingest by forwarding

**Decision.** Offerly does not use Gmail OAuth and does not store IMAP passwords.
Each account gets a private forwarding address; the user sets a mail filter deciding
what reaches it.

**Why.** Reading a user's mailbox requires a Google *restricted scope*, which for a
production app means verification plus a recurring paid third-party security
assessment. That is out of reach for a project of this size — but the more important
reason is liability: storing tokens or passwords for other people's mailboxes makes
this service a target, and a breach would expose far more than job-search data.

Forwarding inverts the trust model. The user decides what Offerly sees, the service
never holds a credential, and it works with any mail provider rather than Gmail only.

**Cost.** One-time setup step for the user: creating a forwarding rule. Replies are
only visible if the user forwards them.

---

## 3. Offers and applications are separate entities

**Decision.** An `Offer` can exist without an `Application`.

**Why.** Most of the job-search funnel happens before applying: offers arrive, get
triaged, and most are rejected. Modelling only applications discards that, and with it
the ability to answer "what am I actually filtering out, and why?" It also allows an
inbox of incoming offers awaiting a decision.

---

## 4. Salary is structured, not a string

**Decision.** Salary is stored as amount, currency, gross/net, period (monthly or
hourly) and contract type — not free text.

**Why.** Employers ask inconsistently: gross monthly, net monthly, net hourly plus VAT
for B2B contracts. Comparing offers or answering "what did I declare there?" is
impossible once it is prose. Structured fields also allow conversion between
employment and B2B rates.

---

## 5. AI is optional and never sends anything

**Decision.** Classification and draft generation require the user's own API key. With
no key configured the application is fully functional. Generated follow-ups are saved
as drafts; nothing is ever sent automatically.

**Why.** A tool that might email an employer on your behalf is a tool you cannot trust
with your job search. Keeping AI optional also keeps the project usable for anyone
unwilling to send their correspondence to a model provider.

---

## 6. No scraping

**Decision.** Offers enter the system through forwarded alerts, manual entry or the
API — never by scraping job boards.

**Why.** Job boards prohibit automated access and enforce it with account bans. A tool
that risks its user's job-board account to save them a copy-paste is a bad trade.

---

## 7. Hosted first, self-hosting later

**Decision.** v0.1 targets a hosted deployment only. Database access is confined to a
single layer so a self-hosted PostgreSQL option can be added later without rewriting
business logic.

**Why.** Supporting both from day one doubles the surface area — two auth paths, two
deployment stories, two sets of documentation — and the largest risk to this project
is not shipping at all.
