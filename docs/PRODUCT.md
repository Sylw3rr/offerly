# What Offerly is becoming

A record of the product direction, written down because it is too large to keep
in one conversation. `ARCHITECTURE.md` records how things are built and
`PRICING.md` where the paid line sits; this one records what is being built and
what is still undecided.

Status: direction agreed, most of it unbuilt. Dates are deliberately absent —
the order matters, the calendar does not.

---

## The shape

Offerly began as a register of applications. It is becoming the whole job
search: a landing page describing the product, sign-up behind it, and inside,
one loop that carries an offer from arrival to answer.

**The loop.**

1. An offer arrives — forwarded from a job-board alert, or entered by hand.
2. It lands in a triage inbox. Keep it or drop it.
3. Opening one shows an application already prepared: a CV chosen or tailored
   for it, and the employer's questions already answered from what the account
   knows.
4. The person reads what was prepared, changes anything they disagree with, and
   sends.
5. The reply — an acknowledgement, a refusal, an invitation — is matched back to
   the application, and the register updates itself.

Everything already built is step 5's destination: the register, the history, the
dashboard, the flow chart. The loop is what feeds it.

---

## Where each part runs

This is the question that decides the architecture, and it came from noticing
that a browser extension cannot exist on a phone. Chrome on Android has no
extensions; Safari on iOS has them in name only. If sending an application
depended on an extension, the main loop would be broken for most sessions.

It resolves once you look at what people actually do on which device.

| | Phone | Desktop |
|---|---|---|
| Triage a new offer | yes, mostly here | yes |
| See what needs chasing | yes, mostly here | yes |
| Read that a reply arrived | yes, mostly here | yes |
| Edit a CV or a template | no | yes, only here |
| Tailor a CV to an offer | trigger it | review it |
| Fill in and send an application | queue it | yes, only here |

Nobody submits an application with a CV attached from a phone if they have a
choice, and editing a CV template on a six-inch screen is punishment. So the
phone is the tracker's eyes and ears; the desktop is the workshop. An extension
living only on the desktop is not a hole in the product — it sits where that
work already happens.

The gap that remains is real and gets an answer rather than a shrug: on a phone,
"apply" **prepares and queues**. The whole packet waits, ready, until the person
is at a computer. And the fallback works everywhere — open the advert, copy the
prepared answers, paste them in by hand.

**Consequence for how we build:** preparation is server-side and knows nothing
about how the application will be sent. Choosing the CV, tailoring it, answering
the employer's questions — all of that is useful whether the final step is an
extension, a copy-paste, or something not yet invented. The submission channel
is a decision that can be deferred without stalling anything, and it is last in
the order below.

---

## The submission question, recorded honestly

The instinct that "the user clicks, so it is not automation" is wrong in a way
worth writing down, because it will come up again.

A job board does not see the click. It sees an HTTP request: from a datacenter
address, without a browser's fingerprint, without a session built by ordinary
browsing, at machine timing. That is indistinguishable from a bot, because it is
one. Consent protects us from the user; it does not protect the user's account
from the portal — and the account at risk is the one they are job-hunting with.

What changes the picture is **where the request comes from**:

- **Server sends it** — looks like a bot, is treated like one.
- **Extension sends it** — the person's own browser, session, address and
  cookies. Still outside the letter of most terms of service, but without the
  technical signal that gets accounts banned.

Coverage will be partial in either case. Pracuj.pl has its own form; WeNet's ran
through eRecruiter and Fortum's through elementapp.ai. Each integrator is
separate work, so this starts with one portal and grows.

`README.md` currently promises *no auto-applying* and *no portal scraping*. The
first stays true under any option here — nothing goes out that the person has
not seen and sent. The second needs rewording once the channel is decided; it is
deliberately not reworded yet.

---

## CV generation

A new pillar, and the largest single piece.

- **Source of truth is a structured profile** — experience, education, skills as
  records — which templates render. Not a document edited like a word processor.
  Tailoring per offer only makes sense over structured data.
- **Five templates at the start**, made by a designer, all editable by the
  person using them, with full control over layout. The editor itself is a
  separate design conversation.
- **Tailoring rearranges, it does not invent.** The model moves emphasis inside
  what the profile already claims — reorders skills, rewrites the summary
  against the advert. It does not write experience nobody has. This is not a
  technical constraint; it is the difference between a useful tool and a machine
  for lying on CVs.
- **Deferred** relative to the ingest work. It impresses people, but the loop is
  what makes the product coherent.

`claude-resume-kit` already produces LaTeX CVs and can supply the starting
templates; whether the web app renders LaTeX or HTML is open, and it decides how
heavy the hosting is.

---

## AI, and who pays for it

`ARCHITECTURE.md` decision 5 says AI runs on the user's own key and Offerly
sends nothing. **The first half of that changes**: features are going behind a
paywall, so they run on our keys, with per-plan limits and abuse protection. The
second half does not change — nothing is ever sent to an employer without the
person seeing it first.

Costs were the open worry. They were computed, and they are not the constraint:

| | Per unit | Notes |
|---|---|---|
| Tailoring a CV to an advert | under 1 gr on a cheap model, 4–5 gr on a strong one | ~3 000 tokens in, ~1 500 out |
| Classifying and extracting one email | ~0.05 gr | forty times cheaper than the 2 gr guessed |
| Hosting at ~70 people | ~30–60 zł/month total | app host, mail sending; Supabase and mail receiving free at this size |

**So a limit of ten CV generations a month is protection against abuse, not
against cost.** An ordinary person cannot run up a bill worth worrying about; a
script pointed at the endpoint can. Set the number for the script, and be more
generous with the person than the first instinct suggested.

The same finding settles the email question: full extraction — interview times
into the calendar, requested documents into tasks — is affordable, so it is in.

*(Figures are estimates against known pricing and should be re-checked before
money is spent.)*

---

## Email

Forwarding and filters for now, exactly as `ARCHITECTURE.md` decision 2
describes: no mailbox credentials, the person decides what Offerly sees.

A Gmail connector is wanted later, and needs Google's restricted-scope
verification with its paid security assessment. That is a thing to buy once the
product has proved itself, not before.

---

## Rollout

1. **Friends** — a group of about thirteen. Perhaps eight try it, perhaps three
   use it for a week. Small enough that invite codes remain the right mechanism.
2. **Followers** — perhaps seventy. This is where the landing page, open
   registration and the cost arithmetic above start to matter.
3. **Public** — invites end here, not before.

---

## Order of work

1. **Email ingest** — offers in, replies matched, with full extraction. Closes
   the loop and feeds the statistics that already exist.
2. **Landing page** — nothing else can be shown to anyone without it.
3. **CV generation** — the profile, the templates, the editor, the tailoring.
4. **Assisted applying** — last, because it depends on the submission channel
   and because everything before it is useful without it.

---

## Still open

- Extension or copy-and-paste for submission. Deferrable; the preparation layer
  is built the same way either way.
- CV generator before or after the landing page.
- Which model tier for which job — classification is cheap enough for the small
  one, tailoring may be worth the larger.
- How the bank of recruitment questions gets filled: collected automatically
  from the forms people meet, or written out by hand.
- LaTeX or HTML for rendering CVs.
