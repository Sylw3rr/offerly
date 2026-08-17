-- Offerly — account plans
--
-- Two plans: 'free' and 'plus'. Where the line sits and why is in
-- docs/PRICING.md; this migration is only concerned with making the line
-- impossible to step over.
--
-- There is no checkout. Plans are granted by hand with the service role, the
-- same way invite codes are.

create type account_plan as enum ('free', 'plus');

alter table profiles
  add column plan account_plan not null default 'free',
  -- When the plan lapses. Null means it does not — which is what a granted
  -- plan looks like. Nothing is deleted when it passes: the automation stops
  -- and the data stays readable, exportable and editable.
  add column plan_until timestamptz;

-- ---------------------------------------------------------------------------
-- A user may not promote themselves
--
-- `profiles` had a blanket UPDATE grant, which was harmless while every column
-- was a preference. It stops being harmless the moment one of them decides
-- what the account is allowed to do: the anon key is public, so anyone could
-- have sent `{"plan": "plus"}` straight to PostgREST and skipped the
-- application entirely.
--
-- Column-level grants are the right tool. The row level security policy still
-- limits the update to the user's own row; this decides which columns of that
-- row they may touch at all.
-- ---------------------------------------------------------------------------

revoke update on public.profiles from authenticated;
grant update (display_name, ghost_after_days) on public.profiles to authenticated;

-- ---------------------------------------------------------------------------
-- CV versions: two on free, unlimited on plus
--
-- Enforced here rather than only in Python for the same reason isolation is —
-- the client can reach PostgREST directly, so a check that lives in the
-- application is a check that can be walked around. See docs/ARCHITECTURE.md,
-- decision 1.
-- ---------------------------------------------------------------------------

create or replace function enforce_document_limit()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  user_plan account_plan;
  active_count integer;
begin
  select plan into user_plan from profiles where id = new.user_id;

  if user_plan = 'plus' then
    return new;
  end if;

  select count(*) into active_count
    from documents
   where user_id = new.user_id and is_active;

  if active_count >= 2 then
    raise exception 'document_limit_reached'
      using hint = 'The free plan keeps two CV versions.';
  end if;

  return new;
end;
$$;

create trigger documents_plan_limit
  before insert on documents
  for each row execute function enforce_document_limit();

-- Reactivating an archived version is another way to end up with three.
create trigger documents_plan_limit_on_activate
  before update of is_active on documents
  for each row when (new.is_active and not old.is_active)
  execute function enforce_document_limit();
