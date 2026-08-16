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

## Design notes

**Every table keys on `user_id`** (`profiles` uses `id`, which is the auth user id).
Policies compare it against `auth.uid()`, so a query can only ever see its own rows.

**`status_events` is append-only.** It has read and insert policies but no update or
delete policy, so the history of an application cannot be rewritten from a client.

**`SUPABASE_SERVICE_KEY` bypasses all of this.** It exists for server-side jobs that
legitimately act across users — scheduled ghosting, inbound email routing. It must
never reach a browser or a mobile client.

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
