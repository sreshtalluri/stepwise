# Identity, analytics and age — the three questions that are one question

Resolves `docs/OPEN-DECISIONS.md` **D5** ("Accounts: none, magic link, or OAuth?") and gives the
analytics and age-gating positions that D5 cannot be decided without.

Builds on `docs/research/rights-and-privacy.md` (D8). That document is not re-derived or
contradicted here. Where this one depends on it, it cites the section.

Written against a business model the builder has now stated: **free to users, funded by
advertising and sponsorship.** That single fact is what ties the three questions together, and it
is why they could not be answered separately.

I am not a lawyer. Every statute and rule quoted below was opened and read at the URL in §10.
§9 lists what I could not verify.

---

## 1. The one-paragraph answer

**Do not add a third-party analytics suite. Do not require accounts. Do not ask anyone's age
except at the one moment you create an account, and then ask for month and year only.**

The reason all three land in the same place is that the revenue model makes them the same
decision. Advertising to children is the one thing US law regulates hard, and the rule's own
text exempts **contextual** advertising while all but foreclosing **behavioural** advertising to
under-13s (§4.3). Behavioural advertising is also the only thing that needs cross-site tracking,
a consent banner, a consent-management platform, and an age gate that actually works. Drop
behavioural advertising — which a site this size was never going to monetise well anyway — and
the tracking, the banner, the age gate and the child-privacy exposure all drop out together.
The privacy-minimal path and the commercially-realistic path are the same path here. That is a
real result, not a tidy one, and §4.7 says what would break it.

What you gain by not tracking, you lose in one specific place: **you cannot measure returning
users well without some durable identity.** That is the honest cost, and it is the strongest
argument in favour of the optional account recommended in §3 — not §512(i), which is the
strongest *legal* argument, but retention measurement, which is the strongest *commercial* one.

---

## 2. What is already true, so this document does not re-open it

Verified against the branch this sits on and against `rights-and-privacy.md`:

- There is no database, no accounts, no sessions and no analytics of any kind today.
- `apps/web` on `w7-marketing` already stores the user's own clips locally
  (`rememberLocalClip`, imported by `apps/web/app/upload/page.tsx`). Browser-local state already
  exists and is already load-bearing for "works in your browser".
- The marketing page ships **"No account. Works in your browser."** directly under the primary
  action (`apps/web/lib/copy.ts`, `marketing.hero.noAccount`, verbatim from `DESIGN.md` §7e).
  Every recommendation below keeps that sentence literally true. That is a constraint this
  document accepted, not a coincidence.
- The job contract already records everything a product-analytics tool would otherwise be asked
  for at the pipeline end: `state`, `stage_message`, `progress`, `error.code`, `retry_count`
  (`packages/motion-contract/schema/job-status.schema.json`), and `persons`, `grounding`,
  `sample_times_s`, `model_report` (`motion-result.schema.json`).
- `rights-and-privacy.md` §6.2 recommends **dropping** `expr_params`, `pred_vertices` and
  `shape_params.vector` because holding unread person-specific data is pure liability. Any
  analytics recommendation that adds person-level collection is arguing against that, and has to
  say so out loud. §2.5 below does.
- Ad revenue makes the platform commercial without ambiguity. This changes nothing about the SAM
  License (no commercial restriction, no field-of-use limit, no user-count threshold) and it
  changes nothing about the non-commercial bar in `docs/research/grounding-models.md` §1.5 except
  to remove the last reason anyone might have argued about it. Noted, not re-litigated.

---

## 3. Question 1 — analytics

### 3.1 Start from the questions, not the tool

There are two audiences for a number here and they want different things.

**Product questions — what you need to know to make the thing good.** These are the ones the
builder actually cares about day to day, and almost all of them are answerable from data the
application already creates:

| Question | Where the answer lives | Needs a tracker? |
|---|---|---|
| Do uploads succeed? Which failure is most common? | `job-status`: `state`, `error.code`, `retry_count` | No |
| What does a lesson cost to build? | job wall time × GPU rate, per `persons` count | No |
| Do people finish a lesson? | playback time against lesson length | First-party event |
| Which parts do people loop, and how many times? | loop set/clear events, part index | First-party event |
| Where do people drop off? | last count reached before the tab goes away | First-party event |
| Does using orbit correlate with staying longer? | view-preset changes joined to playback time | First-party event |
| Do multi-dancer clips confuse the picker (`DESIGN.md` §7a2)? | `persons` count, index picked, time to pick | First-party event |
| Does the share loop work? | lesson opens carrying no creator token, then an upload | First-party event |

Not one of those needs a third-party product-analytics suite. They need an event table and some
SQL. The pipeline half needs nothing new at all.

**Commercial questions — what a person paying you wants to see.** Monthly and daily actives,
sessions, session length, return rate, geography, page and lesson views. These are shallower and
coarser than the product questions, and the first-party log answers all of them except one:
**return rate**, which is the only metric in this document that genuinely costs privacy to
measure. §3.6 deals with it.

### 3.2 The tool survey, on the same axes `grounding-models.md` used

`grounding-models.md` §1.6 established that a licence is not one fact, it is several, and that
the axes have to be checked separately. The same discipline applies here, with the axes adapted:
the risk in an analytics tool is not what it is licensed as, it is what it stores on your users'
devices and what leaves your control.

| Tool | Code licence (read) | Self-host reality | Stores on the device | Leaves your control |
|---|---|---|---|---|
| **PostHog** | MIT Expat, **except** everything under `ee/`, which is under `ee/LICENSE` | Officially unsupported. PostHog's own docs: self-hosted is "officially unsupported", "We don't offer customer support", free-plan features only, "All paid-plan features are Cloud-only", and there are no tagged releases so no CVEs. Needs ~4 vCPU / 16 GB, ClickHouse, Kafka, Postgres, Redis | First-party cookies by default; a cookieless persistence mode exists | Everything, if you use Cloud |
| **Plausible CE** | AGPL-3.0, whole repo. Trademarks explicitly **not** licensed | Supported, documented, but still ClickHouse + Postgres + an Elixir app | Nothing — no cookies | Nothing, if self-hosted |
| **Umami** | MIT, © Umami Software, Inc. | One Next.js container plus a Postgres or MySQL database — the database the infrastructure decision is already choosing | Nothing by default — no cookies | Nothing, if self-hosted |
| **Matomo** | GPL-3.0-or-later for core, tracker and free plugins; premium plugins under the InnoCraft EULA | PHP + MySQL, plus an archiving cron you have to understand. Heaviest of the four | Cookies by default; can be configured off | Nothing, if self-hosted |
| **Fathom** | Fathom Lite is MIT; the product is hosted-only and paid | Fathom Lite's Docker image has not been updated in five years | n/a | n/a |
| **None** | n/a | n/a | Nothing | Nothing |

Four readings fall straight out of that table.

**PostHog is the wrong tool for this product, and self-hosting it is the wrong way to get it.**
Not because of the licence — MIT Expat outside `ee/` is clean, and the `ee/` split is the normal
open-core shape. Because of the other three columns. PostHog's own documentation tells you not
to self-host it; their stated position on the economics is blunt ("We've literally never seen
this math work out"). The builder's stated reason for preferring self-hosting is avoiding a
service that is cheap now and expensive later, and that reason is sound in general — but the
thing PostHog wants you to self-host is a five-service stateful cluster with no release tags and
no published CVEs, standing next to a GPU pipeline that is already the hard part of this system.
That is not a cheap hedge, it is a second production system. And the product PostHog *is* —
autocapture, person profiles, session replay, feature flags — is a person-level instrument
bolted onto a project whose entire privacy posture is "hold less about people". §2.5 takes that
seriously rather than waving at it.

**Plausible CE is AGPL-3.0, and that is fine here — but say why, because this project has been
bitten by AGPL before.** PRD §2 G2 dropped Ultralytics specifically to delete an AGPL tree,
reasoning from the FSF position that modules sharing one Python interpreter's address space are
"almost surely combined" into one program. That reasoning does not reach a separate analytics
service. Plausible CE is a distinct Elixir application in its own container, spoken to over HTTP;
nothing of it is imported into `apps/web` or `services/motion-api`, and no combined work is
formed. AGPL §13's obligation is triggered by *modifying* the program and letting users interact
with the modified version over a network — run it unmodified and the duty is satisfied by
pointing at upstream. The separate trademark position ("Plausible", "Plausible CE") is not
licensed under the AGPL, which only matters if you rebrand or resell, and you are doing neither.
So: AGPL is not a disqualifier for Plausible CE. It is a disqualifier for importing AGPL code
into this repo, which is a different act, and the G2 decision stands untouched.

**Umami is the cleanest third-party option on every axis.** MIT with no carve-out, no acceptable-
use clause, cookieless by default, and it runs as one container against the Postgres the
infrastructure agent is already choosing. If a third-party tool is ever added, this is the one.

**Fathom Lite fails the same test `grounding-models.md` applied to research code.** A permissive
licence on a five-year-stale codebase is not an advantage. Matomo is not wrong, it is just more
machine than the question needs; its one distinctive asset is the CNIL configuration paper trail
in §3.3, which matters only if France is where your traffic is.

### 3.3 Does any of this need a consent banner?

This is the part most often answered too confidently in both directions. The honest position has
three layers.

**Layer one — the storage rule.** [Directive 2002/58/EC Article 5(3)](https://eur-lex.europa.eu/legal-content/EN/ALL/?uri=CELEX:32002L0058),
as amended by 2009/136/EC, conditions "the storing of information, or the gaining of access to
information already stored, in the terminal equipment of a subscriber or user" on consent, with
an exemption only for what is "strictly necessary in order for the provider of an information
society service explicitly requested by the subscriber or user to provide the service". Analytics
is not strictly necessary to provide a dance lesson. **So any analytics that sets a cookie, or
reads or writes `localStorage` or `sessionStorage`, needs consent in the EU.** That rules out
PostHog's default configuration and Matomo's default configuration.

**Layer two — cookieless is not automatically consent-free.** This is the part that gets
overstated. The EDPB's [Guidelines 2/2023 on the technical scope of Article 5(3)](https://www.edpb.europa.eu/system/files/2024-10/edpb_guidelines_202302_technical_scope_art_53_eprivacydirective_v2_en_0.pdf),
final version adopted at the October 2024 plenary, take a deliberately broad reading: they treat
"information" as covering non-personal data, treat storing and accessing as separate triggers
either of which suffices, and in the dedicated "tracking based on IP only" use case place the
burden on the collector — unless the entity can establish that the IP address does not originate
from the user's terminal equipment, it must treat Article 5(3) as engaged. Commentators noted at
draft stage that this goes past the plain meaning of "storing" and "accessing". It is a guideline,
not a judgment, and it has not been tested in court. But "we are cookieless so no banner" is a
weaker claim after October 2024 than before it.

**Layer three — the audience-measurement exemption, which is where the practical answer lives.**
The Article 29 Working Party's 2012 opinion already treated first-party analytics limited to
aggregate statistics as exemptible, and CNIL turned that into operable conditions in
[Deliberation No. 2020-092 of 17 September 2020](https://www.cnil.fr/en/sheet-ndeg16-use-analytics-your-websites-and-applications).
To qualify, the measurement must serve only the publisher, produce only anonymous statistics, be
limited to one publisher's site, not be cross-checked against other processing, not transmit
identifiable data to third parties, not track across sites, cap the identifier lifetime at 13
months and retention at 25 months, and be disclosed to users. CNIL ran an evaluation programme
against these conditions from 2021; **that programme was replaced on 1 January 2026 by a
self-assessment tool**, so there is no longer a list to be on — you assess yourself against the
published criteria. Matomo is the tool with the most detailed published configuration guide for
this; Google Analytics never qualified in any version.

The UK is stricter. The ICO's PECR position is that non-essential analytics requires prior
consent, restated in its Storage and Access Technologies guidance finalised in April 2026.
Luxembourg's CNPD is closer to CNIL. There is no single European answer.

**So the cheap way to not care, which is the actual recommendation:** do the counting
**server-side**, from your own request and job records, storing nothing on the device for
analytics purposes and reading nothing from it. Article 5(3) is a rule about terminal equipment.
If you never touch the terminal equipment for this purpose, the rule has nothing to attach to,
the EDPB's broad reading of "access" is not reached because you are processing a request you were
sent rather than reaching into a device, and what remains is ordinary GDPR — a lawful basis
(legitimate interests, the same Art. 6(1)(f) basis `rights-and-privacy.md` §5b already
established for the core processing), a line in the privacy notice, and a retention period. This
is not a loophole. It is the design that collects least.

The local clip store that already exists (`rememberLocalClip`) is a separate matter and is
genuinely covered by the strictly-necessary exemption: it exists to deliver "your lessons, in
this browser", which is the service the user explicitly requested. §3.6 is careful about the one
place that gets complicated.

### 3.4 The tension, named

The brief asked for this not to be dodged, and it should not be.

`rights-and-privacy.md` §6.2 recommends deleting `expr_params` (facial expression coefficients,
never read), `pred_vertices` (18,439 × 3 floats per person per frame, never read) and
`shape_params.vector` (45 numbers describing a person's body proportions, never consumed). The
argument is not that these are illegal. It is that holding unread person-specific data is pure
downside — it is the artifact most likely to be called "biometric data" under the broader
comprehensive state definitions, and nothing is gained by keeping it.

A product-analytics suite is the same argument running the other way. Autocapture records every
click and input on the page whether or not you asked a question about it. Person profiles build
a durable record of an individual across sessions. Session replay is the sharpest case. To be
precise rather than alarming: PostHog's replay is a DOM reconstruction, not a screen recording,
so a `<video>` element is not captured as pixels, and WebGL canvas capture is opt-in
(`captureCanvas.recordCanvas`). But the DOM it records includes the URL of the uploaded clip,
and a replay will play that clip inside the replay if the URL is still reachable at replay time;
if canvas recording were enabled to see the 3D stage, the reconstructed body would be captured
too. And PostHog's documented default is that general page text is **not** masked — only inputs
are. So the accurate statement is: session replay on this product would create a second,
differently-shaped copy of exactly the material §6.2 argues for holding less of, retained on a
different clock, in a system whose retention you configure separately and will forget about.

There is no version of "we drop `pred_vertices` because unread person data is liability" that
survives "and we record everyone's sessions in case we want to look". Pick one. This document
picks the first, because it is the one already in the repo and the one the product's own copy
already implies.

### 3.5 Recommendation

**Primary: no third-party analytics at launch. A first-party event log in the application's own
database, read with SQL.**

Reasons, in order of weight:

1. It answers every product question in §3.1 and every commercial question except return rate.
2. It adds no vendor, no second stateful system, no new licence to the `NOTICE`, no data
   processor to name in the privacy notice, and no consent banner.
3. It is the only option consistent with §6.2's posture.
4. It is roughly one table, one insert helper and a handful of queries. The infrastructure agent
   is choosing the database anyway; this is a table in it, not an architecture.

**The escape hatch, pre-approved so the decision is reversible in an afternoon: Umami,
self-hosted, MIT.** One container against the same database. Add it if and only if the trigger
in §3.7 fires.

**Explicitly rejected, with reasons rather than vibes:**

- **PostHog self-hosted** — vendor tells you not to, five-service cluster, no release tags, and
  the product shape is wrong for this posture (§3.2, §3.4).
- **PostHog Cloud as a permanent fixture** — same posture problem, plus a processor relationship
  and a DPA. If a specific question ever genuinely needs a funnel you cannot write, PostHog Cloud
  EU with `person_profiles: 'identified_only'`, cookieless persistence and replay off, for a
  fixed number of weeks, then removed, is a defensible instrument. A permanent install is not.
- **Matomo** — more machine than the question needs; its CNIL configuration advantage is
  irrelevant if you are not storing anything on the device in the first place.
- **Fathom Lite** — unmaintained.

### 3.6 Minimum instrumentation

One table. Nine events. Nothing per-person beyond the creator token from §4.

```
event(
  id, occurred_at,
  name,                 -- one of the nine below
  lesson_id,            -- nullable
  job_id,               -- nullable
  creator_token_id,     -- nullable; only set when the request already carries one
  day_hash,             -- see below
  country,              -- derived from IP, then the IP is discarded, never stored
  props jsonb
)
```

| Event | Source | Props | Answers |
|---|---|---|---|
| `job_created` | server, on upload | clip seconds | uploads per day, clip length distribution |
| `job_finished` | server, from the job record | `state`, `error.code`, `retry_count`, wall seconds, `persons` count | completion rate, which B1/B2 failure dominates, cost per lesson, how common multi-dancer really is |
| `lesson_opened` | server, on the lesson route | `own` vs `shared` (does the request carry the creator token for this lesson), referrer **host only** | the A3 share loop, daily actives |
| `play_seconds` | client heartbeat, every 30 s of playing time | `seconds`, cumulative bucket | session length, do people finish a lesson |
| `part_looped` | client, when a loop is set | part index, loop count bucket | **the single most product-shaped metric here** — which parts fight people |
| `view_changed` | client, on a preset or orbit change | preset id | does the reveal teach orbiting, does orbiting correlate with staying |
| `dancer_picked` | client, `DESIGN.md` §7a2 | `persons` count, index picked, ms since load | do multi-dancer clips confuse the picker |
| `share_copied` | client | — | growth loop, top of funnel |
| `account_linked` | server | — | account conversion, and the retention denominator |

**`day_hash` is the unique-visitor device, and its trade-off must be stated.** It is
`hash(daily_rotating_salt + site_id + ip + user_agent)`, computed server-side, never sent to the
device. A salt that rotates daily gives you clean daily actives and makes cross-day linkage
impossible by construction — which is the privacy-correct default and is also why **it cannot
measure retention**. You cannot have both from the same field. The resolution is not to weaken
the salt; it is §4: signed-in users have a durable identity you already hold for a different and
better reason, so measure retention on them and say plainly that the number is for the signed-in
subset. A measured cohort with a stated denominator beats a fuzzy whole-population estimate, and
it is the honest number to show a sponsor.

**Retention of analytics data:** 13 months for row-level events, then roll up to daily aggregates
and delete the rows. That sits inside CNIL's 25-month ceiling with room to spare and closes the
analytics half of D6 without a separate decision.

**Deliberately not collected:** no autocapture, no session replay, no per-user event streams for
anonymous visitors, no third-party pixels, no stored IP addresses, no `utm_` fan-out beyond
referrer host, no scroll or mouse tracking.

### 3.7 When a third party becomes genuinely necessary — and the non-obvious answer

The coordinator asked where a tool stops being convenient and starts being necessary. The honest
answer is that it is a **credibility** threshold, not a knowledge one, and that self-hosting is
the wrong response to it.

- **For knowledge: never, realistically.** Everything in §3.6 is a SQL query. A solo builder who
  can operate a GPU pipeline can write a retention query.
- **For programmatic ads: also never.** If ads ever run, the network's own reporting *is* the
  audience measurement — impressions, RPM, geography, all counted by the counterparty. You do not
  buy a tool to measure something your advertiser is already measuring for you.
- **For direct sponsorship: this is the real case, and the answer is counter-intuitive.** A
  sponsor who wants to verify your numbers is not reassured by a dashboard you host, because a
  self-hosted dashboard is self-reported by definition. Umami self-hosted is exactly as
  independent as your own SQL, which is to say not at all. If independence is genuinely demanded,
  the correct purchase is a **hosted** analytics service with a public dashboard link — Plausible
  Cloud's public dashboards are the cheapest form of this. That is the one scenario in this entire
  document where self-hosting is the wrong answer, and it is worth knowing in advance so the
  decision is not made in a hurry during a sponsorship conversation.

So: ship §3.6. If a sponsor asks for independent numbers, buy hosted Plausible and make the
dashboard public — a commercial decision, made once there is revenue to justify it, not a
launch blocker.

---

## 4. Question 2 — accounts, and the resolution of D5

### 4.1 The three options, honestly costed

**Option A — no accounts at all (status quo).** A lesson is a link, and holding the link is the
capability.

- Enables: the shipped promise, zero friction, nothing personal stored, no password, no reset
  flow, no account-takeover surface, no breach to disclose.
- Costs: no library across devices; no owner, so `rights-and-privacy.md` §6.1's removal path is
  asymmetric — anyone holding a link can get a lesson taken down and nobody can get it back; and
  **no subscriber or account holder to terminate under §512(i)**, which is the D8 note's point.
- Costs commercially: no retention cohort at all, and "returning users" is the question sponsors
  ask most.

**Option B — required accounts.** Sign in before you can do anything.

- Enables: everything in §512(i), a clean retention measurement, an age screen that actually
  covers your users, and a real deletion request path.
- Costs: retracts **"No account. Works in your browser."** from the marketing page, under the
  primary action, where W7 deliberately put it as a conversion decision. It converts the most
  important step in the product (`DESIGN.md` §7h names it as such) into a form. It also creates
  the child-privacy exposure §5 spends its length avoiding, for every user rather than a
  minority. For a free tool whose entire pitch is "try this right now", this is the worst trade
  in the document.

**Option C — optional accounts, anonymous by default. Recommended.**

Concretely:

1. **Every upload mints a creator token** — an opaque random value, stored in the browser
   alongside the existing local clip record, and recorded server-side against the lesson. It is
   not an identity; it is a capability, the same shape as the share link, but held privately and
   never put in a URL.
2. **The creator token is what owns a lesson.** It is what lets you delete it, restore it after a
   removal request, and see it in "my lessons". This closes D7's "does the share link die with
   it" and closes §6.1's asymmetry without any sign-in.
3. **Signing in binds tokens to an email.** The sign-in flow posts the browser's token list and
   binds them to the account. That is the whole answer to "what happens to anonymously-created
   lessons when someone later signs in": they are already in the browser's hands, so they are
   claimed automatically and silently. Nothing is orphaned and nothing needs a migration screen.
4. **Nothing else changes.** Uploading, viewing, sharing, looping, deleting all work signed out.
   The sentence on the marketing page stays literally true.

### 4.2 Why this is the §512(i) answer and not a dodge

[17 U.S.C. § 512(i)(1)(A)](https://www.law.cornell.edu/uscode/text/17/512) conditions every one
of §512's limitations on the provider having

> adopted and reasonably implemented, and informs subscribers and account holders of the service
> system or network of, a policy that provides for the termination in appropriate circumstances of
> subscribers and account holders of the service system or network who are repeat infringers

With no identity of any kind, there is no "subscriber or account holder", so the statutory hook is
empty and the policy is unimplementable — that is exactly what the D8 note flagged. The creator
token fills it: it is a persistent account identifier that you issue, that you can block, and that
is what a repeat uploader would have to discard and re-earn.

Two Ninth Circuit decisions say how much is enough, and they are unusually encouraging for a solo
operator. [*Perfect 10, Inc. v. CCBill LLC*, 488 F.3d 1102 (9th Cir. 2007)](https://law.justia.com/cases/federal/appellate-courts/F3/488/1102/496805/)
reads "reasonably implemented" as two questions — is there a policy, and is the implementation
reasonable — and holds that a provider implements a policy where it has a working notification
system, a procedure for handling compliant notices, and does not obstruct copyright owners; a
policy is unreasonable "only if the service provider failed to respond when it had knowledge of
the infringement". [*Ventura Content, Ltd. v. Motherless, Inc.*, 885 F.3d 597 (9th Cir. 2018)](https://www.leagle.com/decision/infco20180314132)
applied that to a one-person site whose operator terminated repeat infringers on his own
judgement, without a written policy document and without keeping a log, and still found the safe
harbour available: the process need not be perfect, only work a reasonable amount of the time.

So the bar is not "build an enforcement system". It is "have something to terminate, and
terminate it when you should". The creator token is the smallest thing that clears it, and
binding it to an email when someone chooses to sign in makes termination stick across a cleared
browser. `rights-and-privacy.md` §6.4's written repeat-infringer policy is unchanged; this just
gives it a subject.

### 4.3 Mechanism: email magic link

For a solo builder, ranked by what each actually costs to operate:

- **Magic link — recommended.** One `email` column, one signed single-use token, one transactional
  email sender. No passwords, so no hashing decisions, no reset flow, no credential stuffing, no
  password breach to disclose. The failure mode is email deliverability, which is a known problem
  with a known fix. It also yields the one contact channel you will genuinely need — a removal
  request outcome, or a §512 counter-notice, has somewhere to go.
- **OAuth (Google / Apple) — not recommended for v1.** It hands you a verified email but also a
  name and avatar you did not ask for and now hold, adds a third-party identity provider to the
  privacy notice, and for Apple adds a paid developer account. Google's own client-ID
  configuration is a recurring source of silent breakage. The upside over a magic link on a free
  site with no enterprise buyer is one tap.
- **Passkeys — the right upgrade, the wrong starting point.** Strongest security and no shared
  secret, but the second-device and lost-device recovery story is exactly the support load a solo
  operator cannot carry, and the recovery path ends up being an email link anyway. Because the
  identity is the email either way, adding passkeys later is additive and costs nothing to keep
  open. Note it, do not build it.

### 4.4 Copy

Passes `apps/web/test/copy.test.ts` (no banned words, no exclamation marks, no emoji, no
all-caps runs, sentence case) and `DESIGN.md` §11 and §7h — it states a mechanism, not a
guarantee.

```ts
export const account = {
  // Offered, never demanded. Appears on the lesson page and in "my lessons",
  // never as a wall in front of upload — DESIGN.md §7e, and the marketing
  // promise "No account. Works in your browser." stays true.
  heading: "Keep your lessons",
  body: "Your lessons live in this browser. Add an email and they follow you to another one.",
  action: "Email me a link",
  sent: "Check your email. The link works once, and for 15 minutes.",
  signedIn: (email: string) => `Signed in as ${email}`,
  signOut: "Sign out",

  // Month and year only. Asked once, here, and nowhere else — see §5.
  ageLabel: "Month and year you were born",
  ageWhy: "We ask so an account is not set up by a child. Nothing else uses it.",
  ageBlocked:
    "You need to be 13 or older for an account. The site works without one, and your lessons stay in this browser.",
};
```

Nothing in that says "secure", "protected" or "verified". It says where the lessons are and what
adding an email does.

### 4.5 D5 resolution, and the single strongest justification

**Optional accounts, anonymous by default, creator token as the unit of ownership, email magic
link to bind it.**

If only one sentence survives: **without some account identifier there is no subscriber to
terminate, so §512(i)'s repeat-infringer policy cannot be reasonably implemented, and §512(i)
conditions every DMCA safe harbour — which is the only thing standing between a solo operator and
direct liability for what strangers upload.** The creator token is the smallest thing that makes
that policy real, and it costs the marketing promise nothing.

The second-strongest, and the one that will matter sooner in practice, is commercial: retention is
the metric sponsors ask about and the only one anonymity cannot give you (§3.6).

---

## 5. Question 3 — age

This is the question most likely to be got wrong, and the failure mode is over-reaction: adding a
birthdate field, which collects personal data you did not have, manufactures the legal trigger you
were trying to avoid, and buys nothing.

### 5.1 COPPA — is this service "directed to children"?

[16 C.F.R. § 312.2](https://www.law.cornell.edu/cfr/text/16/312.2) defines a website or online
service directed to children as a commercial site "or portion thereof, that is targeted to
children", and lists the factors the Commission weighs: subject matter; visual content; use of
animated characters or child-oriented activities and incentives; music or other audio content; age
of models; presence of child celebrities or celebrities who appeal to children; language or other
characteristics; whether advertising promoting or appearing on the site is directed to children;
plus "competent and reliable empirical evidence regarding audience composition" and evidence of
intended audience, including marketing materials, statements to consumers or third parties,
"reviews by users or third parties, and the age of users on similar websites or services".

Applied honestly to a dance-learning tool:

| Factor | This product | Cuts |
|---|---|---|
| Subject matter | Learning a dance from a video | Neutral — dance spans all ages |
| Visual content | A stylised 3D body on a stage beside the user's clip | Neutral |
| Animated characters, child-oriented activities **and incentives** | None. `DESIGN.md` §7g bans points, XP, streaks, badges and levels outright | **Against** child-directed, and it is already in writing |
| Music or audio | Whatever is in the user's own clip | Neutral |
| Age of models | **The demo lesson, the before/after and the marketing footage are yours to choose** | Could cut either way |
| Child celebrities | None | Against |
| Language | Plain adult register, linted in `copy.test.ts` | Against |
| Advertising on the site directed at children | **Nothing today. Becomes a self-inflicted factor the moment you accept kid-targeted creative** | Your choice |
| Empirical audience composition; age of users on similar services | TikTok dance skews young, and the FTC expressly weighs the age of users on similar services | **For** child-directed. This is the real counterweight |

**Verdict: general audience, not child-directed — defensible today, but it is a verdict you
maintain by choice, not a fact you are handed.** Three concrete product rules keep it:

1. **Use adult dancers in the demo lesson, the before/after, and every piece of marketing
   footage.** This is the cheapest single item in this document and it goes straight at the "age
   of models" factor. `evaluation/README.md` already tracks clip rights in tiers; extend the same
   discipline to the age of the person in any clip that appears publicly.
2. **Keep §7g's ban on gamification.** It was written as a taste rule. It is also evidence.
3. **Never accept ad creative aimed at children.** The rule lists advertising on the site as a
   factor in whether the site is child-directed, so the ads you run feed back into your own
   status.

Note the "mixed audience" category, because it is a trap if misread. §312.2 defines it as a
service that *meets* the child-directed factors but does not target children as its primary
audience, and the FTC's [Complying with COPPA FAQ](https://www.ftc.gov/business-guidance/resources/complying-coppa-frequently-asked-questions)
is explicit that it is a "subset of the 'directed to children' category" — a general-audience site
does not become mixed-audience merely because children show up. Do not reach for it. Its practical
sting is that a mixed-audience operator "may not block children from participating altogether",
whereas a general-audience operator may.

### 5.2 What a general-audience service actually owes — and why a birthdate field is the wrong move

Two sentences from the FTC's own FAQ do most of the work. The Rule "does not require operators of
general audience sites to investigate the ages of visitors", and COPPA "does not *require* you to
permit children under age 13 to participate". A general-audience service owes nothing under COPPA
until it has **actual knowledge** that it is collecting personal information from a child. The FAQ
gives the examples: a parent tells you; a responsible person at the company sees a post where the
child says her age or mentions elementary school; an email says so.

Now look at what verifiable parental consent would require if you did acquire that knowledge.
[16 C.F.R. § 312.5(b)(2)](https://www.law.cornell.edu/cfr/text/16/312.5) lists the acceptable
methods: a signed form by mail, fax or scan; a payment card transaction that notifies the primary
account holder; "a toll-free telephone number staffed by trained personnel"; a video-conference
with trained personnel; government-issued ID checked against a database and deleted promptly;
knowledge-based authentication with dynamic multiple-choice questions a 12-year-old in the
household could not answer; or photo ID matched to a face image by facial recognition and reviewed
by trained personnel. "Email plus" and "text plus" exist but are available only to operators that
do not disclose personal information to third parties — which an ad-supported site is in a poor
position to claim.

**None of those is operable by one person.** So the practical consequence of acquiring actual
knowledge is not "run a consent flow", it is "do not knowingly serve under-13s". Which means the
worst possible design is a birthdate field on a page everyone sees: it collects personal
information you had no need for, from people you had no obligation to ask, and converts a clean
"no actual knowledge" posture into a live obligation for every honest child. Asking the question
is the thing that creates the problem.

The 2025 amendments do not change that analysis, and are worth stating precisely because they are
recent. The FTC approved them on 16 January 2025; publication was delayed by the January 2025
regulatory freeze; they were published at
[90 Fed. Reg. (22 April 2025)](https://www.federalregister.gov/documents/2025/04/22/2025-05904/childrens-online-privacy-protection-rule),
effective **23 June 2025**, with a general compliance date of **22 April 2026** (both now passed).
The changes that matter here: "personal information" now names biometric identifiers as their own
category — §312.2 lists fingerprints, handprints, retina and iris patterns, genetic data,
voiceprints, **gait patterns** and facial templates — and §312.5(a)(2) now requires **separate**
verifiable parental consent before disclosing a child's personal information to third parties
unless the disclosure is "integral to the website or online service". §312.10 also bans indefinite
retention of children's data and requires a published written retention policy. The gait-pattern
listing is worth noticing given what this pipeline computes, but it only engages if COPPA engages
at all, which is the question §5.1 answers.

### 5.3 The commercial half — and where the two paths converge

This is the finding the coordinator was right to push on, and it holds.

**Contextual advertising is permitted even to children, without parental consent, by the text of
the Rule.** §312.2's definition of "support for the internal operations of the website or online
service" expressly includes activities necessary to "[s]erve contextual advertising on the website
or online service or cap the frequency of advertising". §312.5(c)(7) then exempts from verifiable
parental consent the collection of "a persistent identifier and no other personal information"
used solely to provide support for internal operations. Paragraph (2) of the internal-operations
definition draws the line precisely: the information collected for those activities may not be
used or disclosed "to contact a specific individual, including through behavioral advertising, to
amass a profile on a specific individual, or for any other purpose".

So the rule itself splits advertising into a permitted half and a foreclosed half, and the
permitted half is the half that needs no tracking:

| | Contextual ads / direct sponsorship | Programmatic behavioural |
|---|---|---|
| Needs cross-site tracking | No | Yes |
| Needs a consent-management platform in EU/UK | No | Yes |
| Needs an age gate that works | No | Effectively yes |
| Permitted to under-13s without parental consent | Yes, by §312.2 and §312.5(c)(7) | No — and post-April-2025, needs *separate* consent under §312.5(a)(2) |
| Available to a site with a young audience | Yes | Restricted, and the restriction is enforced by the network, not only by the regulator |

Google implements exactly this split itself. Its publisher documentation (AdSense and Ad Manager)
describes the tag for age treatment — `tfat`, which supersedes the deprecated tag for
child-directed treatment — where the child value "disables personalized ads and remarketing",
disables "requests to third-party ad vendors, such as ad measurement pixels and third-party ad
servers", and stops transmission of the Android and iOS advertising identifiers. Site-level
tagging is done through Search Console. The sentence to take seriously: **Google states that even
without notice from the publisher, it may in some cases begin treating a site as child-directed
under its own COPPA obligations.** You do not fully control this classification.

**Strategic consequence, stated plainly.** For an audience that skews young, behavioural
programmatic is the revenue path most likely to be restricted, and it is restricted by your
counterparty's own machinery as much as by the FTC. Contextual advertising and direct sponsorship
stay fully available, and they are precisely the options that need no tracking, no banner and no
age verification. **The privacy-clean path and the commercially-viable path converge.**

The part that is *not* tidy, and should not be sold as if it were: contextual and direct inventory
earn less per thousand impressions than behavioural inventory, so the convergence is real but it
is not free — you are choosing the lower-CPM half of the market. On a small site the difference is
mostly theoretical, because programmatic behavioural revenue at low traffic is negligible anyway
and direct sponsorship at any traffic is negotiated rather than auctioned. But if this ever grows
to the point where the auction is worth entering, the trade becomes real and this section should
be re-read rather than re-quoted.

**Recommendation on revenue: direct sponsorship first, contextual ads second, programmatic
behavioural not at all in v1.** Cost of keeping programmatic open later: structurally nothing —
you would add a consent-management platform for EU/UK, `tfat` tagging, and the age question would
become load-bearing. That is a later decision with a known shape, not a now decision.

### 5.4 GDPR Article 8 — narrower than it looks, for a reason already established

[Article 8](https://gdpr-info.eu/art-8-gdpr/) applies "[w]here point (a) of Article 6(1) applies"
— that is, **only to processing whose lawful basis is consent**, and only for information society
services offered directly to a child. It sets 16 as the default, lets member states legislate
lower but "not below 13 years", and requires the controller to "make reasonable efforts to verify"
parental authorisation "taking into consideration available technology".

`rights-and-privacy.md` §5b already established that this product's lawful basis is Article
6(1)(f) legitimate interests, not consent. **So Article 8 does not bind the core processing.**
Where it would bite is any processing you choose to base on consent — which, in practice, means
the cookie and ad consent you would need for behavioural advertising. Avoid consent-based
processing and Article 8 never engages. That is the same convergence as §5.3, arriving from the
European side.

If consent ever becomes necessary, the age threshold is not one number: the UK and Ireland set 13,
France 15, Germany and the Netherlands 16. A single hard-coded age would be wrong in most of
Europe.

### 5.5 DSA Article 28 — real, and probably disapplied

[Regulation (EU) 2022/2065](https://www.eu-digital-services-act.com/Digital_Services_Act_Article_28.html)
Article 28(1) requires providers of online platforms accessible to minors to put in place
appropriate and proportionate measures ensuring a high level of privacy, safety and security of
minors on their service. Article 28(2) prohibits presenting advertisements based on profiling as
defined in Article 4(4) GDPR using a recipient's personal data "when they are aware with
reasonable certainty that the recipient of the service is a minor". Article 28(3) adds that
compliance does not oblige providers to process additional personal data to assess whether a
recipient is a minor — the Regulation explicitly declines to force an age gate.

Article 28 sits in Chapter III Section 3 (Articles 19–28). **Article 19(1) disapplies that entire
Section to providers of online platforms qualifying as micro or small enterprises under
Recommendation 2003/361/EC**, except Article 24(3), and continues the exemption for 12 months
after a provider outgrows the status; Article 19(2) removes the exemption for designated very
large online platforms. A solo operator is a micro enterprise. **So Article 28 very likely does
not apply.**

Worth knowing anyway for two reasons. First, the exemption is a size exemption, so it expires on
success rather than on a change of law. Second, Article 28(2) is another regulator independently
reaching the conclusion in §5.3 — profiling-based advertising to minors is the thing that gets
prohibited, and contextual advertising is not. The recommended position complies with Article 28
whether or not Article 28 applies, which is the cheapest possible form of compliance.

### 5.6 The UK — the one that actually reaches a small site

Two regimes, and the second is the one most likely to be overlooked.

**The Age Appropriate Design Code.** [Section 123 of the Data Protection Act 2018](https://www.legislation.gov.uk/ukpga/2018/12/section/123)
required the Information Commissioner to produce a code of practice on age-appropriate design for
relevant information society services "likely to be accessed by children", children meaning under
18. On an honest reading, a dance-learning site is likely to be accessed by children. The Code has
no small-operator exemption. The good news is that its standards — data minimisation, high privacy
by default, no profiling by default, no nudge techniques, transparency in language a child can
read — are things the recommendations above already do, mostly for other reasons. The concrete
deliverable is a short data protection impact assessment recording that reasoning. It is a
document, not engineering.

**The Online Safety Act 2023, which is the sharper one.** A service where content is uploaded by
users and may be encountered by other users is a Part 3 user-to-user service, which this becomes
the moment a lesson can be shared. Ofcom published its children's access assessment guidance on
16 January 2025 with a completion deadline of 16 April 2025; services concluding that children are
likely to access them had to complete a children's risk assessment by 24 July 2025 and implement
protective measures from 25 July 2025. **There is no small-service exemption from the access
assessment** — size affects which Code measures are recommended, not whether the assessment is
owed. And without highly effective age assurance, a service must conclude that children can
normally access it, so the assessment's first stage is decided in advance for this product.

Calibrated view: the assessments are records, not systems, and Ofcom's enforcement attention has
gone to high-risk categories rather than small tutorial sites. Complete them as documents before
UK traffic is meaningful; do not let them block launch; do not pretend they are not owed.
`rights-and-privacy.md` §6.7 already rejected geo-blocking Europe and that reasoning is not
reopened here.

### 5.7 US state age-verification laws — narrower than the headlines

[*Free Speech Coalition, Inc. v. Paxton*, 606 U.S. ___ (27 June 2025)](https://supreme.justia.com/cases/federal/us/606/23-1122/)
upheld Texas H.B. 1181 under intermediate scrutiny. The scope is the point: the statute reaches
commercial sites where **more than one-third** of content is sexual material harmful to minors.
The decision is tethered to that threshold and to material obscene as to minors; it does not
authorise age verification for non-sexual content. A dance-learning site is nowhere near it. Some
states have enacted percentage-free versions of these statutes and those are where the general-
audience question will next be litigated — worth a note in the calendar, not a change to the
product.

**California's AADC (AB 2273) is live in part and should be tracked, but almost certainly does not
cover this service.** After a first preliminary injunction in September 2023, a partial Ninth
Circuit ruling in August 2024, a second full injunction in March 2025 and a second Ninth Circuit
opinion on 12 March 2026 (mandate issued 3 April 2026), the data protection impact assessment
provisions remain enjoined while several substantive obligations are now in effect. The reason it
probably does not reach here is threshold, not merits: CAADCA applies to a "business" as defined
by the CCPA, whose thresholds are roughly 25 million dollars in annual revenue, personal
information of 100,000 or more California consumers or households, or half of revenue from selling
or sharing personal information. A free solo-operated site meets none. **Re-check on growth**, and
note that the 100,000-consumer threshold is a traffic number, not a revenue one, so it is the one
that could be crossed without noticing.

App-store age-verification laws (Utah, Texas) bind app stores and app developers. A website is out
of scope.

### 5.8 Age estimation — the ironic option, and why it is the wrong one

Facial age estimation would be self-defeating here for reasons that go beyond taste.

Under GDPR Article 4(14), biometric data means personal data resulting from specific technical
processing relating to physical characteristics "which allow or confirm the unique identification"
of a person. Age estimation categorises rather than identifies, which is the same distinction
*Zellmer v. Meta* drew in `rights-and-privacy.md` §4b — so it arguably is not Article 9 data. But
BIPA's enumerated list at 740 ILCS 14/10 names a "scan of hand or face geometry" directly, and
§4 of the prior research spends its length establishing that this pipeline creates nothing on that
list. Adding a face scan at the front door would create one, deliberately, for the sole purpose of
avoiding a privacy problem. It also requires camera access the product does not have and does not
want — record-yourself is explicitly out of v1 per PRD §5 — and it means sending images of
children's faces to a vendor.

Both European instruments point the same way: DSA Article 28(3) says compliance does not require
processing extra personal data to determine whether a recipient is a minor, and Recital 71 adds
that the obligation should not incentivise collecting more data, citing data minimisation. **Never
do age estimation on this product.**

### 5.9 Recommendation, exact copy, exact placement

**Do not gate the site. Ask for age at exactly one point, ask for month and year only, and act on
the answer.**

1. **Anonymous visitors and uploaders are never asked their age.** There is no duty to ask, asking
   would collect personal data you do not need, and asking is what creates actual knowledge. This
   also means an age question never touches the conversion step the whole product depends on.
2. **At account creation only, ask for month and year of birth in a neutral field.** The FTC's
   description of a neutral screen is a "system that allows the user to freely enter month and
   year of birth"; a drop-down restricted to qualifying years is not neutral, and a single "I am
   over 12" checkbox is not neutral. Do not say beforehand that under-13s cannot sign up — the FTC
   names that as encouraging falsification. Month and year, not full date: you need the age band,
   not the birthday.
3. **Under 13: no account, and say what still works.** Blocking is permitted for a general-audience
   service, and the FTC states that an operator who screens neutrally "may rely on the age
   information its users enter, even if that age information is not accurate". Set a local flag so
   a back-button retry does not present a fresh form, which the FTC's staff guidance recommends.
4. **Do not treat 13 to 16 differently in v1.** There is nothing to differentiate: no consent-based
   processing (§5.4), no profiling, no behavioural ads, no messaging between users, no public
   index. Adding a teen tier now would be building a mechanism with nothing to do.
5. **Record the age band, not the date.** Store a derived band (`under_13` / `13_17` / `18_plus`)
   and discard the month and year after deriving it. That answers the commercial question — the
   age distribution of your signed-in audience, which a sponsor may ask — without holding a
   birthdate.

The copy is in §4.4 above (`account.ageLabel`, `account.ageWhy`, `account.ageBlocked`), placed in
the account creation step and nowhere else. Repeated here for the checklist:

```
Month and year you were born
We ask so an account is not set up by a child. Nothing else uses it.

You need to be 13 or older for an account. The site works without one, and your
lessons stay in this browser.
```

Three lines. It says why, it says what happens, it does not claim verification, and it does not
imply the site is unavailable. `DESIGN.md` §7h's test — would someone who understood exactly how
this works feel misled — passes: the mechanism described is the mechanism that exists.

**What changes if the product monetises differently.** If it ever charges users, payment creates a
far better age signal than any screen and the contract-law question in GDPR Article 8(3) arrives
with it. If it ever runs behavioural advertising, this entire section is rebuilt: the age question
moves to the front door, becomes load-bearing, and needs a consent-management platform beside it.
That is the real cost of the programmatic path and it belongs in the decision, not in a footnote.

---

## 6. Launch checklist

### 6.1 Needs a lawyer — four items, not five

These are in addition to, not instead of, the five in `rights-and-privacy.md` §8. Two of those
five — the terms and privacy notice, and the DPIA/Art. 30/Art. 27 question — now have to cover
advertising as well, which is the only change.

1. **The advertising and sponsorship terms.** Not the ad network's boilerplate, which you accept
   as-is; the *disclosure* obligations on your side. Whether the site needs an FTC-compliant
   sponsorship disclosure, what you may represent to a sponsor about your audience, and whether
   any audience claim you make creates a warranty. One hour.
2. **Whether the UK Online Safety Act Part 3 duties apply once lessons are shareable, and what a
   proportionate children's risk assessment looks like for a service this size** (§5.6). This is
   the item most likely to be missed entirely, and it has no small-service exemption. Ask before
   UK traffic is meaningful, not at launch.
3. **The privacy notice's advertising and analytics sections specifically** — the legitimate-
   interests balancing for server-side measurement, and the representation that you do not do
   cross-site tracking. This folds into `rights-and-privacy.md` §8's terms-and-privacy-notice
   item rather than adding a new engagement.
4. **Confirmation that the general-audience COPPA verdict in §5.1 is right**, given that the
   audience skews young and the FTC weighs the age of users on similar services. This is the one
   conclusion in this document where being wrong is expensive — child-directed status with
   behavioural ads running is the bad outcome — and it is a 30-minute question for someone who
   does this work. Bring §5.1's table; it is the form the answer takes.

### 6.2 Builder decides alone — no lawyer needed

- **No third-party analytics at launch; first-party event log** (§3.5). Choosing to collect less
  never needs advice.
- **The nine events and the 13-month analytics retention** (§3.6).
- **Optional accounts, creator token, magic link** (§4.5). Product and security decision.
- **No OAuth and no passkeys in v1** (§4.3).
- **Month-and-year age question at account creation only; block under-13 accounts; store the band,
  discard the date** (§5.9). The FTC's own FAQ answers this directly.
- **No age estimation, ever** (§5.8).
- **Adult dancers in all demo and marketing footage** (§5.1). Cheapest item here.
- **Keep §7g's ban on points, streaks and badges** (§5.1). Already written; now also evidence.
- **Direct sponsorship first, contextual ads second, no programmatic behavioural in v1** (§5.3).
- **Refuse child-targeted ad creative** (§5.1).
- **Buy hosted Plausible with a public dashboard if and only if a sponsor demands independent
  numbers** (§3.7). Not before.

### 6.3 Order

1. Creator token and the anonymous ownership model, because `rights-and-privacy.md` §6.1's removal
   path and D7's deletion both depend on there being an owner.
2. The event table and the nine events, because they cost almost nothing and the first weeks of
   data are the ones you cannot go back and collect.
3. Magic-link sign-in with the age question, before sign-up opens to strangers — the same tripwire
   §6.6 of the prior document names for the takedown agent and the terms.
4. Advertising, last, and only after §6.1 item 1.

---

## 7. What this changes in `OPEN-DECISIONS.md`

**D5** is updated to record this recommendation, marked as a recommendation rather than a
decision. **D6** and **D7** are not resolved here, but both get easier: the creator token gives D7
an owner to authorise deletion and to restore after a wrongly-honoured removal request, and §3.6's
13-month analytics retention settles the analytics half of D6 independently of the clip half.
**A6** ("My lessons / library", DEFER) is now answerable — the library is browser-local by default
and follows an email if one is added — but this document does not claim to close it, because the
screen still needs designing.

**D8** is unchanged. Nothing here contradicts it. The one addition is that §512(i) now has a
subject, which the D8 note flagged as missing.

---

## 8. Calibration — what is and is not worth worrying about

Stated bluntly so the document is not read as uniformly alarmed.

**Genuinely worth acting on before strangers arrive:**
- Having an owner for a lesson, so removal and restoration both work (§4.1).
- Not asking for birthdates on pages everyone sees (§5.2).
- Keeping demo and marketing footage adult (§5.1).
- Not running behavioural advertising (§5.3).

**Real but cheap, and dischargeable as paperwork:**
- The UK children's access assessment and a short DPIA (§5.6).
- A line in the privacy notice about what is counted and for how long (§3.3).

**Unsettled, and here is how to not care:**
- Whether cookieless analytics needs consent in the EU. The EDPB's 2024 guidelines made this
  murkier, not clearer, and no court has tested it. Count server-side and the question does not
  arise (§3.3).
- Whether the DSA's minors provision applies. Article 19(1) very likely exempts a micro
  enterprise, but the recommended posture complies either way (§5.5).

**Not worth worrying about now:**
- US state age-verification statutes (§5.7). Aimed at sexual material; the threshold is a third of
  content.
- California's AADC (§5.7). Threshold-gated on CCPA business status; re-check at 100,000 California
  users.
- GDPR Article 8 (§5.4). It conditions consent, and the lawful basis here is not consent.

---

## 9. What I could not verify

1. **The FTC's February 2026 policy statement on age-verification data.** A secondary source
   reports that on 25 February 2026 the FTC issued a statement limiting COPPA enforcement where
   children's data is collected for age-verification purposes without prior parental consent,
   conditional on compliance "in every other respect". I did not open the statement. It would, if
   accurate, make an age screen slightly safer than §5.2 assumes — it does not change the
   recommendation, because the recommendation is to ask fewer people rather than to ask more
   safely. Read it before relying on it.
2. **The exact `ee/LICENSE` terms in the PostHog repository.** I read the top-level `LICENSE`,
   which carves out `ee/` by reference. I did not open `ee/LICENSE` itself. This does not affect
   the recommendation, since the recommendation is not to deploy PostHog, but anyone who reverses
   that decision must read it — it is the one file that could contain a hosted-service or
   competing-product restriction.
3. **Whether Umami's tracker touches `sessionStorage` in its current release.** Umami is
   documented as cookieless, and its unique-visitor method is a server-side rotating hash, but
   some builds use client-side caching for the session id. Since Umami is the escape hatch rather
   than the recommendation, this only needs checking at the moment it is adopted — and if it does
   touch device storage, §3.3 layer one applies to it.
4. **The verbatim operative text of DSA Articles 19 and 28, and of ePrivacy Article 5(3) as
   amended by 2009/136/EC.** EUR-Lex served me the recitals and the pre-2009 text respectively; I
   read Articles 19 and 28 from a secondary reproduction of the final Regulation, cross-checked
   against DSA Recitals 57 and 71, which state the same policy. The article numbering, the
   Section 3 boundary (Articles 19 to 28) and the Article 24(3) carve-out are consistent across
   both sources. Confirm against the Official Journal before relying on the exact wording.
5. **The verbatim text of DPA 2018 s.123(1)–(6).** legislation.gov.uk returned the section's
   headings and notes but truncated the operative subsections. The scope phrase "likely to be
   accessed by children" and the under-18 definition are well sourced; the precise duties are the
   Commissioner's, not mine, so this does not affect the analysis.
6. **Whether Ofcom would in practice treat a service of this size as in scope of Part 3 before it
   has public sharing.** The statutory definition plainly covers user-uploaded content encountered
   by other users, and there is no size exemption from the access assessment. What I could not
   establish is Ofcom's practical posture toward pre-launch and invite-only services. This is
   §6.1 item 2.
7. **The certiorari citation for *Ventura Content v. Motherless*.** The reporter citation
   885 F.3d 597 (9th Cir. 2018) is solid and the holding is reported consistently across several
   sources, but one source's cert-denied citation appeared garbled. I did not open the slip
   opinion. The holding this document relies on — that an informal, unwritten, unlogged
   repeat-infringer practice by a one-person operator can be reasonably implemented — is reported
   identically everywhere I looked, but it is a summary-judgment holding in one circuit and should
   not be over-read.
8. **Advertising CPM figures.** §5.3 asserts that contextual and direct inventory earn less than
   behavioural inventory and that the gap is mostly theoretical at low traffic. Both are
   widely-repeated industry positions; I did not verify either against a primary source and
   deliberately quoted no numbers.
9. **Hosted terms for any analytics vendor.** `grounding-models.md` §1.6's discipline says the
   hosted terms are a separate axis from the code licence. I read code licences. I did not read
   PostHog Cloud's, Plausible Cloud's or Umami Cloud's terms of service or data processing
   agreements, because the recommendation is to buy none of them. If hosted Plausible is bought
   under §3.7, its DPA and sub-processor list must be read then.

---

## 10. Sources

**Primary — statute, rule and regulation**

- [16 C.F.R. § 312.2](https://www.law.cornell.edu/cfr/text/16/312.2) — definitions: directed to children, mixed audience, personal information, support for the internal operations
- [16 C.F.R. § 312.5](https://www.law.cornell.edu/cfr/text/16/312.5) — verifiable parental consent, separate consent for third-party disclosure, the (b)(2) methods, the (c)(7) persistent-identifier exception
- [Children's Online Privacy Protection Rule, 90 Fed. Reg. (22 April 2025)](https://www.federalregister.gov/documents/2025/04/22/2025-05904/childrens-online-privacy-protection-rule) — effective 23 June 2025, general compliance date 22 April 2026
- [17 U.S.C. § 512](https://www.law.cornell.edu/uscode/text/17/512) — §512(i)(1)(A) repeat-infringer condition
- [Regulation (EU) 2016/679 (GDPR) Article 8](https://gdpr-info.eu/art-8-gdpr/)
- [Regulation (EU) 2022/2065 (DSA) Article 28](https://www.eu-digital-services-act.com/Digital_Services_Act_Article_28.html) and [Article 19](https://www.eu-digital-services-act.com/Digital_Services_Act_Article_19.html)
- [Directive 2002/58/EC Article 5(3)](https://eur-lex.europa.eu/legal-content/EN/ALL/?uri=CELEX:32002L0058) as amended by 2009/136/EC
- [Data Protection Act 2018 s.123](https://www.legislation.gov.uk/ukpga/2018/12/section/123) — the Age Appropriate Design Code

**Primary — regulator guidance**

- [FTC, Complying with COPPA: Frequently Asked Questions](https://www.ftc.gov/business-guidance/resources/complying-coppa-frequently-asked-questions) — neutral age screens, actual knowledge, no duty to investigate, mixed audience
- [EDPB Guidelines 2/2023 on the technical scope of Art. 5(3) ePrivacy](https://www.edpb.europa.eu/system/files/2024-10/edpb_guidelines_202302_technical_scope_art_53_eprivacydirective_v2_en_0.pdf) — final version, October 2024 plenary
- [CNIL, Sheet no. 16: use analytics on your websites and applications](https://www.cnil.fr/en/sheet-ndeg16-use-analytics-your-websites-and-applications) — Deliberation 2020-092 exemption conditions; evaluation programme replaced by self-assessment on 1 January 2026

**Case law**

- [*Perfect 10, Inc. v. CCBill LLC*, 488 F.3d 1102 (9th Cir. 2007)](https://law.justia.com/cases/federal/appellate-courts/F3/488/1102/496805/) — "reasonably implemented" under §512(i)
- [*Ventura Content, Ltd. v. Motherless, Inc.*, 885 F.3d 597 (9th Cir. 2018)](https://www.leagle.com/decision/infco20180314132) — a one-person operator's informal repeat-infringer practice
- [*Free Speech Coalition, Inc. v. Paxton*, 606 U.S. ___ (2025)](https://supreme.justia.com/cases/federal/us/606/23-1122/) — Texas H.B. 1181, one-third threshold
- *NetChoice, LLC v. Bonta* — California AADC, Ninth Circuit opinion of 12 March 2026, mandate 3 April 2026 (read through firm summaries; see §9)

**Licences and vendor documentation, read directly**

- [PostHog `LICENSE`](https://github.com/PostHog/posthog/blob/master/LICENSE) — MIT Expat except `ee/`
- [PostHog, self-hosting documentation](https://posthog.com/docs/self-host) — officially unsupported, no customer support, free-plan features only, no release tags
- [PostHog, session replay privacy](https://posthog.com/docs/session-replay/privacy) — masking defaults, opt-in canvas capture
- [PostHog, GDPR compliance guide](https://posthog.com/docs/privacy/gdpr-compliance) — cookie banner guidance, cookieless mode, processor position
- [Plausible `LICENSE.md`](https://github.com/plausible/analytics/blob/master/LICENSE.md) — AGPL-3.0
- [Plausible, Introducing Community Edition](https://plausible.io/blog/community-edition) and [Trademark Guidelines](https://plausible.io/trademark)
- [Umami `LICENSE`](https://github.com/umami-software/umami/blob/master/LICENSE) — MIT
- [Matomo licences](https://matomo.org/licences/) — GPL-3.0-or-later core, InnoCraft EULA premium plugins
- [Google AdSense, tag an ad request for age restricted treatment](https://support.google.com/adsense/answer/9007197) and [Ad Manager, tag for age treatment](https://support.google.com/admanager/answer/3671211)

**In repo**

`docs/research/rights-and-privacy.md` (D8 — §5b lawful basis, §6.1 removal path, §6.2 hold less,
§6.4 takedown agent, §8 lawyer list) · `docs/research/grounding-models.md` §1.5–§1.7 (the
multi-axis licence method, and the non-commercial bar) · `docs/OPEN-DECISIONS.md` D5–D8, A6 ·
`docs/DESIGN.md` §7d, §7e, §7g, §7h, §11 · `docs/PRD.md` §2 G2 (the AGPL decision), §5 ·
`packages/motion-contract/schema/job-status.schema.json`,
`packages/motion-contract/schema/motion-result.schema.json` · `apps/web/lib/copy.ts`,
`apps/web/app/upload/page.tsx`, `apps/web/test/copy.test.ts` (branch `w7-marketing`)
