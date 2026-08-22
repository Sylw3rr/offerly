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

## Password recovery

Recovery is handled server-side, so the emailed link must carry a token hash rather
than a session in the URL fragment. Two settings in the Supabase dashboard:

1. **Authentication → URL Configuration → Redirect URLs** — add
   `<APP_BASE_URL>/reset-password`, e.g. `http://127.0.0.1:8000/reset-password`.
   Supabase refuses to redirect anywhere that is not on this list.
2. **Authentication → Emails → Reset Password** — replace the link in the template so
   it carries the token hash:

   ```html
   <a href="{{ .SiteURL }}/reset-password?token_hash={{ .TokenHash }}&type=recovery">
     Set a new password
   </a>
   ```

   The default template uses `{{ .ConfirmationURL }}`, which returns the tokens in the
   URL fragment — the part a browser never sends to the server. Offerly would see a
   link with nothing in it and say the token is missing.

Without SMTP configured, Supabase's shared sender is rate-limited to a few messages an
hour and is fine for trying this out. Any real deployment needs its own SMTP under
**Authentication → Emails → SMTP Settings**.

## Receiving forwarded mail

Each account gets a private address, `<token>@<INGEST_DOMAIN>`. Nothing reads a
mailbox — the person sets a filter in their own and decides what reaches it.

1. Point `INGEST_DOMAIN` at a domain (or subdomain) whose mail you control, and
   set `INGEST_WEBHOOK_SECRET` to a long random string. **Without the secret the
   endpoint refuses everything**, on purpose: an open endpoint that writes to
   the database is worse than a missing feature.
2. Move the domain's nameservers to Cloudflare, then **Email → Email Routing →
   Enable**. Cloudflare sets the MX records itself.
3. **Email Workers → Create**, paste [`workers/email-router.js`](../workers/email-router.js),
   and set two variables on it: `OFFERLY_ENDPOINT` (`https://<host>/ingest/email`)
   and `OFFERLY_SECRET` (the same string as `INGEST_WEBHOOK_SECRET`).
4. **Routing rules → Catch-all → Send to a Worker**, and choose it.

   The Worker forwards the message as it arrived — Python unpacks the MIME,
   because the standard library has met far more broken mail than anything
   worth maintaining in JavaScript. It signs the exact body it sends with
   HMAC-SHA256, hex-encoded, in `X-Offerly-Signature`.

   Keeping a normal address for yourself is a **custom address** rule above the
   catch-all: `kontakt@` → your own inbox. Rules are matched in order.

   The endpoint also accepts `{"to", "from", "subject", "text"}` without the raw
   message, which is what the tests use and what a simpler sender can post.
5. Find your own address with:

   ```sql
   select ingest_token from profiles where id = auth.uid();
   ```

The endpoint answers `202`-style `{"status": "accepted"}` for an address nobody
owns, exactly as it does for a real one — otherwise it would be a way to test
which addresses exist. A message that arrives twice is stored once, because
forwarding rules loop and webhooks retry.

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
| `APP_SECRET` | yes | Long random string |
| `APP_BASE_URL` | yes | Where this installation answers; password reset links point back here |
| `INGEST_DOMAIN` | from v0.2 | Domain for per-user forwarding addresses |
| `INGEST_WEBHOOK_SECRET` | from v0.2 | Verifies the inbound-email webhook |
| `ANTHROPIC_API_KEY` | no | Leave empty to run without AI features |
| `GEMINI_API_KEY` | no | Reads adverts out of forwarded alerts. Empty means only boards with a written parser are read |
| `GEMINI_MODEL` | no | Defaults to `gemini-2.0-flash` |
| `RESEND_API_KEY` | no | Reminder mail. Empty means nothing is sent |
| `MAIL_FROM` | no | Sender address, e.g. `Offerly <przypomnienia@offerly.com.pl>` |

Both keys are on **Project Settings → API Keys**. Current projects issue keys in the
`sb_publishable_…` / `sb_secret_…` format; the pinned `supabase` version understands
these. Older releases only accept legacy JWT keys and fail with `Invalid API key`.

Where to find the project URL: **Project Settings → Data API**, or read it off the
dashboard address — `.../project/<ref>` means the URL is `https://<ref>.supabase.co`.

`SUPABASE_SERVICE_KEY` bypasses every row level security policy. It belongs on the
server and nowhere else — never in a browser, a mobile client, or a committed file.
