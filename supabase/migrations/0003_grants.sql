-- Offerly — table privileges for the authenticated role
--
-- Row level security and table privileges answer different questions:
--
--   GRANT decides whether a role may touch the table at all.
--   RLS policies decide which rows it then sees.
--
-- Supabase projects created with "Automatically expose new tables" switched on
-- grant these implicitly. This project has it off, on purpose: privileges are
-- listed here so what each role can do is visible in the repository rather
-- than in a dashboard toggle.
--
-- The grants deliberately mirror the policies from 0001. Where a table has no
-- policy for an operation, it has no privilege for it either — the two
-- controls agree instead of one quietly covering for the other.

grant usage on schema public to authenticated;

-- profiles: created by trigger on sign-up, never inserted or deleted by hand.
grant select, update on public.profiles to authenticated;

grant select, insert, update, delete on public.companies       to authenticated;
grant select, insert, update, delete on public.documents       to authenticated;
grant select, insert, update, delete on public.offers          to authenticated;
grant select, insert, update, delete on public.applications    to authenticated;
grant select, insert, update, delete on public.profile_answers to authenticated;
grant select, insert, update, delete on public.reminders       to authenticated;

-- status_events is append-only. No update or delete privilege, matching the
-- absence of those policies: the history of an application cannot be rewritten
-- even if a policy were added by mistake later.
grant select, insert on public.status_events to authenticated;

-- invites gets nothing. Only the service role reads or writes it.
