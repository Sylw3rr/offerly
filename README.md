# Offerly

**Job application tracker that reads your inbox so you don't have to.**

Offerly keeps every job application in one place — which CV you sent, what salary you
quoted, and whether anyone replied. It ingests job alerts from your email and matches
incoming employer replies back to the application they belong to.

> Status: early development. See [Roadmap](#roadmap).

---

## The problem

Job hunting falls apart in the details, not the big decisions:

- You send twelve applications and lose track of which CV went where.
- One employer asks for gross monthly, the next for net hourly, the third for a B2B rate.
- An offer expires while it sits on your "maybe" list.
- A reply arrives, gets buried under job alerts, and you answer four days late.
- You never learn which CV version actually gets responses.

A spreadsheet records these things. It does not notice them.

## What Offerly does

**Track** — every application with company, role, source, date, CV version, declared
salary and deadline.

**Chase** — the dashboard lists only what needs doing today: offers about to close while
the application is still a draft, applications nobody has answered, forms left half-done.

**Reuse** — the answers every recruitment form asks for (notice period, expected rate,
GDPR clause) written once and copied afterwards, so October's answer matches August's.

**Ingest** — forward your job alerts to a private Offerly address; new offers land in a
triage inbox instead of your mailbox.

**Match** — incoming employer email is matched back to the application it belongs to,
with a confidence score. High confidence updates the status automatically; anything
uncertain waits for you to confirm.

**Measure** — response rate per CV version, per job board, per salary bracket. The
number that tells you whether your CV works.

## What Offerly deliberately does NOT do

These are design decisions, not missing features:

- **No portal scraping.** Job boards forbid it and ban accounts for it.
- **No auto-applying.** Applications go out under your name; you press send.
- **No sending email on your behalf.** Follow-ups are drafted, never sent.
- **No mailbox passwords or OAuth tokens.** Offerly cannot read your inbox — you
  forward what you choose. See [Security](#security-and-privacy).

## Stack

| Layer | Choice |
|---|---|
| Database, auth, row-level security | Supabase (PostgreSQL) |
| Backend / API | Python 3.11+, FastAPI |
| Web UI | HTMX + Jinja2 (no build step) |
| Email ingest | Cloudflare Email Routing → webhook |
| Mobile (planned) | Native client on the same REST API |

## Security and privacy

**Tenant isolation lives in the database, not the application.** Every table is
protected by PostgreSQL Row Level Security. A missing `WHERE` clause in application
code cannot leak another user's rows, because the database refuses the query.

**No mailbox credentials, ever.** Offerly does not use Gmail OAuth or store IMAP
passwords. Each account gets a private forwarding address; you decide with a mail
filter what reaches it. This removes the single largest liability such a tool can
carry — and it works with any mail provider, not just Gmail.

**Your data is yours to take and yours to destroy.** The account page exports every
application and saved answer as plain CSV, and closes the account for good — the
tables cascade from the account row, so deletion is immediate and total rather than a
flag on a row that stays behind.

## Quickstart

Requires Python 3.11+ and a free Supabase project.

```bash
git clone https://github.com/Sylw3rr/offerly.git
cd offerly
python -m venv .venv && .venv/Scripts/activate   # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                              # fill in your Supabase keys
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000.

Full setup, including database migrations and the forwarding address, is in
[`docs/SETUP.md`](docs/SETUP.md).

## Roadmap

| Version | Scope |
|---|---|
| v0.1 | Auth, application registry, statuses, CV versions, dashboard |
| v0.2 | Email forwarding, alert parsers, reply matching, reminders |
| v0.3 | Optional LLM classification, n8n workflow templates, public API |
| Later | Mobile client, self-hosted deployment |

Registration is invite-only during early development.

## Architecture notes

Design decisions and their reasoning are documented in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## License

MIT — see [LICENSE](LICENSE).

---

## Po polsku

**Offerly to tracker aplikacji o pracę, który czyta skrzynkę za Ciebie.**

Trzyma w jednym miejscu wszystkie wysłane zgłoszenia — z jakim CV poszły, jakie podałeś
oczekiwania i czy ktokolwiek odpisał. Zaciąga oferty z alertów mailowych i dopasowuje
przychodzące odpowiedzi pracodawców do właściwej aplikacji.

**Czego świadomie nie robi:** nie scrapuje portali, nie aplikuje za Ciebie, nie wysyła
maili w Twoim imieniu i nie przechowuje haseł ani tokenów do Twojej poczty. Zamiast
logowania do skrzynki dostajesz prywatny adres, na który sam przekierowujesz to, co
chcesz — dzięki temu narzędzie nie ma dostępu do reszty Twojej korespondencji.

**Izolacja danych** działa na poziomie bazy (PostgreSQL Row Level Security), a nie kodu
aplikacji. Błąd w zapytaniu nie ujawni cudzych danych, bo baza takie zapytanie odrzuci.

Instalacja i konfiguracja: [`docs/SETUP.md`](docs/SETUP.md).
Rejestracja na etapie wczesnego rozwoju odbywa się na zaproszenia.
