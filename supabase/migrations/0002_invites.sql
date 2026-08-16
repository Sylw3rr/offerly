-- Offerly — invite codes (v0.1)
--
-- Registration is invite-only during early development.
--
-- Note the deliberate absence of policies below. Row level security is enabled
-- but no policy grants access, so neither `anon` nor `authenticated` can read
-- or write this table — not even to check whether a code exists. Only the
-- service role, used server-side during sign-up, can touch it.

create table invites (
  code       text primary key check (length(code) between 6 and 64),
  note       text,
  -- When set, the code only works for this address.
  email      text,
  max_uses   smallint not null default 1 check (max_uses > 0),
  uses       smallint not null default 0 check (uses >= 0),
  expires_at timestamptz,
  disabled   boolean not null default false,
  created_at timestamptz not null default now(),

  constraint uses_within_limit check (uses <= max_uses)
);

create index invites_active_idx on invites (code)
  where disabled = false;

alter table invites enable row level security;

-- Intentionally no policies. See the comment at the top of this file.

-- Redeems a code and reports whether it was accepted. Runs as the definer so
-- it can read the table despite row level security, and is only reachable
-- from the server.
create or replace function redeem_invite(p_code text, p_email text)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
  v_invite invites%rowtype;
begin
  select * into v_invite
  from invites
  where code = p_code
  for update;

  if not found then
    return false;
  end if;

  if v_invite.disabled
     or v_invite.uses >= v_invite.max_uses
     or (v_invite.expires_at is not null and v_invite.expires_at < now())
     or (v_invite.email is not null and lower(v_invite.email) <> lower(p_email))
  then
    return false;
  end if;

  update invites set uses = uses + 1 where code = p_code;
  return true;
end;
$$;

revoke execute on function redeem_invite(text, text) from anon, authenticated;
