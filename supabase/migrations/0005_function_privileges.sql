-- Offerly — take the functions out of the public API
--
-- PostgreSQL grants EXECUTE on a new function to PUBLIC unless told otherwise,
-- and PostgREST exposes everything in the `public` schema as an RPC endpoint.
-- Between them, every function written so far became callable by anyone
-- holding the anon key — which is public by design.
--
-- This is the same shape of mistake as the blanket UPDATE on profiles that
-- 0004 narrowed: a default that was harmless until it was not.

-- ---------------------------------------------------------------------------
-- redeem_invite — the one that mattered
--
-- Only sign-up calls this, and it does so with the service role. Left open, it
-- is an endpoint for guessing invite codes: no sign-in required, the
-- application's own checks skipped, and every wrong guess against a real code
-- still burns a use.
-- ---------------------------------------------------------------------------

revoke execute on function public.redeem_invite(text, text) from public, anon, authenticated;
grant  execute on function public.redeem_invite(text, text) to service_role;

-- ---------------------------------------------------------------------------
-- Trigger functions
--
-- These run from their triggers, which does not depend on anyone holding
-- EXECUTE — the privilege is checked when the trigger is created, not when it
-- fires. Calling them directly would fail on the missing row anyway; the point
-- is that they have no business being listed as endpoints at all.
-- ---------------------------------------------------------------------------

revoke execute on function public.handle_new_user() from public, anon, authenticated;
revoke execute on function public.enforce_document_limit() from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- set_updated_at: pin the search path
--
-- Without one, the function resolves names against whatever search_path the
-- caller happens to have. It is a small hole and a one-line fix; the newer
-- functions already set it.
-- ---------------------------------------------------------------------------

alter function public.set_updated_at() set search_path = public;

-- ---------------------------------------------------------------------------
-- Not fixed here, on purpose
--
-- `invites` has row level security enabled and no policies. The linter reports
-- that as a finding; here it is the intent. No policy means no row is visible
-- to anon or authenticated, which is exactly right for a table only the
-- service role touches. Adding a policy to quiet the warning would open it.
-- ---------------------------------------------------------------------------
