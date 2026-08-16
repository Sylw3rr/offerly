# Setup

> This document grows with the project. Right now it covers running the API skeleton
> locally. Database and email ingest steps are added in v0.1 and v0.2.

## Requirements

- Python 3.11 or newer
- A free [Supabase](https://supabase.com) project (needed from v0.1 onwards)

## Local run

```bash
git clone https://github.com/Sylw3rr/offerly.git
cd offerly

python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install -r requirements-dev.txt
cp .env.example .env
```

Open `.env` and fill in what you have. The skeleton starts with empty values —
`/health` reports which parts are configured.

```bash
uvicorn app.main:app --reload
```

- API: http://127.0.0.1:8000
- Interactive docs: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health

## Tests and linting

```bash
pytest -q
ruff check .
ruff format .
```

CI runs the same three commands on every push and pull request.

## Environment variables

| Variable | Required | Notes |
|---|---|---|
| `SUPABASE_URL` | from v0.1 | Project URL |
| `SUPABASE_ANON_KEY` | from v0.1 | Public key; row level security still applies |
| `SUPABASE_SERVICE_KEY` | from v0.1 | **Server only.** Bypasses row level security |
| `APP_SECRET` | yes | Long random string |
| `INGEST_DOMAIN` | from v0.2 | Domain for per-user forwarding addresses |
| `INGEST_WEBHOOK_SECRET` | from v0.2 | Verifies the inbound-email webhook |
| `ANTHROPIC_API_KEY` | no | Leave empty to run without AI features |

`SUPABASE_SERVICE_KEY` bypasses every row level security policy. It belongs on the
server and nowhere else — never in a browser, a mobile client, or a committed file.
