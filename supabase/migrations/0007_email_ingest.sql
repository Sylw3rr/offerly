-- Offerly — receiving forwarded mail
--
-- Each account gets a private address. The person sets a filter in their own
-- mailbox deciding what reaches it; Offerly never holds a credential and never
-- sees the rest of their correspondence. See docs/ARCHITECTURE.md, decision 2.

-- ---------------------------------------------------------------------------
-- The address
-- ---------------------------------------------------------------------------

alter table profiles
  -- The local part of the forwarding address: <token>@<INGEST_DOMAIN>. Unique
  -- across all accounts, because it is the only thing identifying who a
  -- forwarded message belongs to.
  add column ingest_token text unique;

create or replace function new_ingest_token()
returns text
language sql
volatile
as $$
  select encode(gen_random_bytes(6), 'hex');
$$;

-- Everyone who already has an account gets one too.
update profiles set ingest_token = new_ingest_token() where ingest_token is null;

alter table profiles alter column ingest_token set default new_ingest_token();
alter table profiles alter column ingest_token set not null;

-- ---------------------------------------------------------------------------
-- What arrives
-- ---------------------------------------------------------------------------

create type inbound_kind as enum (
  'offer_alert',     -- a job board's notification, holding one or more offers
  'employer_reply',  -- a human, or their applicant tracking system, answering
  'unknown'          -- kept, shown, and left for the person to judge
);

create table inbound_emails (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null references auth.users(id) on delete cascade,

  -- From the message itself. `message_id` is what stops a forwarding loop or a
  -- retrying webhook from creating the same offer twice.
  message_id   text,
  from_address text not null,
  from_domain  text,
  subject      text,
  body         text,

  kind         inbound_kind not null default 'unknown',
  -- Where it ended up, when it led anywhere.
  offer_id       uuid references offers(id) on delete set null,
  application_id uuid references applications(id) on delete set null,
  -- Set when a person has looked at it, or when it turned into something.
  handled_at   timestamptz,

  received_at  timestamptz not null default now(),
  created_at   timestamptz not null default now(),

  unique (user_id, message_id)
);

create index inbound_emails_user_idx on inbound_emails (user_id, received_at desc);
create index inbound_emails_pending_idx on inbound_emails (user_id, kind)
  where handled_at is null;

-- ---------------------------------------------------------------------------
-- Row level security
--
-- The person may read and tidy their own mail. Nothing writes here from a
-- browser: messages arrive through the webhook, which runs as the service role.
-- ---------------------------------------------------------------------------

alter table inbound_emails enable row level security;

create policy "inbound_emails: read own" on inbound_emails
  for select to authenticated using ((select auth.uid()) = user_id);
create policy "inbound_emails: update own" on inbound_emails
  for update to authenticated using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);
create policy "inbound_emails: delete own" on inbound_emails
  for delete to authenticated using ((select auth.uid()) = user_id);

-- Matching the policies exactly: no insert privilege, because nothing signed in
-- has any business inventing received mail.
grant select, update, delete on public.inbound_emails to authenticated;
grant select, insert, update, delete on public.inbound_emails to service_role;

-- ---------------------------------------------------------------------------
-- Matching replies back to applications
--
-- `companies.email_domain` has been in the schema since 0001 waiting for this.
-- An index makes the lookup on every arriving message cheap.
-- ---------------------------------------------------------------------------

create index if not exists companies_domain_lookup_idx
  on companies (user_id, lower(email_domain))
  where email_domain is not null;
