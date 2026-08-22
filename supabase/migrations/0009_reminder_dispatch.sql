-- Recording that a reminder was sent.
--
-- The table has existed since 0001 as somewhere to keep a due date a person
-- set. It is now also the log of what Offerly has told them about, which needs
-- two things it did not have: the reason, and the fact of having been sent.
--
-- `done_at` is not that fact. It means the person considers the thing dealt
-- with; `sent_at` means we put it in their inbox. Conflating them would let a
-- dismissed reminder be mailed again.

alter table reminders
  add column if not exists kind text,
  add column if not exists sent_at timestamptz;

-- The rule "one mail per application per reason" enforced where it cannot be
-- got around: the job can run twice — a retry, two schedulers, a deploy
-- overlapping a run — and the second insert fails instead of the second mail
-- being sent. A guard that lives only in Python is a guard that holds until
-- the day two copies of the job are running.
create unique index if not exists reminders_one_per_reason_idx
  on reminders (user_id, application_id, kind)
  where kind is not null and application_id is not null;

-- The job asks "what has this account already been told?" per run.
create index if not exists reminders_user_sent_idx
  on reminders (user_id, sent_at)
  where sent_at is not null;

-- Written by the job as the service role, read by the person. `kind` and
-- `sent_at` are a record of what we did, so the browser may read them and not
-- write them — the same reasoning as `offers.external_id` in 0008. The blanket
-- UPDATE grant has to go for the narrower one to mean anything.
revoke update on public.reminders from authenticated;

grant update (application_id, offer_id, due_at, title, body, done_at)
  on public.reminders to authenticated;

-- The switch. Default on, because a reminder nobody asked for is the point of
-- the feature and an account that silently never mails is indistinguishable
-- from one that is broken. Turning it off is one checkbox on the account page,
-- and every mail carries a List-Unsubscribe header for readers who would
-- rather not sign in to find it.
alter table profiles
  add column if not exists reminders_enabled boolean not null default true;

-- 0004 narrowed this grant to the columns a person may set. The new one joins
-- them; the plan columns stay out, as they did then.
grant update (display_name, ghost_after_days, reminders_enabled)
  on public.profiles to authenticated;
