# What is free, what is paid

A record of where the line sits and why, written before there is anything to
sell — so the reasoning is the thing being judged, not the revenue.

**On the absence of a checkout.** Offerly is built to be used and to be read.
The tiering below is real: there is a plan on the account, one gate that
enforces it, and an interface that says plainly what a plan would add. There is
no payment processor, and adding one is not on the roadmap. Wiring up Stripe is
a solved problem that demonstrates nothing this repository does not already
show, and taking money for a digital service in the EU brings VAT, invoicing
and a legal entity along with it — obligations worth accepting for revenue, not
for the exercise. Plans are granted by hand while that stays true.

Everything else here is designed as though the money were real, because the
boundary is only worth drawing if it is drawn honestly.

---

## The rule everything follows from

**Offerly charges for what the application does, never for what you put into
it.**

Entering an application costs nothing to store and makes every other feature
worth more. A tracker is only useful once it holds a history, and a history
only accumulates if the free tier is worth loading. Capping the record at
fifteen applications would meet the user at exactly the moment their data
starts being useful and ask them for money to keep their own notes — which
teaches them not to write things down.

So the ceiling is never on rows. It sits on three things that genuinely
deserve a price:

1. **Work the server does on your behalf** — receiving and parsing forwarded
   mail, matching replies, sending reminders. This costs real money per user
   and scales with use.
2. **Time saved at volume** — capture without typing, status changes without
   clicking.
3. **Answers a spreadsheet cannot give** — which CV actually gets replies,
   which board is wasting your evenings.

---

## The floor: things that stay free whatever happens

These are not features. They are the conditions for trusting the tool at all,
and putting any of them behind a card would be a bait.

- **Export.** Every application and answer, as CSV, at any time. Paywalling the
  exit is holding a job search hostage.
- **Account deletion.** Immediate and total, always.
- **Password recovery.** Locking someone out of their own history over a
  lapsed subscription is indefensible.
- **Reading and editing everything already recorded.** Including after a
  subscription ends — see below.
- **The status history.** It is the record of what happened; it is not a
  feature to rent.

---

## Free — "the tracker"

Everything needed to run a job search by hand, without a limit and without a
card. This tier has to stand on its own, because most people will never leave
it and their word of mouth is the only marketing this has.

| | |
|---|---|
| **Applications** | Unlimited. Add, edit, delete, change status, full history. |
| **Offers** | Unlimited, entered by hand — including ones you are still deciding on. |
| **Companies and notes** | Unlimited. |
| **CV versions** | Two. Enough to run a search; the third is the moment someone started experimenting, which is the paid question. |
| **Today's list** | The whole attention engine: deadlines about to pass, offers that closed unsent, silence past your own window, forms left half-done. |
| **Form answers** | Unlimited, with copy-to-clipboard. |
| **Headline numbers** | Sent, replied, response rate, and the funnel — how far applications actually got. |
| **Export and deletion** | Always. |
| **Both languages** | Polish and English. |

The deliberate inclusion here is **today's list**. It is the best thing the
product does and it costs nothing to run — it is arithmetic over rows the user
typed. Putting it behind a wall would leave the free tier as a worse
spreadsheet, and nobody recommends a worse spreadsheet.

---

## Paid — "Offerly Plus"

Everything where the server works while the user is asleep, plus the questions
that need volume to answer.

### 1. Offers collected from your mail *(the anchor)*

A private forwarding address; job-board alerts land in a triage inbox instead
of the mailbox, parsed into title, company, location and range. One click turns
one into an application.

This is the anchor because it is the promise on the front page and because it
is the only feature with a real per-user cost: mail routing, parsing,
storage. Charging for it is honest and it limits itself.

**Free gets a taste, not a trial: ten collected offers a month.** A job search
is bursty — a fourteen-day trial expires during a quiet fortnight and teaches
nothing, while an allowance runs out exactly when the tool is proving useful.
The count resets monthly rather than being a one-off pool, so someone who tries
it in March and returns in September finds it working rather than spent.

### 2. Replies matched to applications

Incoming employer mail matched back to the application it belongs to, with a
confidence score. High confidence moves the status on its own; anything
uncertain waits to be confirmed. Nothing is ever sent on the user's behalf —
that stays true at every price.

### 3. Reminders that reach you

Email when a deadline is three days out, when silence crosses the ghosting
window, when an offer in the inbox is about to close. A Monday summary.

The tracker knows these things today and says them only when the page is open.
Making them arrive is what turns a page into a service — and it is the strongest
reason to pay, more than any statistic.

### 4. What actually works

Response rate **per CV version**, per board, per salary bracket, per contract
type — with the one sentence that follows from it. "The Sales CV gets replies
four times as often as the general one" is a thing no spreadsheet says and the
single most valuable output this product can produce.

Free keeps the headline number: *how am I doing*. Paid answers *why, and what
to change*.

### 5. Drafts, on request

Follow-up messages and form answers suggested from the user's own history.
Optional, never automatic, never sent. Runs on the user's own API key when they
have one — see decision 5 in ARCHITECTURE.md — so this stays cheap to offer.

---

## When a subscription ends

The data stays. All of it, readable, editable and exportable, forever. Only the
automation stops: no new offers are collected, no replies are matched, no
reminders are sent.

Anything else — hiding rows, freezing the account, holding the export — would
make the tool unsafe to adopt in the first place. This is a promise worth
writing into the interface, not just here.

---

## What it would cost

Shown in the interface, so the boundary reads as a real product decision rather
than an unfinished feature.

- **Monthly: 19–25 zł.** Below the threshold where someone without an income
  stops to think.
- **Three-month pass: ~49 zł, one payment, no renewal.** This is the headline.
  A job search lasts about that long, and a pass matches how the need actually
  arrives — a subscription for something you intend to stop needing invites
  cancellation anxiety on day one, which is a bad first impression.
- **Yearly: ~99 zł** for the people who keep an eye on the market permanently.

Anchoring on the pass rather than the subscription is unusual and it is the
point: it says the product knows what it is for and expects you to succeed and
leave.

---

## Build order

Every paid feature above is unbuilt. The gate comes first — not because it is
urgent, but because a boundary added after twenty call sites already exist gets
enforced in nineteen of them.

1. **`plan` on the profile, and one gate.** `free` and `plus`, granted by hand.
   One place that answers "may this account do that", so the answer cannot
   drift. Row level security enforces it in the database for anything the
   client could otherwise ask for directly.
2. **The interface tells the truth about it.** A locked feature says what it
   does, what it would cost and that the data stays either way — never a dead
   button, never a nag.
3. **Email ingest** — forwarding addresses, the inbound webhook, alert parsers.
   The first thing actually behind the gate.
4. **Reminders** — a scheduled job and outbound mail.
5. **Statistics per CV version**, which needs enough applications to say
   anything, and so lands after people have used the free tier for a while.

A checkout is not on this list. If that ever changes, a merchant-of-record
provider — Paddle, Lemon Squeezy — handles EU tax for a cut, which for one
person beats registering for VAT MOSS. Until then, plans are granted the same
way invites are.

---

## The one place inputs are capped, and why it is not a contradiction

Two CV versions on free is the single limit on something the user types, which
sits awkwardly beside the rule at the top of this page. It earns its place
because a second CV is not more of the same thing — it is the start of an
experiment, and the experiment is exactly what the paid tier answers. Someone
tracking one search with one CV never meets this limit. Someone testing four
versions against the market is doing the thing Offerly is for, and that is the
thing worth paying for.

It stays at two rather than one so that the free tier can still hold the
ordinary case: a general CV and a version for one particular kind of role.

## The order things arrive in

Invite-only stays until the product goes to production properly. Plans land
first, while the door is still shut — a boundary is much easier to get right in
front of people who already expect the thing to be unfinished, and much harder
to change once strangers have organised their job search around it.
