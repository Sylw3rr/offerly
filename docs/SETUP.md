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

## Supabase setup

1. Create a project. Under **Security**, leave *Enable Data API* on, switch **off**
   *Automatically expose new tables*, and switch **on** *Enable automatic RLS*.
2. Apply the migrations in [`supabase/migrations/`](../supabase/migrations) in order —
   see [`supabase/README.md`](../supabase/README.md).
3. **Authentication → Sign In / Providers → disable "Allow new users to sign up".**
   The anon key is public by design, so leaving this on would let anyone create an
   account straight through the Supabase API and bypass the invite check.
4. Create yourself an invite code:

   ```sql
   insert into invites (code, note, max_uses) values ('YOUR-CODE', 'first account', 1);
   ```

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
| `SUPABASE_URL` | from v0.1 | Project URL, e.g. `https://<ref>.supabase.co` |
| `SUPABASE_ANON_KEY` | from v0.1 | Publishable key; row level security still applies |
| `SUPABASE_SERVICE_KEY` | from v0.1 | **Server only.** Bypasses row level security |

Both keys are on **Project Settings → API Keys**. Current projects issue keys in the
`sb_publishable_…` / `sb_secret_…` format; the pinned `supabase` version understands
these. Older releases only accept legacy JWT keys and fail with `Invalid API key`.

Where to find the project URL: **Project Settings → Data API**, or read it off the
dashboard address — `.../project/<ref>` means the URL is `https://<ref>.supabase.co`.
| `APP_SECRET` | yes | Long random string |
| `INGEST_DOMAIN` | from v0.2 | Domain for per-user forwarding addresses |
| `INGEST_WEBHOOK_SECRET` | from v0.2 | Verifies the inbound-email webhook |
| `ANTHROPIC_API_KEY` | no | Leave empty to run without AI features |

`SUPABASE_SERVICE_KEY` bypasses every row level security policy. It belongs on the
server and nowhere else — never in a browser, a mobile client, or a committed file.
