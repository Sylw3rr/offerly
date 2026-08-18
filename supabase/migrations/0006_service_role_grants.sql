-- Offerly — table privileges for the service role
--
-- 0003 granted the tables to `authenticated` and stopped there, which was
-- enough while everything server-side went through either the signed-in user's
-- token or a SECURITY DEFINER function. It stops being enough the moment
-- something runs on nobody's behalf: importing a register, sending reminders,
-- receiving a forwarded offer.
--
-- The service role bypasses row level security — that is the whole point of it
-- and the reason the key never leaves the server. These grants decide which
-- tables it may reach at all, and they are listed here rather than left to a
-- dashboard toggle, for the same reason the others are.

grant usage on schema public to service_role;

grant select, update on public.profiles to service_role;

grant select, insert, update, delete on public.companies       to service_role;
grant select, insert, update, delete on public.documents       to service_role;
grant select, insert, update, delete on public.offers          to service_role;
grant select, insert, update, delete on public.applications    to service_role;
grant select, insert, update, delete on public.profile_answers to service_role;
grant select, insert, update, delete on public.reminders       to service_role;

-- status_events stays append-only for every role. An operator with the service
-- key can add to the history of an application; nobody rewrites it.
grant select, insert on public.status_events to service_role;

-- invites is the one table only this role touches: codes are made and read by
-- hand, never by the application on a visitor's behalf.
grant select, insert, update, delete on public.invites to service_role;
