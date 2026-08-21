-- Offers collected out of forwarded alerts.
--
-- Two things are needed that the original schema did not have: a way to know
-- an advert has been seen before, and a way to know an advert was collected
-- rather than typed in.
--
-- `external_id` is the board's own identifier, taken from the advert's link
-- (pracuj.pl writes it as `,oferta,1005033672`). It is what makes tomorrow's
-- digest, which repeats half of today's, add nothing. It is unique per user
-- and not globally: two people tracking the same advert each own their row,
-- and row level security depends on that staying true.

alter table offers
  add column if not exists external_id text,
  -- Which arriving message produced this row. Null for anything a person
  -- entered themselves, which is also how the two are told apart.
  add column if not exists collected_from uuid references inbound_emails(id) on delete set null;

-- Partial, because the overwhelming majority of rows are hand-entered and have
-- no external id; a plain unique index would collapse them all into one.
create unique index if not exists offers_user_external_idx
  on offers (user_id, external_id)
  where external_id is not null;

-- The inbox lists what a message produced.
create index if not exists offers_collected_from_idx
  on offers (collected_from)
  where collected_from is not null;

-- Triage reads "everything still untouched", which is the common query on this
-- table now that adverts arrive on their own.
create index if not exists offers_user_status_idx on offers (user_id, status);

-- Both new columns are written by the ingest worker as the service role, never
-- by the browser. `offers` currently carries a blanket UPDATE grant, which
-- would let a client rewrite the identity of its own rows — pinning
-- `external_id` to an advert that has not arrived yet makes the real one look
-- like a duplicate and vanish. Postgres cannot revoke one column out of a
-- table-wide grant, so the grant is narrowed to the columns a person actually
-- edits. This is the same correction 0004 made to `profiles.plan`.
revoke update on public.offers from authenticated;

grant update (
  company_id, title, source, url, location, mode, level,
  salary_min, salary_max, salary_currency, salary_kind, salary_period,
  contract, status, discard_reason, expires_at, description, updated_at
) on public.offers to authenticated;
