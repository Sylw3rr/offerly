-- The interface language, on the account rather than in a cookie.
--
-- A cookie is the right home for it while someone is looking at the page: it
-- works before there is anyone to look a profile up for, which is why the sign-
-- in screen can already be in the right language. But a reminder is written by
-- a scheduled job at four in the morning, with no browser and no cookie
-- anywhere near it, so the choice has to be recorded somewhere the job can
-- read.
--
-- The cookie stays as the fast path for rendering. This is the copy that
-- outlives the session, and it also makes the FAQ true: the landing page says
-- the language is an account setting.

alter table profiles
  add column if not exists lang text
    check (lang is null or lang in ('pl', 'en'));

grant update (display_name, ghost_after_days, reminders_enabled, lang)
  on public.profiles to authenticated;
