# Deploying

Offerly ships as a container. Whatever it runs on today should be replaceable
tomorrow without rewriting the deployment, so the `Dockerfile` is the contract
and nothing here depends on one provider's build system.

---

## It has to stay awake

This matters more than the price. Offerly receives mail through a webhook, and a
platform that sleeps an idle app answers that webhook with an error or a long
cold start. The mail router then rejects the message and the sending server
retries — sometimes for days, sometimes not at all.

So: **free tiers that sleep are the wrong tool here.** Render's free plan sleeps
after fifteen minutes. Railway and Fly both stay up on their paid starter plans,
which is the 20–40 zł a month the arithmetic in `PRODUCT.md` assumed.

## Railway, the short version

1. **New Project → Deploy from GitHub** and pick the repository. The
   `Dockerfile` is detected; there is nothing to configure about the build.
2. Set the variables below under **Variables**.
3. **Settings → Networking → Generate Domain**, or point `offerly.com.pl` at it.
4. Set `APP_BASE_URL` to whatever that domain turned out to be, and redeploy.

Fly is the same shape: `fly launch` detects the Dockerfile, `fly secrets set …`
for the variables.

## Variables

| Variable | Value |
|---|---|
| `APP_BASE_URL` | The public address, **with `https://`** |
| `APP_SECRET` | A long random string |
| `SUPABASE_URL` | From the Supabase dashboard |
| `SUPABASE_ANON_KEY` | Publishable key |
| `SUPABASE_SERVICE_KEY` | **Server only.** Bypasses row level security |
| `INGEST_DOMAIN` | `offerly.com.pl` |
| `INGEST_WEBHOOK_SECRET` | A long random string, shared with the mail Worker |
| `APP_ENV` | `production` (only affects what `/health` reports) |

`PORT` is set by the platform and read by the container; leave it alone.

Generate the two secrets rather than inventing them, and keep them out of any
chat window or commit:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

**`APP_BASE_URL` decides more than it looks like.** Session cookies are marked
`Secure` when it begins with `https://`, and password-recovery links are built
from it. Getting it wrong does not throw an error — it quietly hands out
cookies without protection, which is why it is read from the address rather
than from a separate flag someone could forget.

## After the first deploy

1. **Supabase → Authentication → URL Configuration → Redirect URLs**: add
   `https://<domain>/reset-password`. Recovery links go nowhere until it is
   listed.
2. **Cloudflare → Email Workers**: set `OFFERLY_ENDPOINT` to
   `https://<domain>/ingest/email`. Steps are in `SETUP.md`.
3. Check `https://<domain>/health` — it reports which pieces are configured:

   ```json
   {"status":"ok","env":"production","database_configured":true,
    "ingest_configured":true,"ai_enabled":false}
   ```

   `ingest_configured: false` after all of the above means the domain or the
   secret is missing, and the webhook will refuse everything until it is not.

## Why `--proxy-headers` is in the start command

Behind a load balancer the application is reached over plain HTTP, and without
being told otherwise it believes that is how the world sees it. Every absolute
URL it builds — the stylesheet included — then comes out as `http://` on an
`https://` page, where the browser refuses to load it. The site appears
completely unstyled and nothing in the logs looks wrong.

## Migrations

The container does not run them. They are applied deliberately, in order, from
`supabase/migrations/` — see `supabase/README.md`. A deployment that migrates
its own database on boot is a deployment that can destroy it on a bad rollout.
