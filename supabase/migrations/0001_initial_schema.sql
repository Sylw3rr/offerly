-- Offerly — initial schema (v0.1)
--
-- Covers the manual tracking core: companies, offers, applications, status
-- history, documents, reusable form answers and reminders.
-- Email ingest tables arrive in a later migration.
--
-- Every user-owned table carries `user_id` and is protected by row level
-- security. Isolation is enforced by the database, never by application code
-- alone — see docs/ARCHITECTURE.md, decision 1.

-- ---------------------------------------------------------------------------
-- Enums
-- ---------------------------------------------------------------------------

create type offer_source as enum (
  'pracuj_pl', 'linkedin', 'olx', 'justjoin', 'rocketjobs', 'referral', 'direct', 'other'
);

create type offer_status as enum (
  'new',          -- just arrived, not triaged
  'shortlisted',  -- worth applying to
  'discarded',    -- rejected by the user, with a reason
  'expired',      -- deadline passed before applying
  'applied'       -- an application exists
);

create type work_mode as enum ('onsite', 'hybrid', 'remote');

create type seniority as enum ('intern', 'junior', 'mid', 'senior', 'lead');

create type contract_type as enum ('employment', 'b2b', 'mandate', 'task', 'internship', 'other');

create type salary_kind as enum ('gross', 'net');

create type salary_period as enum ('hour', 'month', 'year');

create type application_status as enum (
  'draft',        -- being prepared
  'blocked',      -- needs a manual step: external form, file upload, phone call
  'submitted',    -- sent
  'acknowledged', -- automated confirmation received
  'replied',      -- a human responded
  'interview',
  'offer',
  'rejected',
  'ghosted',      -- no answer within the configured window
  'withdrawn'     -- withdrawn by the user
);

create type document_kind as enum ('cv', 'cover_letter', 'other');

create type status_source as enum ('manual', 'email_match', 'system');

-- ---------------------------------------------------------------------------
-- Helper: keep updated_at honest
-- ---------------------------------------------------------------------------

create or replace function set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- ---------------------------------------------------------------------------
-- profiles — one row per auth user
-- ---------------------------------------------------------------------------

create table profiles (
  id            uuid primary key references auth.users(id) on delete cascade,
  display_name  text,
  -- Mark an application as ghosted after this many days without a reply.
  ghost_after_days smallint not null default 21 check (ghost_after_days between 1 and 365),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

create trigger profiles_updated_at
  before update on profiles
  for each row execute function set_updated_at();

-- Create the profile row automatically on sign-up.
create or replace function handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, display_name)
  values (new.id, new.raw_user_meta_data ->> 'display_name');
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function handle_new_user();

-- ---------------------------------------------------------------------------
-- companies
-- ---------------------------------------------------------------------------

create table companies (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null references auth.users(id) on delete cascade,
  name         text not null check (length(trim(name)) > 0),
  -- Used to match incoming email back to an application (v0.2).
  email_domain text,
  website      text,
  notes        text,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  unique (user_id, name)
);

create index companies_user_id_idx on companies (user_id);
create index companies_email_domain_idx on companies (user_id, email_domain)
  where email_domain is not null;

create trigger companies_updated_at
  before update on companies
  for each row execute function set_updated_at();

-- ---------------------------------------------------------------------------
-- documents — CV and cover letter versions
-- ---------------------------------------------------------------------------

create table documents (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users(id) on delete cascade,
  kind        document_kind not null default 'cv',
  label       text not null check (length(trim(label)) > 0),
  -- Path in Supabase Storage, or null when the user only tracks the name.
  storage_path text,
  is_active   boolean not null default true,
  notes       text,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create index documents_user_id_idx on documents (user_id);

create trigger documents_updated_at
  before update on documents
  for each row execute function set_updated_at();

-- ---------------------------------------------------------------------------
-- offers — may exist without an application
-- ---------------------------------------------------------------------------

create table offers (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null references auth.users(id) on delete cascade,
  company_id    uuid references companies(id) on delete set null,

  title         text not null check (length(trim(title)) > 0),
  source        offer_source not null default 'other',
  url           text,
  location      text,
  mode          work_mode,
  level         seniority,

  salary_min      numeric(10, 2),
  salary_max      numeric(10, 2),
  salary_currency char(3) not null default 'PLN',
  salary_kind     salary_kind,
  salary_period   salary_period,
  contract        contract_type,

  status          offer_status not null default 'new',
  discard_reason  text,
  expires_at      date,
  description     text,

  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),

  constraint salary_range_ordered
    check (salary_min is null or salary_max is null or salary_min <= salary_max)
);

create index offers_user_status_idx on offers (user_id, status);
create index offers_user_expires_idx on offers (user_id, expires_at)
  where expires_at is not null;
create index offers_company_idx on offers (company_id);

create trigger offers_updated_at
  before update on offers
  for each row execute function set_updated_at();

-- ---------------------------------------------------------------------------
-- applications
-- ---------------------------------------------------------------------------

create table applications (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users(id) on delete cascade,
  offer_id    uuid not null references offers(id) on delete cascade,

  cv_document_id           uuid references documents(id) on delete set null,
  cover_letter_document_id uuid references documents(id) on delete set null,

  status        application_status not null default 'draft',
  submitted_at  timestamptz,

  -- What was actually declared to this employer. Kept separate from the
  -- offer's advertised range: employers ask in different units, and knowing
  -- what you quoted is what makes the number useful later.
  declared_salary        numeric(10, 2),
  declared_salary_kind   salary_kind,
  declared_salary_period salary_period,
  declared_contract      contract_type,

  -- Why this application cannot proceed without the user, when status = 'blocked'.
  blocked_reason text,

  notes       text,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),

  -- One application per offer keeps the funnel arithmetic honest.
  unique (offer_id)
);

create index applications_user_status_idx on applications (user_id, status);
create index applications_user_submitted_idx on applications (user_id, submitted_at desc);
create index applications_cv_idx on applications (cv_document_id);

create trigger applications_updated_at
  before update on applications
  for each row execute function set_updated_at();

-- ---------------------------------------------------------------------------
-- status_events — how the application got where it is
-- ---------------------------------------------------------------------------

create table status_events (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null references auth.users(id) on delete cascade,
  application_id uuid not null references applications(id) on delete cascade,
  from_status    application_status,
  to_status      application_status not null,
  source         status_source not null default 'manual',
  note           text,
  created_at     timestamptz not null default now()
);

create index status_events_application_idx on status_events (application_id, created_at desc);
create index status_events_user_idx on status_events (user_id, created_at desc);

-- ---------------------------------------------------------------------------
-- profile_answers — reusable answers for recruitment forms
-- ---------------------------------------------------------------------------

create table profile_answers (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references auth.users(id) on delete cascade,
  label      text not null check (length(trim(label)) > 0),
  value      text not null,
  sort_order smallint not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, label)
);

create index profile_answers_user_idx on profile_answers (user_id, sort_order);

create trigger profile_answers_updated_at
  before update on profile_answers
  for each row execute function set_updated_at();

-- ---------------------------------------------------------------------------
-- reminders
-- ---------------------------------------------------------------------------

create table reminders (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null references auth.users(id) on delete cascade,
  application_id uuid references applications(id) on delete cascade,
  offer_id       uuid references offers(id) on delete cascade,
  due_at         timestamptz not null,
  title          text not null check (length(trim(title)) > 0),
  body           text,
  done_at        timestamptz,
  created_at     timestamptz not null default now(),

  constraint reminder_has_target
    check (application_id is not null or offer_id is not null)
);

create index reminders_user_due_idx on reminders (user_id, due_at)
  where done_at is null;

-- ---------------------------------------------------------------------------
-- Row level security
--
-- Enabled explicitly on every table. `(select auth.uid())` is wrapped in a
-- subquery so PostgreSQL evaluates it once per statement rather than per row.
-- ---------------------------------------------------------------------------

alter table profiles        enable row level security;
alter table companies       enable row level security;
alter table documents       enable row level security;
alter table offers          enable row level security;
alter table applications    enable row level security;
alter table status_events   enable row level security;
alter table profile_answers enable row level security;
alter table reminders       enable row level security;

-- profiles keys on id rather than user_id
create policy "profiles: read own" on profiles
  for select to authenticated using ((select auth.uid()) = id);
create policy "profiles: update own" on profiles
  for update to authenticated using ((select auth.uid()) = id) with check ((select auth.uid()) = id);

-- The remaining tables all follow the same shape.
create policy "companies: read own" on companies
  for select to authenticated using ((select auth.uid()) = user_id);
create policy "companies: insert own" on companies
  for insert to authenticated with check ((select auth.uid()) = user_id);
create policy "companies: update own" on companies
  for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy "companies: delete own" on companies
  for delete to authenticated using ((select auth.uid()) = user_id);

create policy "documents: read own" on documents
  for select to authenticated using ((select auth.uid()) = user_id);
create policy "documents: insert own" on documents
  for insert to authenticated with check ((select auth.uid()) = user_id);
create policy "documents: update own" on documents
  for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy "documents: delete own" on documents
  for delete to authenticated using ((select auth.uid()) = user_id);

create policy "offers: read own" on offers
  for select to authenticated using ((select auth.uid()) = user_id);
create policy "offers: insert own" on offers
  for insert to authenticated with check ((select auth.uid()) = user_id);
create policy "offers: update own" on offers
  for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy "offers: delete own" on offers
  for delete to authenticated using ((select auth.uid()) = user_id);

create policy "applications: read own" on applications
  for select to authenticated using ((select auth.uid()) = user_id);
create policy "applications: insert own" on applications
  for insert to authenticated with check ((select auth.uid()) = user_id);
create policy "applications: update own" on applications
  for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy "applications: delete own" on applications
  for delete to authenticated using ((select auth.uid()) = user_id);

-- Status history is append-only: no update or delete policy exists, so the
-- audit trail cannot be rewritten from the client.
create policy "status_events: read own" on status_events
  for select to authenticated using ((select auth.uid()) = user_id);
create policy "status_events: insert own" on status_events
  for insert to authenticated with check ((select auth.uid()) = user_id);

create policy "profile_answers: read own" on profile_answers
  for select to authenticated using ((select auth.uid()) = user_id);
create policy "profile_answers: insert own" on profile_answers
  for insert to authenticated with check ((select auth.uid()) = user_id);
create policy "profile_answers: update own" on profile_answers
  for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy "profile_answers: delete own" on profile_answers
  for delete to authenticated using ((select auth.uid()) = user_id);

create policy "reminders: read own" on reminders
  for select to authenticated using ((select auth.uid()) = user_id);
create policy "reminders: insert own" on reminders
  for insert to authenticated with check ((select auth.uid()) = user_id);
create policy "reminders: update own" on reminders
  for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy "reminders: delete own" on reminders
  for delete to authenticated using ((select auth.uid()) = user_id);
