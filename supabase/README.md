# Database

## Applying migrations

Migrations are plain SQL, applied in filename order.

**Via the Supabase dashboard** (simplest):

1. Open your project → **SQL Editor** → **New query**
2. Paste the contents of a migration file
3. **Run**
4. Repeat for each file, in order

**Via the Supabase CLI:**

```bash
supabase link --project-ref <your-project-ref>
supabase db push
```

## Verifying row level security

After applying `0001_initial_schema.sql`, confirm every table is protected:

```sql
select tablename, rowsecurity
from pg_tables
where schemaname = 'public'
order by tablename;
```

`rowsecurity` must be `true` for every row. Then check the policies exist:

```sql
select tablename, policyname, cmd
from pg_policies
where schemaname = 'public'
order by tablename, cmd;
```

`invites` is the deliberate exception: row level security on, no policies. No
policy means no row is visible to `anon` or `authenticated`, which is what a
table only the service role touches should look like. The dashboard's linter
reports it as a finding; leave it.

## Verifying privileges

Two defaults have already had to be narrowed here, and both were invisible
until someone looked. After applying `0004` and `0005`:

```sql
-- Must both be false: a signed-in user cannot promote their own account.
select has_column_privilege('authenticated', 'public.profiles', 'plan', 'UPDATE'),
       has_column_privilege('authenticated', 'public.profiles', 'plan_until', 'UPDATE');

-- Must be false: invite codes cannot be guessed straight through the API.
select has_function_privilege('anon', 'public.redeem_invite(text, text)', 'EXECUTE');
```

The dashboard's **Advisors → Security** page catches this class of thing on its
own and is worth a look after every migration that adds a function or a grant.

## Design notes

**Every table keys on `user_id`** (`profiles` uses `id`, which is the auth user id).
Policies compare it against `auth.uid()`, so a query can only ever see its own rows.

**`status_events` is append-only.** It has read and insert policies but no update or
delete policy, so the history of an application cannot be rewritten from a client.

**`SUPABASE_SERVICE_KEY` bypasses all of this.** It exists for server-side jobs that
legitimately act across users — scheduled ghosting, inbound email routing. It must
never reach a browser or a mobile client.

## Granting a plan

There is no checkout. `plus` is set by hand, with the service role — the SQL
editor in the dashboard runs as that role:

```sql
update profiles set plan = 'plus', plan_until = null
 where id = (select id from auth.users where email = 'someone@example.com');
```

`plan_until` null means it does not lapse; set a timestamp to have it fall back
to `free` on its own. Nothing is deleted when it does.

The `authenticated` role cannot write either column — `0004_plans.sql` narrows
its UPDATE grant to `display_name` and `ghost_after_days`, so the public anon
key cannot promote an account straight through PostgREST.

## Migrations

| File | Adds |
|---|---|
| `0001_initial_schema.sql` | profiles, companies, documents, offers, applications, status_events, profile_answers, reminders + RLS |
| `0002_invites.sql` | invite codes and the `redeem_invite` function |
| `0003_grants.sql` | table privileges for the `authenticated` role |

## Privileges and policies are not the same thing

A missing `GRANT` produces `permission denied for table …` (SQLSTATE 42501) even
when the row level security policies are correct. `GRANT` decides whether a role may
touch a table; policies decide which rows it then sees. Both are required.

Projects created with *Automatically expose new tables* enabled receive these grants
implicitly. This project has that switched off, so `0003_grants.sql` states them
explicitly — the privileges live in the repository rather than in a dashboard
setting, and they mirror the policies exactly.
