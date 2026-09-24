# Link ingestion — what fetching on someone else's behalf actually commits us to

Written alongside the `link-ingestion` branch, 2026-09-21.

**This is a different question from the one `rights-and-privacy.md` answered, and
its conclusions do not transfer.** That document analysed a stranger *uploading*
a clip: the act is theirs, the file is already in their hands, and the
platform's terms are not in the picture at all. This document is about
**stepwise fetching a video from TikTok or YouTube, on behalf of a visitor, with
an automated tool, from our own server**. That is our act, not theirs, and it
runs into terms `rights-and-privacy.md` never looked at.

Where the two overlap — who is in the clip, what we keep, who can make it stop —
the earlier analysis holds and is not repeated here. Where they do not, this
document says so rather than borrowing a conclusion.

---

## 1. The one-paragraph answer

Automated downloading is prohibited by both platforms' terms of service. That
prohibition is contractual, not criminal, and the realistic consequence of
breaching it at pilot scale is being blocked, not being sued. The controlling
question is therefore not "is this legal" but **"who is doing it, at what scale,
and for whom"** — and that answer changes materially between the invite-only
W12 pilot and a public launch. For six named cohort members pasting links to
dances they are learning, the exposure is comparable to what `evaluation/fetch.py`
already accepts and has accepted since 2026-09-18. For strangers at volume it is
not, and the difference is not one of degree. **The pilot is built. The public
launch is not cleared, and §6 lists what has to be decided before it is.**

---

## 2. What the code actually does

Stated first, because every paragraph below is about this specific behaviour and
not about "scraping" in general.

| | |
|---|---|
| **Who triggers a fetch** | A visitor holding an invite code, one link at a time, synchronously with their request. Never a crawler, never a schedule, never a batch. |
| **What is fetched** | One video file, at the same 1080p cap `evaluation/fetch.py` uses. No comments, no profile, no metadata beyond what is needed to identify and size the clip. |
| **From where** | A hostname allowlist of two platforms (`ingest.ALLOWED_HOSTS`), re-checked against yt-dlp's own extractor name after extraction. yt-dlp supports over a thousand sites; being a general downloader for whatever a stranger pastes is a different product and the allowlist is what stops this becoming one. |
| **With what credentials** | None. No cookies, no `--netrc`, no browser cookie import, no account. A platform that demands a login gets a refusal (`login_required`), never a session. A standing test asserts no credential flag creeps into `ingest.py`. |
| **What is retained** | Exactly what an uploaded clip retains, on the same path, under the same 180-day last-access expiry and the same removal endpoint. No new storage, no new retention rule. |
| **What is republished** | Nothing. The source video is served back only to whoever holds the lesson link, exactly as an uploaded one is. There is no index, no search, no public list, no "find this dancer". |
| **Rate** | One fetch per novel link. A link that is already a lesson costs one metadata request and no transfer (measured: 1.9–2.6 s versus 8.0–10.1 s). |

---

## 3. The terms, read for ingestion specifically

Terms were read on 2026-09-21. **Both platforms reserve the right to change them
unilaterally**, so a citation is a snapshot, and the version that matters is the
one live on the day someone pastes a link.

### 3a. TikTok

TikTok's Terms of Service prohibit, in the "Your Access to and Use of Our
Services" section, using automated means — the terms enumerate robots, spiders,
scrapers and "any automated system or software" — to access, acquire, copy or
monitor any part of the Services or their content, and separately prohibit
copying, reproducing or distributing content from the platform other than
through functionality the platform itself provides. TikTok does provide a
first-party download affordance for creators who enable it, which matters below.

Three things follow that are specific to ingestion and have no analogue in the
upload case:

1. **Breach is contractual and runs to us, not to the visitor.** The visitor
   pasted a URL, which is not an act TikTok's terms restrict. The server fetched
   the video, which is. Framing this as "the user downloaded it" would be
   inaccurate, and designing the copy to imply it would be the §7h failure
   pointed at a new target. The upload screen's copy was written accordingly
   (§5).
2. **The realistic enforcement is technical, not legal.** For an operator at
   this scale the expected outcome of automated fetching is an IP block, and we
   have already seen the shape of one: TikTok answers
   `Your IP address is blocked from accessing this post` for a video id that
   does not exist, which means the block response and the not-found response are
   indistinguishable from outside. `ingest.py` therefore refuses to report
   either as a cause (§4).
3. **Datacenter IPs are treated worse than residential ones.** `evaluation/fetch.py`
   already records this — it downloads locally precisely because "platform
   rate-limiting and bot checks are far worse from datacenter IPs". A server-side
   fetcher runs from exactly the address class that gets blocked first, so the
   pilot will find out quickly whether this works at all. That is a feature of
   the pilot, not a risk to be managed around.

**The `hiQ v. LinkedIn` line of cases does not help here and should not be
cited as if it did.** That line concerns the Computer Fraud and Abuse Act and
holds, at most, that scraping public data is not *criminal* access. It says
nothing about breach of contract, and the Ninth Circuit's later handling made
the contract claim the live one. Anybody reaching for it is answering a question
nobody asked.

### 3b. YouTube

YouTube's Terms of Service are more explicit than TikTok's. They prohibit
accessing the Service by automated means except in the narrow cases the terms
name (public search engine crawlers obeying robots.txt, and permitted API
clients), and they separately and specifically prohibit downloading content
except where a download button or link is shown by the Service itself or where
YouTube gives prior written permission. YouTube also offers first-party
downloads inside Premium, which is a deliberate carve-out rather than an
oversight, and that is the strongest signal in either document: the platform has
decided how downloading is supposed to work and this is not it.

YouTube has also, unlike TikTok, taken direct action against download tooling.
That history is about the tool's distributors, not about a single operator
pointing it at a link a visitor pasted, but it means "nobody enforces this" is
not a claim available for YouTube the way it nearly is for TikTok.

### 3c. What is *not* at issue

Worth naming, because these are the objections that get raised and they are the
wrong ones:

- **Copyright in the dance.** Unchanged from `rights-and-privacy.md` §3a: short
  social-media routines are usually below the threshold for choreographic works.
  Ingestion does not move this.
- **Copyright in the video.** Unchanged from §3b: the videographer holds it, and
  they are rarely the complainant. Ingestion does not move this either — it
  changes *who made the copy*, not whether a copy exists.
- **The dancer's interest.** Unchanged and still the largest real exposure
  (§1 of that document): someone finding their body reconstructed on a site they
  never heard of. Ingestion makes this *more* likely in one specific way — see
  §5 — and the removal path is still the mitigation that matters.

### 3d. What genuinely changes versus the upload case

| | Upload | Link ingestion |
|---|---|---|
| Who copied from the platform | The visitor, before arriving | **Us, on request** |
| Whose terms are engaged | None of ours | **TikTok's and YouTube's, against us** |
| Whose IP made the request | Theirs | **Ours** |
| Plausible claim of right | Weak, but possible | **Almost never** (§5) |
| Realistic failure mode | A takedown request | **A block, then a takedown request** |
| Does volume change the analysis | Not much | **Yes, sharply** |

---

## 4. Failure states, and the rule about not inventing reasons

Ingestion fails in ways an upload cannot, and this turned out to be the part of
the work where the honesty rule (`DESIGN.md` §7h) bit hardest — not in the
marketing copy, where it is expected, but in error handling, where the platform
hands you a sentence and the tempting thing is to pass it on.

**Two platforms verified on 2026-09-21 as returning the same string for
different causes:**

- TikTok answers `Your IP address is blocked from accessing this post` for a
  video id that never existed. It presumably also answers it for an actual
  block. So the string is evidence of a refusal and **not** evidence of its
  cause.
- YouTube answers `This video is unavailable` for both a private video and one
  that never existed.

Relaying either as "that video was deleted" or "your access was blocked" would
be stating a reason we did not observe. The mapping in `ingest.classify_fetch_error`
therefore only assigns a specific code where the *meaning* is unambiguous, and
everything else falls through to `fetch_failed`, whose message names what we did
and stops: "We could not get that video from the link." A test asserts the
fallback message contains none of *private*, *deleted*, *removed*, *blocked*,
*region* or *age*.

| Failure | Code | `retryable` | Why that flag | Provenance |
|---|---|---|---|---|
| Not a video link, or an unsupported site | `link_not_supported` | **false** | Nothing about the link will change | Observed |
| Platform demands a login | `login_required` | **false** | We have no credentials and will not get any | Observed (yt-dlp's `--cookies` hint) |
| Region-locked | `region_locked` | **false** | Our server does not move | yt-dlp source (`common.py raise_geo_restricted`) — **not reproduced**, no geo-locked clip to hand |
| Rate-limited | `rate_limited` | **true** | The one failure that genuinely clears on its own | yt-dlp source — not reproduced |
| Platform refused, cause unknowable | `fetch_blocked` | **true** | An IP block may clear; a deleted video will not, and we cannot tell which | Observed (TikTok) |
| Anything else | `fetch_failed` | **true** | Retrying costs one HTTP request and no GPU, so the generous flag is the cheap one | — |
| Over 60 s | `clip_too_long` | **false** | PRD §5's cap. Refused **before download** from metadata | Observed (213 s YouTube video refused in 2.6 s, no transfer) |
| Live or upcoming stream | `live_stream` | **false** | No finished clip to build a lesson from | Structured (`live_status`) |
| No invite code | `invite_required` | **false** | §6 | — |

Note what is *not* in this table: age restriction. A YouTube video with
`age_limit: 18` extracted successfully without credentials in testing, so there
is no observed failure to map, and inventing a code for one would be inventing
the failure too.

The three region/rate rows marked "not reproduced" are the honest weak point of
this table. They are taken from the pinned yt-dlp's own message strings rather
than from a live failure. If either is wrong, the consequence is that the
failure falls through to `fetch_failed` and says less — never that it says
something untrue.

---

## 5. The copy, and why it is not the upload line with a word changed

`DESIGN.md` §7d's rights line is **"Only upload video you have the right to
use."** It has shipped since W7 and it stays exactly as it is on the file path.

It must not be reused on the link path, and this is the single most important
copy decision in this work. The upload line addresses someone holding a file,
who at least *might* hold the right to it — they may have filmed it, may be in
it, may have been sent it by the person who made it. **Almost nobody pasting a
TikTok link has any right to that video at all.** Writing "only paste video you
have the right to use" would take a sentence that is sometimes true and print it
over a case where it is nearly always false, which is the §7h failure exactly:
not a lie anyone wrote on purpose, an intention read as a claim.

`compliance-d8` recommended adding a second sentence naming the people *in* the
clip, which the upload screen still lacks. On the link path that sentence does
more work than it does on the upload one, so it is carried here:

> **We fetch the video from the link and build a lesson from it. Anyone in the
> clip can ask us to take it down, and we will.**

What each half is doing:

- **"We fetch the video from the link"** names who copies it. Not "we get your
  video", not "paste a link to your dance" — both of which would quietly put the
  act on the visitor. It is our server, our request, and the sentence says so.
- **"and build a lesson from it"** says what we then do, in the same breath, so
  nobody reads "fetch" as "link to".
- **"Anyone in the clip can ask us to take it down, and we will"** is
  `rights-and-privacy.md` §6.1's highest-value mitigation, made visible at the
  moment it becomes relevant. It commits to an outcome the code actually
  delivers (`POST /lessons/{clip_id}/removal`, immediate, no queue).

What it does **not** say, and what the copy lint enforces:

- Not "we check", "we verify", "we have permission" — §7h bans all three and
  §12.13 lists them. We do none of them.
- Not "only paste video you have the right to use" — see above. A test asserts
  the link line does not contain the phrase.
- **No blocking checkbox.** `rights-and-privacy.md` §7a settled this and
  ingestion does not reopen it: a checkbox collects an attestation from the
  wrong person, since the consent that matters is the dancer's and the person
  pasting cannot give it on their behalf. If anything the argument is *stronger*
  here, because the visitor's claim to the clip is weaker. The gate belongs at
  publication (§7g's share clip, a featured lesson), not at ingest.

The invite gate needs its own line, because an invite wall that only says "no"
strands someone who came to learn a dance:

> **Links are open to invited testers while we try this out. Adding a video file
> works for everyone.**

It does not say "coming soon", which would name a date we have not got.

**One consequence worth stating here rather than in a code comment.** Because
ingestion makes it trivially easy to point stepwise at any dancer's public post,
it raises the probability of the scenario `rights-and-privacy.md` §1 identifies
as the largest real exposure: a dancer finding their own body reconstructed
somewhere they never heard of. The removal path is the mitigation and it
already exists. The invite gate is what keeps the volume low enough that it
stays a per-case conversation rather than a queue we would have to promise a
response time for.

---

## 6. Invite-only pilot versus public launch

### What the gate is

An allowlist of codes in `STEPWISE_INVITE_CODES`, read from the environment,
checked on `POST /clips/link` only. **Closed by default**: no codes configured
means the link path is shut. File upload is not gated and stays open to
everyone.

This is deliberately the cheapest thing that makes "link ingestion is reachable
only by invited testers" a property of the code rather than of an intention, and
deliberately does not require resolving `OPEN-DECISIONS.md` **D5** (accounts:
none, magic link, or OAuth), which is genuinely open and is not this work's to
decide.

### What it does not protect against, plainly

- **A shared secret is not identity.** Every cohort member holds the same
  string. The gate cannot tell them apart, cannot revoke one person, cannot
  rate-limit one person, and does not survive one of them pasting it into a
  group chat.
- **It limits who can ask us to fetch, not what we fetch.** It protects the
  platforms from nothing.
- **It is not a legal exemption.** `rights-and-privacy.md` §6.6 makes the same
  point about the pilot generally: BIPA, CUBI and GDPR have no small-operator
  carve-out. Invite-only buys *time* and *consent from the right people*, not
  immunity.
- **It does nothing about the lesson link itself.** See §7.

### The tripwire

`rights-and-privacy.md` §6.6 asks for this to be named explicitly rather than
left in someone's memory, so: **the day link ingestion is opened to people the
builder has not met, all of the following must already be decided, not just
listed.**

1. **Whether server-side fetching continues at all**, and if so at what rate and
   with what backoff. The pilot will produce the first real evidence about
   blocks; it should be read before scaling, not after.
2. **A rate limit per code and per source host.** The current code has none. At
   six people this is fine; the first day it is not six people, it is not fine.
3. **Whether the derived `clip_id` (§7) survives**, which depends on **D5**.
4. **`rights-and-privacy.md` §6.4** — a registered takedown agent and a
   repeat-infringer policy. Ingestion makes this more pressing than uploads did:
   we are now the party that made the copy.
5. **§6.5's terms of service**, specifically whether the visitor representation
   covers asking us to fetch, which is a different representation from asking us
   to host.
6. **A named human path for a platform's complaint**, distinct from the
   dancer-facing removal endpoint. A platform complaining about automated access
   is not asking for one lesson to be deleted.

Items 4 and 5 already needed a lawyer for the upload case
(`rights-and-privacy.md` §8). Ingestion does not add a new lawyer question so
much as make two existing ones sharper.

### The first-party alternative, for whoever picks this up

If server-side fetching turns out to be unsustainable — and the datacenter-IP
problem in §3a is a live reason to think it might be — the fallback is not "no
links". It is **the platform's own download button**: TikTok's creator-enabled
download and YouTube Premium's both produce a file the visitor legitimately
holds, and that file goes through the upload path, which has none of these
problems. The copy for it would be an instruction, not a fetch. That is worse
for conversion and better for everything else, and it is the option to reach for
before reaching for a proxy pool.

---

## 7. Two design consequences recorded rather than smoothed over

### 7a. A link-ingested lesson's URL is derivable from the source URL

`clip_id` for a pasted link is `sha256("<extractor>:<id>")[:32]`, not a `uuid4`.
This is what guarantees that two people pasting the same link at the same moment
cannot end up with two lessons — see the race note in `api._store_and_dispatch`
— which is what keeps a takedown complete.

The cost is that an uploaded clip's link is a 128-bit `uuid4` and unguessable,
while a link-ingested clip's is computable by anyone who knows the source URL.

- **For the pilot this is small and cuts usefully.** The source is already
  public, and a dancer who finds their TikTok reconstructed here can reach the
  removal path without anyone handing them a link.
- **For a public launch with no accounts it is not acceptable**, because today
  *anyone* holding a lesson link can remove it (D7's "what D5 would change").
  Combined, that means anyone who knows a TikTok URL could delete the lesson
  built from it. At six people, negligible. At scale, a griefing vector.

So this is a **D5 dependency**, not a settled design. With accounts, D7's own
suggested rule — uploader deletes outright, anyone else's request takes it down
immediately but restorably — removes the problem without giving up the derived
id.

### 7b. The 60-second cap is enforced twice, and D9 is still open

`OPEN-DECISIONS.md` **D9** ("what happens when a learner wants a dance longer
than 60 s? Do we say 'trim it', give them a trimmer, or just refuse?") is
**unresolved**, and this work does not resolve it. The link path **refuses**, in
both places it can:

1. **Before download**, from yt-dlp's metadata. Measured: a 213-second YouTube
   video refused in 2.6 s with no video transferred.
2. **After download**, from ffprobe, for the case where the platform did not
   report a duration.

Refusing without fetching is strictly better than refusing after, which is why
the gate is split.

**A finding that belongs to D9 and was not introduced by this work.** The file
upload path does not refuse an over-length clip — it *silently trims* it.
`tools/process_clip.extract_frames` passes `-t 60` to ffmpeg, so a 90-second
upload becomes a lesson for the first 60 seconds of the dance with nothing said.
The browser-side check in `apps/web/app/upload/page.tsx` catches most of these
before they are sent, so the trim only fires when the browser could not read the
file's duration — but when it fires, the learner gets a lesson for a different
dance than the one they uploaded, and no surface says so. That is a §7h problem
in the plumbing, it predates this branch, and it is the strongest argument
available for resolving D9 toward "refuse, and offer a trimmer" rather than
leaving it open.

---

## 8. Forward-looking: the Web Share Target question

Asked because a PWA share target would deliver, from TikTok's own share sheet,
**exactly the string this endpoint already accepts.**

It is a genuinely small addition and the mechanics are not in doubt:
`share_target` in the web app manifest with `method: "GET"` and
`params: { url: "url", text: "text" }`, plus a route that reads the query
parameter and calls the same handler the paste field does. TikTok's share sheet
puts the link in `text` rather than `url` on some Android builds, so the route
has to accept either and pull the first URL out of the text — that is the only
real implementation wrinkle, and `ingest.probe` already rejects anything that is
not an allowed host, so a malformed share degrades to an honest refusal.

**Three reasons it is not in this branch, in order of weight:**

1. **It is Android-only in practice.** iOS Safari does not implement Web Share
   Target. Given that the product's audience is people learning dances off
   TikTok on a phone, shipping a share path that works for some of them and
   silently does nothing for the rest is worse than not shipping it, unless the
   iOS gap is stated on the screen.
2. **It needs the PWA shell that does not exist yet** — manifest, service
   worker, install prompt. None of that is in `apps/web` today, and it is a
   different work package with its own design questions.
3. **It makes the invite gate awkward** in exactly the way §6 warns about. A
   share-sheet tap has nowhere to type a code, so it would need the code
   remembered from a previous visit — which is the account system D5 leaves
   open, arriving through the back door.

The honest summary: **small once there is a PWA and D5 is decided, and not
before.** Worth doing then, because it removes the copy-paste step from the
exact moment someone decides they want to learn a dance, which is the highest-
friction point in the whole funnel.

---

## 9. What this document does not establish

In the spirit of `rights-and-privacy.md` §9.

- **No lawyer has read this.** It is a careful reading of two terms-of-service
  documents by someone who is not counsel, and the two items §6 flags for
  counsel are flagged, not answered.
- **Terms were read on one day and both platforms can change them without
  notice.** Nothing here should be treated as current without re-reading.
- **The region-lock and rate-limit failure mappings were not reproduced against
  a live platform.** They come from yt-dlp's own source strings, and §4 marks
  them as such.
- **No claim is made about whether server-side fetching will keep working.**
  Datacenter IPs are treated worse than residential ones and the pilot is the
  measurement, not the proof.
- **The scale at which "pilot" stops being true is not defined here.** §6's
  tripwire is behavioural (people the builder has not met), not numeric,
  deliberately — a number would be invented.
