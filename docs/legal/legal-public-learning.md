# Learning in public: the legal picture for stepwise, by stage

> **This is research, not legal advice.** Neither the author nor the builder is a lawyer. It
> builds on `rights-and-privacy.md` (uploads, biometrics, GDPR), `../research/link-ingestion.md` (platform
> terms) and the identity/age research on `research-identity-analytics`, and covers what they did
> not: **public** lessons, embedding, a curated library and revenue. §7 lists what a lawyer has to
> confirm. Terms were read on 2026-09-23 and can change without notice.

## 1. Executive summary

The law treats the product's three layers very differently:

1. **The copy of the video, with its music.** This is the exposure. It is a protected
   audiovisual work plus a sound recording and a composition. We host it and re-stream it
   (looped and slowed) to anyone with the link, for the *same purpose* as the original:
   watching the dance. After *Warhol v. Goldsmith* (2023), sharing the original's purpose
   weighs against fair use, and ads would weigh further against it.
2. **The derived 3D motion and counts.** This is the strongest part, legally. The purpose is new
   (instruction), no pixels or audio are kept, and most trend routines are not protectable
   choreography. The exception is *Hanagami v. Epic Games* (9th Cir. 2023). There, a claim over
   a two-second routine posted to YouTube and turned into a 3D animation survived dismissal.
   That is our pipeline almost exactly. Epic settled in 2024.
3. **Fetching from TikTok or YouTube.** This is a breach of contract, not a copyright issue
   (`../research/link-ingestion.md` §3).

**Top risks (likelihood × impact):**

| Rank | (a) Invite beta, friends | (b) Public launch, unlisted-by-link | (c) Public library / categories |
|---|---|---|---|
| 1 | Platform IP-blocks the fetcher (likely, low) | **A label or creator sends a DMCA notice, and with no designated agent there is no safe harbour** (likely, medium to high) | **Curation takes us outside §512(c)**: we become the publisher of copies we chose (likely, high) |
| 2 | A dancer finds their lesson (low, medium). The removal button covers it | Platform ToS enforcement against the server fetcher (likely, medium) | A registered-choreography claim over a featured routine (medium, high) |
| 3 | Nothing else material | A minor in a clip becomes findable, and link-derived IDs let people delete others' lessons (medium, medium) | Minors listed publicly, and right-of-publicity claims once ads arrive (medium, high) |

**The most consequential design change is embed-first for links** (§3): play the original in the
platform's own player and store only our 3D and counts. Under the Ninth Circuit's server test an
embed is not our display (*Hunley v. Instagram*, 2023). It does not cure the fetch itself.

## 2. Copyright (details in `rights-and-privacy.md` §3)

- **Choreography.** 17 U.S.C. §102(a)(4) protects "choreographic works". Circular 52 excludes
  social dances, simple routines and short step sequences, which covers most trend dances. It
  does not cover registered routines by working choreographers, and *Hanagami* holds that a
  short excerpt of one can still infringe. A 3D replay of such a routine is a plausible
  derivative work (§106(2)).
- **The video and the music.** These are protected without any doubt. "Publicly posted" is a
  licence to the platform, not to us. Music rightsholders are the likeliest to notice.
- **Fair use (§107).** *Google v. Oracle* (2021) favours copying that serves a new purpose,
  which fits the 3D. *Warhol* disfavours use for the same purpose, which fits the hosted copy.
  The copy also takes the whole clip and substitutes for views of the original (factors three
  and four). Fair use is a defence for the 3D, not a plan for the copy.

## 3. Platform terms and embed-first

**The terms.** YouTube's Terms (effective 15 Dec 2023) forbid access "using any automated means
(such as robots, botnets or scrapers)" and expressly allow showing videos "through the
embeddable YouTube player". Its API Developer Policies (updated 2026-09-14) forbid you to
"download, import, backup, cache, or store copies of YouTube audiovisual content". TikTok's Terms
(updated 15 Jul 2026, §3.4) forbid you to "scrape, crawl, export or otherwise extract any data or
content … using any automated system or software" without written approval.

| | Hosted copy (today) | Embed-first |
|---|---|---|
| Who displays or performs the video and music | Us, from R2 | The platform, under its licences |
| Creator's views and attribution | Bypassed | Preserved. Deleted or private originals vanish from lessons automatically |
| Playback-side ToS | Breached | Official player |
| The fetch for the GPU pass | Breach | **Still a breach**, but the copy can be transient |

**What breaks technically.** The YouTube IFrame API has `seekTo`, `getCurrentTime` and
`setPlaybackRate` (0.25–2×), so loops, speed and 3D sync all work, driven by polling. You cannot
overlay the player or modify its audio. Beats come from the transient copy, which is fine
because the output is timings, not audio. TikTok's embed player exposes `play`, `pause`,
`seekTo`, `mute`, `onCurrentTime` and `loop`, but **no playback rate**. Slow practice would
therefore slow only the 3D, with the video muted or hidden. That is a real cost, and possibly
an acceptable one, because the 3D is the teacher. Uploads have nothing to embed, so they keep
today's hosted model. The cleanest fetch alternative is the platform's own download button
feeding the upload path (`../research/link-ingestion.md` §6).

## 4. Safe harbours

- **DMCA §512(c)** requires a registered, posted agent ($6, renewed every 3 years, 37 C.F.R.
  §201.38), expeditious removal, no actual or red-flag knowledge, no "financial benefit directly
  attributable" to infringement we control, and a repeat-infringer policy (§512(i)). Removal is already fast. The gaps: no agent, no contact email (`/privacy` says there is none
  yet), no terms, and no subscriber to terminate (creator tokens from the identity doc would fix
  that). §512(c) covers material stored "at the direction of a user". Files **we** fetched are on
  weaker footing, and items **we select** for a library may fall outside the harbour entirely
  (*Mavrix v. LiveJournal*, 9th Cir. 2017, curation by moderators).
- **EU DSA.** Every hosting service, whatever its size, needs notice-and-action. Art. 16 says
  "mechanisms … to allow any individual or entity to notify", processed "in a timely, diligent,
  non-arbitrary and objective manner". It also needs statements of reasons (Art. 17) and points
  of contact (Arts. 11–12). A non-EU provider "offering services in the Union" needs an EU legal
  representative (Art. 13). The micro/small exemption in Art. 19 covers only the *online
  platform* duties, which a public library would trigger.
- **UK Online Safety Act 2023.** A lesson one user creates and others open looks like a
  user-to-user service. Ofcom expects a written illegal-content risk assessment within 3 months,
  plus a children's access assessment. Small low-risk services owe less, but still have to
  write the assessment down.

## 5. Privacy, people and minors

- **Biometrics** (see `rights-and-privacy.md` §4–5). Public listing changes nothing: GDPR Art. 9
  requires a "purpose of uniquely identifying", and BIPA, CUBI and Washington omit body
  geometry. What *would* change it is any feature that finds or matches a person ("more from
  this dancer", face-based dedupe). Never build one.
- **Right of publicity.** A free learning use is comfortable. A featured library, ads beside a
  likeness, or use in marketing all move toward "commercial purpose".
- **Minors in clips.** TikTok's minimum age is 13, and trend dancers are often 13–17. COPPA
  covers data collected *from* child users, so a pasted clip of a teen does not engage it. The
  exposure is harm and reputation: a minor's body made findable. **Do not add automated age
  estimation**, which would create the biometric processing this analysis otherwise avoids.
  Instead, add an "under 18" removal reason, keep flagged lessons out of any library, and use
  only adult, permissioned dancers in marketing.
- **"Unlisted" is weaker than it looks.** Link lessons derive `clip_id` from the source URL
  (D11), so anyone who knows the TikTok URL can find or delete the lesson. Lesson pages send
  no `noindex`; only `/admin` does. *(Since fixed: [README](README.md) tracker item 3.)*

## 6. Recommended changes by stage

**(a) Beta, now:**
1. Add `noindex` / `X-Robots-Tag` on `/lesson/*` and `/job/*`, plus a `robots.txt`.
2. Show "Original by @creator on TikTok/YouTube", with a link, on every link lesson.
3. Put a contact email on `/privacy` and in the footer.
4. Add an "under 18" removal reason.

**(b) Before public launch:**
1. Register the DMCA agent ($6), post it, and calendar the renewal.
2. Publish lawyer-reviewed Terms: the user's representation, covering both "fetch" and "host";
   the licence to us; the repeat-infringer policy; the counter-notice process.
3. Adopt creator tokens, so the repeat-infringer policy has a subject, and make deletion of link
   lessons require one (or randomise their IDs).
4. Go **embed-first** for links. Delete the fetched MP4 after processing, and store only the 3D,
   the MotionResult and the beats.
5. Add per-host fetch rate limits.
6. Set up a DSA point of contact and decide on an EU representative. Write a one-page Ofcom risk
   assessment.
7. Keep lessons unlisted by default.

**(c) Before a public library:**
1. Use permissioned inventory only. A creator opts in and verifies (a code in their bio or a
   comment). Show a "Made with permission" badge, keep attribution and the link back, and allow
   removal at any time. Get a written licence for registered choreography.
2. Add a publication gate: "everyone in this is 18+ and agreed" (`rights-and-privacy.md` §7a).
3. List only embedded originals, never hosted copies.
4. Offer a revenue share, or at least traffic back to the creator. It makes permission easy to
   ask for.

**Revenue.** Ads or sponsorship make the use commercial (*Warhol*, factor one), can be a
"financial benefit directly attributable" (§512(c)(1)(B)), and make publicity claims viable.
YouTube's API Policies also forbid ads "on any page … that contains YouTube API Data unless
other data … not obtained from YouTube … offers enough independent value", and forbid ads
"placed on or within … the YouTube player". Keep ads off lesson pages until (c) is done, and
never run child-directed creative (a COPPA factor).

## 7. Questions a real lawyer must confirm

1. Is a transient server-side fetch for processing defensible under each platform's terms, or
   is written approval needed?
2. Does §512(c) cover videos *we* fetched at a user's request? How much curation forfeits it?
3. Are Terms and a repeat-infringer policy enforceable with only creator tokens and no accounts?
4. After *Hanagami*, is a 3D replay of a registered routine a derivative work, and is learning
   a fair use?
5. Does the 3D satisfy YouTube's "independent value" test for ads?
6. Do we need an EU Art. 13 representative and an Ofcom risk assessment at beta scale?
7. How should the creator opt-in licence be worded: minors, revenue share, revocation?
8. The open items in `rights-and-privacy.md` §8: the SAM licence, the DPIA, and the licence grant.

## 8. Sources

- 17 U.S.C. §§102, 106, 107, 512 — https://www.law.cornell.edu/uscode/text/17/512
- Copyright Office, Circular 52 (rev. 10/2022) — https://www.copyright.gov/circs/circ52.pdf ; DMCA Directory FAQ ($6, 3 years) — https://www.copyright.gov/dmca-directory/faq.html
- *Hanagami v. Epic Games*, No. 22-55890 (9th Cir. 2023) — https://law.justia.com/cases/federal/appellate-courts/ca9/22-55890/22-55890-2023-11-01.html ; settlement — https://www.billboard.com/business/legal/fortnite-dance-choreographer-ends-epic-games-copyright-lawsuit-1235607331/
- *Andy Warhol Found. v. Goldsmith*, 598 U.S. 508 (2023) — https://www.supremecourt.gov/opinions/22pdf/21-869_87ad.pdf
- *Google v. Oracle*, 593 U.S. 1 (2021) — https://www.supremecourt.gov/opinions/20pdf/18-956_d18f.pdf
- *Hunley v. Instagram*, 73 F.4th 1060 (9th Cir. 2023) — https://cdn.ca9.uscourts.gov/datastore/opinions/2023/07/17/22-15293.pdf
- *Mavrix v. LiveJournal*, 873 F.3d 1045 (9th Cir. 2017) — cited from memory, verify
- YouTube Terms, effective 2023-12-15 — https://www.youtube.com/static?template=terms
- YouTube API Developer Policies, updated 2026-09-14 — https://developers.google.com/youtube/terms/developer-policies
- TikTok Terms (US), updated 2026-07-15 — https://www.tiktok.com/legal/page/us/terms-of-service/en ; Embed Player — https://developers.tiktok.com/doc/embed-player
- EU DSA 2022/2065 Arts. 13, 16, 19 — https://www.eu-digital-services-act.com/Digital_Services_Act_Article_16.html
- Ofcom, illegal content duties — https://www.ofcom.org.uk/online-safety/illegal-and-harmful-content/illegal-content-duties-under-the-online-safety-act
