# System legal review, September 2026: every moving part, as built

> **This is research, not legal advice.** The author is not a lawyer and neither is the builder.
> It builds on [`rights-and-privacy.md`](rights-and-privacy.md) (R&P),
> [`legal-public-learning.md`](legal-public-learning.md) (LPL) and
> [`../research/link-ingestion.md`](../research/link-ingestion.md). Those documents analyse the
> *design*. This one checks the *code on `main` at `f6457aa` (2026-09-25)* against them and the
> law, and flags where they have drifted apart. Sources were read on 2026-09-25. §6 lists what a
> real lawyer has to confirm, and §7 lists what I could not verify.

## 1. Executive summary

**What changed since the earlier docs.** Four things in the code change the legal picture, and
the first two make a public statement inaccurate today:

1. **The 3D body is now the dancer's body shape.** R&P §2 says the rendered body is a stock
   character "not the dancer's body", and tracker item 6 is marked done on that basis. Commit
   `8f4ae48` changed this. `modal_app.py` export now bakes each dancer's median 45-dimension MHR
   shape vector into the GLB rest mesh (`_character_with_shape`), and stores the vector in
   `{clip_id}.export-manifest.json`. The vector is no longer in the served JSON, but the GLB every
   browser downloads carries the fitted geometry. The shape basis is linear, so the vector can
   be recovered from the mesh. This is the artifact R&P §4d and §6.7 said would reopen the
   biometric analysis if it were kept long-term.
2. **The rate-limit hash did not rotate daily, although `/privacy` said it did.** It used a
   fixed key, so past days' hashes could in principle be linked by us. **Fixed 2026-09-25**: it
   now uses the same random daily salt as analytics, deleted after the day.
3. **The public repo listed live lesson links.** The eval labels file named real lesson ids, and a
   lesson id is its link. **Fixed 2026-09-25**: ids removed from the file; labels are keyed by a
   short clip name. Older commits still contain them, and those lessons expire under the normal
   6-month rule (or can be removed).
4. **File upload is open to anyone today.** Only link ingestion is invite-gated (tracker item 9,
   "partial"). So on the upload path the beta is already a public hosting service: strangers can
   store video with us. That brings the DMCA agent, the CSAM reporting duty and the TAKE IT DOWN
   Act forward from "before public launch" to now.

**Top risks, likelihood × severity.**

| Rank | Invite beta (now, uploads open) | Public launch (links open to strangers) | Library / monetisation |
|---|---|---|---|
| 1 | **Rightsholder notice with no designated DMCA agent**, because uploads are already open. Likely: low to medium. Severity: medium. The fix costs $6. | **Hosted copy of the clip and its music, fetched by us** (copyright plus platform ToS). No §512 agent, weak §512(c) footing for copies we fetched, and possible §1201 exposure for YouTube (*Yout v. RIAA*, on appeal). Likely: medium to high. Severity: high | **Curation takes us out of §512(c)**, plus music licensing for anything we select or promote. Likely: high. Severity: high |
| 2 | **Stale privacy statements** (the IP-hash rotation; the body shape; lesson ids kept after removal). Likely: certain. Severity: low to medium (FTC Act §5 and state UDAP deception claims turn on exactly this) | **Fetching at scale** against TikTok and YouTube terms. Likely: likely. Severity: medium (blocked, account or IP bans, cease-and-desist) | **Registered choreography** in featured lessons (*Hanagami*). Likely: medium. Severity: high |
| 3 | **Public repo lists live lesson links**. Likely: medium. Severity: low to medium | **Biometric reframing of the fitted body mesh** (CCPA/CPRA, Colorado, GDPR ordinary processing; BIPA weak). Likely: low. Severity: medium to high | **Right of publicity and minors** once a likeness is promoted or ads appear. Likely: medium. Severity: high |
| 4 | Apparent CSAM or intimate imagery uploaded. Likely: low. Severity: very high. The instant-delete removal path conflicts with the 18 U.S.C. §2258A preservation duty | EU DSA / UK OSA paperwork missing. Likely: medium if EU/UK use grows. Severity: low to medium | Promotional use of trending audio (TikTok Commercial Music Library rules). Likely: high if marketing starts. Severity: medium |

**The five cheapest high-value actions:**
1. Register the DMCA agent now, not at launch.
2. Fix the `/privacy` IP-hash sentence, or make the code match it.
3. Say on `/privacy` that the 3D body carries the dancer's estimated proportions.
4. Replace the `job_id`s in `evaluation/labels/count_one.json` with opaque labels.
5. Write down a one-paragraph CSAM/NCII procedure: preserve, report, then delete.

None of these needs a lawyer. Embed-first for links (LPL §3) is still the single largest risk
reduction for public launch.

## 2. The system, as built

Read from the code rather than from the design docs:

- **Web:** Next.js on a Cloudflare Worker (`apps/web/wrangler.jsonc`, Workers observability logs
  on). `/api/*` is proxied to Modal with an origin key and `cf-connecting-ip`
  (`app/api/[...path]/route.ts`). Fonts come from Google Fonts and Fontshare, loaded by the browser
  (`app/layout.tsx`). Sentry browser SDK: errors only, `sendDefaultPii: false`, scrubbed
  (`instrumentation-client.ts`, `lib/scrub.ts`).
- **API and GPU:** Modal (`modal_app.py`). The web function is pinned to `region="us"` because
  TikTok refused EU and India containers (measured 2026-09-24). Volumes: `stepwise-uploads`
  (source mp4), `stepwise-results` (MotionResult, GLB, beats, detections, job status/meta with
  credit, fingerprints index, tombstones, owner labels), `stepwise-eval` (evaluation clips).
- **Delivery:** Cloudflare R2 (`storage.py`), private bucket, 6-hour presigned GETs. GLB and
  MotionResult keys are versioned by content hash, and old versions are pruned. There is no CDN
  edge copy yet.
- **Database:** Neon Postgres. `jobs`, `events` (analytics, dispatch and removal rows, `day_hash`,
  lesson/job id), `analytics_salts`, `event_daily`. Also `users`, `creator_tokens`, `sessions`,
  `lessons`, `clips` and `assets` tables from `001_init.sql`, not populated by any live path I
  found.
- **Third parties receiving data:** PostHog US (server-side forward: allowlisted props, lesson id,
  day-hash hex, `$ip: null`, geoip off, no person profiles). Sentry (backend errors plus **10% of
  web requests traced**; browser errors). Cloudflare. Modal. Neon. Google Fonts and Fontshare
  (the visitor's IP, straight from the browser).
- **Retention:** `retention.py`. 180 days since last open, swept daily. Removal writes the
  tombstone first, then deletes Volume files, every R2 object under the clip's prefixes, the
  fingerprint entry and the Postgres job rows. Analytics rows: 13 months, then daily roll-ups.
  **Not deleted by a removal:** `events` rows (they carry the lesson/job id, and removal rows
  carry the requester's IP hash and relationship), the PostHog copy, the tombstone (kept forever,
  including the requester's free text), the eval labels in git, and the `stepwise-eval` Volume.

## 3. Moving parts → issue → mitigation → gap → action

Stage: **B** = beta now, **P** = before public launch, **L** = before library or monetisation.

| # | Moving part | Legal issue | Current mitigation in code | Gap | Recommended action | Stage |
|---|---|---|---|---|---|---|
| 1 | **Link fetch** (`ingest.py`, yt-dlp, logged out, no cookies, host allowlist, 60 s cap) | TikTok Terms and YouTube Terms forbid automated access and downloading (contract). YouTube's signature cipher may be a §1201 "technological measure" (*Yout v. RIAA*, D. Conn. 2022, appeal argued in the 2d Cir. Feb 2024, undecided as of 2026-09-25), and §1201 has no fair-use defence. Logged-out fetching of public pages is on better contract footing after *Meta v. Bright Data* (N.D. Cal. 2024), but that case was about data, not a copyrighted video | Invite gate (`invite_code_ok`), closed by default. Per-IP limits (`ratelimit.check` before download). No credentials ever | Shared-secret gate; no per-host limit; YouTube §1201 risk not analysed anywhere in the repo | Beta: keep links invite-only. Consider **TikTok-only links** until counsel answers the §1201 question, or route YouTube through "download it yourself, then upload". Public: embed-first, a transient copy, per-host limits (LPL §6(b)) | B / P |
| 2 | **Region pin `region="us"`** | Choosing a region because the platform refuses others is not a §1201 circumvention (no TPM is defeated). It is evidence of deliberately working around a platform access decision, which weakens a "we are an ordinary visitor" posture under the ToS | Documented in code | None legally material at beta scale | Never add proxies or residential IP rotation to beat blocks (`ingest.py` already rules out credentials). Treat a TikTok block as the answer (link-ingestion §6) | B |
| 3 | **Stored source mp4** (uploads Volume and R2 `video/…`) | Reproduction, distribution and public performance of the audiovisual work, the sound recording and the composition. "Posted publicly" licenses TikTok, not us | 180-day TTL; instant removal for everyone; `noindex`; credit line; unlisted | No DMCA agent; no Terms; for links, *we* made the copy, which weakens "stored at the direction of a user" | Register the agent **now** (uploads are open). Public: embed-first for links, and delete the fetched mp4 after processing (tracker 14) | B / P |
| 4 | **Credits** (`ingest.credit`: @handle, choreographer @handles and track/artist from the caption; the caption itself is not stored) | Helps: CMI under 17 U.S.C. §1202. Stripping the TikTok watermark and handle and showing nothing could be alleged as removing CMI. The credit line restores it. It also sends traffic back and builds goodwill (LPL). Hurts (mildly): a named choreographer may flag a registered routine, but general awareness is not "red-flag" knowledge of infringement (*Viacom v. YouTube*, 2d Cir. 2012; *UMG v. Shelter Capital*, 9th Cir. 2013). It is also personal data (a handle), and it ties a named person to a fitted body mesh (row 7) | Credits stored in job-meta, deleted on removal; `/privacy` discloses them | None material | Keep credits. Do not add "more from this creator" or anything that aggregates by handle (LPL §5). A credit is not a licence and must never be worded as permission | B |
| 5 | **Uploads** (`POST /clips`, not gated) | The uploader rarely owns the audio. Third-party dancers, minors. §512(c) is available only with a designated agent and a repeat-infringer policy | Rights line with no checkbox (R&P §7). Removal by anyone. Per-IP limits | No agent, no Terms, no repeat-infringer policy, and **no way to identify a repeat infringer** (the IP hash is day-scoped by design) | Agent now. *Cox v. Sony* (U.S. Mar. 2026) narrowed contributory liability to intent (inducement or a service tailored to infringement), which helps a general-purpose tool, but it leaves §512(i) untouched. Before public launch, Terms with a repeat-infringer policy keyed to creator tokens (the table exists, nothing writes it). Say plainly that without accounts, termination means blocking a token or hash | B / P |
| 6 | **Illegal-content edge cases** (uploads) | 18 U.S.C. §2258A: a provider with actual knowledge of apparent CSAM must report to NCMEC's CyberTipline, and the REPORT Act (2024) requires the content to be preserved for 1 year. The TAKE IT DOWN Act (2025) requires covered platforms to remove reported non-consensual intimate imagery within 48 hours, with a process in place by 19 May 2026 | The removal path deletes at once. The "under 18" reason exists | Instant deletion **destroys the evidence §2258A requires us to preserve**. There is no written procedure. Whether stepwise is a TAKE IT DOWN "covered platform" (one that primarily hosts user-generated content) is unclear | Write a one-page runbook in `docs/legal/`: on apparent CSAM, do **not** use the removal button. Disable the lesson, preserve it, report to NCMEC, then delete. Add "intimate image shared without consent" handling to the removal inbox with a 48-hour target. Ask counsel about covered-platform status | B |
| 7 | **3D body: GLB with the fitted shape, joint rotations, 2D detections, hand/foot crop rects** | *BIPA / CUBI:* body geometry is not on the closed lists. Hand and face geometry are, but no template is persisted (R&P §4). *CCPA/CPRA:* "biometric information" covers characteristics "used or … intended to be used … to establish individual identity", and gait is named. That is sensitive only when processed "for the purpose of uniquely identifying". Thresholds are not met today. *Colorado* HB24-1130 applies to **any** controller regardless of the CPA's volume thresholds, but defines biometric identifiers as data that "can be processed for the purpose of uniquely identifying" someone. *MHMDA* also hinges on identification. *BIPA:* the 2024 single-violation amendment is retroactive (*Clay v. Union Pacific*, 7th Cir. Apr. 2026). *Texas TRAIGA* (from 1 Jan 2026) exempts non-identifying uses. *GDPR:* Art. 9 only for "the purpose of uniquely identifying", so this is ordinary personal data. **New:** the mesh now encodes the individual's proportions, which makes the "capable of identifying" reading (*Colombo*-style courts, the Texas AG under CUBI) harder to dismiss than for a stock body | `expr_params` and `pred_vertices` not persisted. The vector is not in the served JSON. No matching or identification feature. Deleted with the lesson | **R&P §2 and tracker 6 are stale**: the proportions ship inside every GLB. `/privacy` says "a 3D body for each dancer" without saying it is shaped like them | Update `/privacy` ("shaped to each dancer's estimated proportions"). Record in R&P that the shape bake happened, and that R&P §6.7's trigger ("retaining shape_params long-term") has partly fired. Decide consciously: keep the bake (product value) and accept documenting it, or bake a *coarsened* shape (for example the first few components, or height only) | B (copy) / P (decision) |
| 8 | **Minors in clips** | COPPA applies to data collected *from* children by child-directed services, or with actual knowledge. The 2025 amended Rule adds biometric identifiers (including gait patterns) to "personal information", with compliance from 22 April 2026. A 12-year-old uploading their own dance with actual knowledge on our side would engage it | No accounts, no age collection, no child-directed content, no ads. "Under 18" removal reason. No age estimation (tracker 20) | None for beta. Actual knowledge could arise from an "under 18" removal or an email | Keep not collecting age. When an "under 18" or under-13 request arrives, delete (row 6 aside) and do not keep derived data. Never market to children | B / L |
| 9 | **Audio playback** (the hosted mp4 plays with its sound: looped, slowed, and synced to the click) | Public performance of the composition (§106(4)) and a digital audio transmission of the sound recording (§106(6)). On-demand, looped playback is *interactive*, so there is no §114 statutory licence: labels license directly. Slowing is still a performance and reproduction. Instruction is a better fair-use purpose than entertainment, but after *Warhol* the whole song played for its expressive use is weak. The closest precedent is the music publishers' 2019 suit against Peloton: songs streamed inside instructional video without sync licences, settled in 2020 | Only per-lesson unlisted links; `noindex`; TTL; removal | No licence path exists at this scale. §512 is the only shield | Beta: accept, with removal and an agent. Public: **embed-first moves playback to the platform's licensed player**, which is the only realistic fix. For uploads, keep hosted playback under §512 | B / P |
| 10 | **Beat detection, count grid, owner count-1** (`beats.json`, `proposed_counts`, `{clip}.count-one-labels.json`) | Tempo and beat times are facts, not expression (*Feist*), and not personal data on their own. They are derived from a copy we may not have had a right to make, but facts do not inherit that | Deleted with the lesson (prefix sweep) | None | None | — |
| 11 | **Metronome** (`lib/metronome.ts`) | A synthesised click on our own grid. No third-party audio | n/a | None | None | — |
| 12 | **Share clip / export with audio** (DESIGN §7g, not built) | A burned-in original audio track is a new reproduction and a synchronisation of music with picture: a sync licence we cannot get. It is posted by the learner, but *we* produce the file | Not built | — | Build it **silent only**. Let the learner add a sound inside TikTok, where TikTok's licences apply. Watermark "made with stepwise" only on content the learner made | L |
| 13 | **Promotion** (stepwise's own social accounts, marketing site) | TikTok business accounts are limited to the Commercial Music Library, and TikTok's music terms bar commercial use of licensed sounds. A dancer's likeness in marketing is a right-of-publicity use (commercial purpose). Posting other people's clips as marketing loses §512 entirely | `evaluation/README.md` rights tiers; demo-public slot empty | No written rule for marketing | Marketing uses only `permission-granted` clips with written releases (adults), CML or royalty-free audio, and never an ingested lesson | L (and any time before posting) |
| 14 | **Choreography** | Circular 52 excludes social dances and simple routines. *Hanagami* (9th Cir. 2023): short excerpts of registered choreography can infringe, and 3D reproduction is the fact pattern. Settled Feb 2024. *Heyer v. Roblox* (2025, settled) was the first TikTok-born dance turned into an avatar emote. The Office refused Ribeiro's "Carlton" as a simple routine (2019) | Unlisted; removal | None at beta | Library: written licence for registered or known-choreographer routines (tracker 21) | L |
| 15 | **Right of publicity** (the dancer's video plus a body mesh with their proportions) | A free instructional use is generally outside "commercial purpose". The new digital-replica statutes (Tennessee ELVIS Act 2024; California AB 1836 and AB 2602; Illinois P.A. 103-836; NY) target realistic replicas of voice or likeness. A textured-less MHR mannequin with someone's proportions is unlikely to be "readily identifiable", but it is closer than a stock body | Free, no ads | Not reviewed for marketing or paid use | Review before any paid tier or marketing (tracker 25) | L |
| 16 | **Removal path** (`POST /jobs/{id}/removal`, `/privacy` form) | GDPR Art. 17 and Art. 21. DSA Art. 16 notice-and-action wants a statement of reasons (Art. 17) to the *uploader*, which is impossible without contact details | Works for anyone, instantly, rate-limited per IP hash | No record of *what* was claimed for rights notices (no DMCA fields). The uploader is never told | Keep it. Add a DMCA-shaped option (§512(c)(3) fields) routed to email so formal notices are complete. The tombstone free text is kept forever: cap it (for example 3 years) and say so | B / P |
| 17 | **Link-derived clip ids** (`_clip_id_for_source`) | Anyone who knows the TikTok URL can find or delete the lesson | Documented trade | Stays until creator tokens exist | Tracker 13 (unchanged) | P |
| 18 | **Analytics** (Neon `events`, `day_hash` with a daily salt deleted, PostHog US forward) | GDPR: a day-scoped keyed hash is still pseudonymous personal data on the day, and lesson ids plus referrer host are personal data in context. ePrivacy: no storage on the device, so no cookie consent is needed. US: no sale or sharing, and processor terms needed | No cookies, no SDK, GPC/DNT honoured, allowlist, `$ip: null`, geoip off, no person profiles, 13-month roll-up. DEPLOYMENT §3.2 says to set "Discard client IP data" | Removal does not purge the lesson's `events` rows or PostHog events. `/privacy` does not say so. PostHog US was chosen, although `analytics-options.md` recommended EU for the upgrade path | Add one `/privacy` sentence: "usage notes about a removed lesson are kept until they expire". Accept the PostHog DPA (it covers SCCs). Confirm "Discard client IP data" is actually on | B |
| 19 | **Rate-limit and removal hashes** (`ratelimit._ip_hash`) | Pseudonymous; **fixed 2026-09-25**: now keyed by the deleted-daily analytics salt. The removal row links (requester IP hash, clip, relationship) | Not written as raw IP | **`/privacy` says the key changes daily; it does not.** It falls back to `DATABASE_URL` as the secret | Either fix the copy ("a keyed hash of your IP address and the date; we keep the key secret"), or, better, use a daily random salt as analytics does. Confirm `STEPWISE_IP_SALT` is set in production | B |
| 20 | **Sentry** (backend and browser) | Processor. Error content can include user data | Whole-event scrubbing (URLs, handles, emails, ids), no locals, `send_default_pii=False`, browser errors only | Backend **traces 10% of web requests**, which `/privacy` does not mention (it lists "error reports"). Data region and IP storage not recorded | Mention performance traces, or set the backend sample rate to 0. Sentry's region is fixed at org creation (US by default; EU is `de.sentry.io`), so record which one it is. Turn on "Prevent storing of IP addresses". Accept the Sentry DPA | B |
| 21 | **Owner tools** (`/owner`, shared key, count-1 override, `/owner/queue` shows recent lessons with credit and video) | The operator viewing user content to label it is ordinary processing. Labels are timings, not personal data | Key-gated, 404 when unset, lockout, `noindex`. Labels are swept with the lesson | None material | Keep the owner key out of shared devices. The labels file is fine | — |
| 22 | **Eval labels in the public repo** (`evaluation/labels/count_one.json`) | Listed lesson links in a public repo. **Fixed 2026-09-25** (ids removed); older commits remain | `_about` says "No video is stored" (true) | Six live `job_id`s are public. Git history keeps them | Replace `job_id` with an opaque label id (for example `HMAC(owner_secret, job_id)`), or keep only clips from `clips.yaml`. If any of the six lessons were made by someone other than the builder, remove them or ask. History rewriting is optional: once the ids point to deleted lessons they are inert | B |
| 23 | **Evaluation clips** (`stepwise-eval` Volume, `evaluation/fetch.py`, `clips.yaml` with `rights: untested`) | The same ToS and copyright posture as link fetch, kept **indefinitely** and outside the TTL sweep. Internal testing only | README rights tiers: `untested` is never public | No retention rule | Add a rule: delete eval clips no longer in `clips.yaml`, and never use an `untested` clip publicly (already the rule) | P |
| 24 | **Hosting / processors**: Modal (US), Cloudflare (Workers, R2), Neon, PostHog US, Sentry, Google Fonts, Fontshare | GDPR Art. 28 needs a DPA with each processor. Chapter V transfers (all US): DPF certification or SCCs. Google Fonts loaded from the browser sends the visitor's IP to Google (*LG München I*, 3 O 17493/20, 2022, €100 damages) | `/privacy` names Cloudflare, Modal, fonts, PostHog, Sentry | Neon (now Databricks) is not named on `/privacy`. R2 location hints are best effort; only a jurisdiction restriction is guaranteed, and it cannot be added later. No DPA inventory. Fonts are hotlinked | Keep a one-table processor register (in this folder) with DPA link, region and transfer mechanism. Name Neon on `/privacy`. Self-host fonts before public launch (`next/font` or local files) | B (register) / P (fonts) |
| 25 | **EU DSA / UK OSA / GDPR Art. 27** | DSA Arts. 11, 12 and 16 apply to all hosting services. Art. 13 requires a legal representative for non-EU providers "offering services in the Union". UK OSA: a user-to-user service with UK links needs a written illegal-content risk assessment and a children's access assessment | Removal path; contact email | No DSA contact statement, no assessments | Public: tracker 16. Beta: nothing, unless EU/UK testers are invited deliberately | P |

## 4. The dance video and audio questions the owner asked

**Can we host and play other people's TikTok videos, with their audio, for learning?**
Not with a clean legal basis, only with a defensible *posture*. The clip, the sound recording and
the composition are all protected, and nobody licensed them to us: TikTok's licence runs to
TikTok. Serving them looped and slowed from R2 is reproduction, distribution and (for the music)
an interactive digital performance. No statutory licence covers that, and after *Warhol*,
"it's for learning" does not reliably make it fair use when we play the whole thing for the
same purpose as the original. What the product actually relies on is:
- small scale;
- unlisted and `noindex`;
- instant removal;
- a credit and link back;
- expiry after six months unopened.

With a registered DMCA agent, §512(c) would add a real shield *for user uploads*. For copies
**we fetched**, §512(c) is arguable but weaker, and the fetch itself breaches both platforms'
terms. For YouTube specifically, the signature decryption yt-dlp performs may be circumvention
under §1201 (*Yout v. RIAA*, 2d Cir. appeal pending). §1201 does not care about fair use. That makes YouTube links the
single most legally exposed feature per unit of value. **Verdict:** fine for an invite-only beta
with the B-stage fixes above. Not fine as the public model.

**What about uploads?** They are better, because the person uploading chose to put the file here.
That is the paradigm case for §512(c): "storage at the direction of a user". It still needs:
- the agent, registered and posted, from the day strangers can upload, which is today;
- Terms with a user representation and a repeat-infringer policy;
- expeditious removal, which we already have.

The music is still unlicensed, but the liability sits primarily with the uploader, and we are
shielded if we comply. Dancers in the clip are a privacy and publicity matter, handled by the
removal path and the absence of any identification feature.

**What changes if we go embed-first for links?**
- Playback of the video *and the audio* moves to the platform's official player, under its
  licences and with the creator's view counts. In the Ninth Circuit (the server test: *Perfect
  10 v. Amazon*; *Hunley v. Instagram*, 2023), embedding is not our display.
- Deleted or private originals disappear from the lesson on their own.
- We keep only derived facts: 3D motion, body shape (row 7), beats and counts. Those are strong
  transformative-use material, plus facts.

What it does **not** fix:
- **The fetch** for the GPU pass is still a ToS breach, and still a possible §1201 act for
  YouTube. It shrinks to a transient copy deleted after processing. The cleaner fetch is the
  platform's own download button feeding the upload path.
- **Features:** the TikTok embed has no playback-rate control, so slow practice slows only the
  3D, with the video muted or hidden. On YouTube, `setPlaybackRate` works.
- **The click:** it still works, because it runs on the player's reported time.
- **Uploads:** they have nothing to embed and stay hosted under §512.

Embed-first is the most important structural change before public launch.

**Does creator credit help or hurt?** Net help. It restores the CMI that a watermark-free
download strips, sends traffic back, and matches platform norms. It is not a licence. It
slightly increases how easily a body mesh can be tied to a named person, so do not build
anything that aggregates by handle.

## 5. What to change in the other docs (for the builder; not done here)

- R&P §2 table and findings 2 and 3: the GLB is now shape-fitted (`8f4ae48`), and the vector sits
  in `export-manifest.json` on the results Volume.
- Tracker item 6: "partial". The JSON no longer carries the vector, but the GLB does.
- The `/privacy` copy in `apps/web/lib/copy.ts`: rows 7, 18, 19, 20 and 24 above. Each is a
  one-sentence change. The copy file says every sentence is checked against code, and these five
  fail that check.

## 6. Things to ask a real lawyer

1. Is yt-dlp's YouTube signature handling "circumvention" under §1201, while *Yout v. RIAA* is pending in the 2d Cir.?
   Should YouTube links be turned off even for the beta?
2. Does §512(c) cover a copy the server fetched at a user's request, and does a no-account
   service with day-scoped hashes have a "reasonably implemented" repeat-infringer policy?
3. Is baking a person's estimated body proportions into a mesh served to anyone with the link
   "biometric information" under CCPA/CPRA, Colorado HB24-1130 or MHMDA, given no identification
   purpose? Does coarsening it change the answer?
4. Is stepwise a TAKE IT DOWN Act "covered platform", and what is the minimum CSAM
   preserve-and-report procedure for a solo operator?
5. For EU/UK users at beta scale: DSA Art. 13 representative, GDPR Art. 27 representative, an
   Ofcom risk assessment. Which are really required now?
6. The music: is instructional, looped, slowed playback of an uploaded clip's audio defensible,
   or should uploads be muted by default with an opt-in?


## 7. What I could not verify

1. **Cited from memory, not opened in this pass:**
   - the TAKE IT DOWN Act (Pub. L. 119-12, May 2025; platform process due 19 May 2026);
   - the REPORT Act (2024; preservation extended to 1 year);
   - *Meta Platforms v. Bright Data* (N.D. Cal. Jan. 2024);
   - *LG München I* 3 O 17493/20 (2022);
   - *Viacom v. YouTube* (2d Cir. 2012) and *UMG v. Shelter Capital* (9th Cir. 2013);
   - *Perfect 10 v. Amazon* (9th Cir. 2007).

   Verify before relying on any of them.
2. **Circular 52's exact wording.** The PDF did not parse in this pass. R&P §3a quotes it from an
   earlier reading.
3. **Other gaps from the research pass:**
   - Modal's data location and DPF status;
   - the final dispositions of the 2 Milly and "Orange Shirt Kid" suits;
   - the full DSA article text (read through secondary sources);
   - the absence of a playback-rate control in TikTok's embed player (confirmed only through a
     secondary summary, as in LPL §3).
4. **Production settings I cannot see from the repo:**
   - PostHog's "Discard client IP data";
   - Sentry's region and IP storage;
   - Neon's AWS region.

   Check each one in its dashboard.
5. **Whose clips the six lessons in `count_one.json` are.** If they are all the builder's own test
   uploads, row 22 drops to hygiene.

## 8. Sources

**Platform terms**
- TikTok Terms of Service (US), updated 2026-07-15 — https://www.tiktok.com/legal/page/us/terms-of-service/en
- TikTok Commercial Music Library user terms — https://www.tiktok.com/legal/page/global/commercial-music-library-user-terms/en
- TikTok Embed Player — https://developers.tiktok.com/docs/en/embed-player
- YouTube Terms of Service, 2023-12-15 — https://www.youtube.com/static?template=terms
- YouTube API Services Developer Policies, updated 2026-09-14 — https://developers.google.com/youtube/terms/developer-policies
- YouTube IFrame API (`setPlaybackRate`) — https://developers.google.com/youtube/iframe_api_reference

**Copyright**
- 17 U.S.C. §§106, 107, 512, 1201, 1202 — https://www.law.cornell.edu/uscode/text/17/512
- Copyright Office, Circular 52 — https://www.copyright.gov/circs/circ52.pdf
- Copyright Office, DMCA Designated Agent Directory FAQ ($6, 3-year renewal) — https://www.copyright.gov/dmca-directory/faq.html
- *Hanagami v. Epic Games*, No. 22-55890 (9th Cir. 2023) — https://law.justia.com/cases/federal/appellate-courts/ca9/22-55890/22-55890-2023-11-01.html
- *Hanagami* settlement, Feb 2024 — https://esportslegal.news/2024/02/16/revolution-over-epic-games-settles-copyright-dispute-with-hanagami-over-fortnite-dance-moves/
- *Heyer v. Roblox* (2025) — https://www.betches.com/article/entertainment/apple-dance-creator-suing-roblox-choreography-tiktok-charlixcx-308164-20250417
- *Brantley v. Epic Games* (2020) — https://www.courtlistener.com/opinion/9737156/brantley-v-epic-games-inc/
- Ribeiro / "Carlton" — https://techcrunch.com/2019/03/08/fresh-prince-actor-dismisses-his-fortnite-dance-lawsuit/
- *Cox Communications v. Sony Music*, No. 24-171 (U.S. Mar. 25, 2026) — https://www.supremecourt.gov/opinions/25pdf/24-171_bq7d.pdf
- Kirkland summary of *Cox v. Sony* — https://www.kirkland.com/publications/kirkland-alert/2026/04/supreme-court-narrows-scope-of-secondary-copyright-liability-in-cox-v-sony
- *Yout v. RIAA*, 2d Cir. No. 22-2760 (pending) — https://torrentfreak.com/yout-com-hopes-supreme-courts-cox-ruling-helps-its-case-riaa-disagrees/
- *Andy Warhol Found. v. Goldsmith*, 598 U.S. 508 (2023) — https://www.supremecourt.gov/opinions/22pdf/21-869_87ad.pdf
- NMPA v. Peloton settlement — https://www.billboard.com/pro/peloton-nmpa-music-publishers-legal-costs-settlement-49-million/
- *Hunley v. Instagram*, 73 F.4th 1060 (9th Cir. 2023) — https://cdn.ca9.uscourts.gov/datastore/opinions/2023/07/17/22-15293.pdf

**Privacy, biometrics and minors**
- Cal. Civ. Code §1798.140 — https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=CIV&sectionNum=1798.140
- CPPA regulations (effective 2026-01-01) — https://www.skadden.com/insights/publications/2025/10/california-finalizes-cppa-regulations
- *Clay v. Union Pacific* (7th Cir. 2026), BIPA amendment retroactive — https://www.shb.com/intelligence/client-alerts/bipa/2026-hutchinson-wolfe-seventh-circuit-clay
- Colorado HB24-1130 — https://www.venable.com/insights/publications/2024/06/colorado-amends-state-privacy-law-to-include
- Texas TRAIGA — https://www.insideprivacy.com/artificial-intelligence/texas-enacts-ai-consumer-protection-law/
- Texas AG / Meta CUBI settlement — https://www.texasattorneygeneral.gov/news/releases/attorney-general-ken-paxton-secures-14-billion-settlement-meta-over-its-unauthorized-capture
- RCW 19.375.010 — https://app.leg.wa.gov/rcw/default.aspx?cite=19.375.010
- EDPB Guidelines 3/2019 (video devices) — https://www.edpb.europa.eu/sites/default/files/files/file1/edpb_guidelines_201903_video_devices_en_0.pdf
- COPPA Rule amendments, 90 FR (2025-04-22) — https://www.federalregister.gov/documents/2025/04/22/2025-05904/childrens-online-privacy-protection-rule
- Texas SB 2420 status — https://www.scotusblog.com/2026/07/supreme-court-allows-texas-to-enforce-law-requiring-age-verification-and-parental-consent-on-app/
- 18 U.S.C. §2258A — https://www.law.cornell.edu/uscode/text/18/2258A

**Right of publicity and digital replicas**
- Illinois P.A. 103-0836 — https://www.ilga.gov/ftp/legislation/103/HB/10300HB4875.htm
- California AB 2602 / AB 1836 — https://www.skadden.com/insights/publications/2024/09/california-enacts-host-of-ai-related-bills
- New York 2025 laws — https://www.debevoisedatablog.com/2025/12/17/new-york-enacts-landmark-ai-right-of-publicity-laws/
- Tennessee ELVIS Act — https://www.globalpolicywatch.com/2024/09/california-passes-digital-replica-legislation-as-congress-considers-federal-approach/

**EU and UK**
- DSA Art. 19 scope — https://www.cms-digitallaws.com/en/dsa/article-19/
- Ofcom illegal-harms statement — https://www.ofcom.org.uk/online-safety/illegal-and-harmful-content/statement-protecting-people-from-illegal-harms-online
- GDPR Art. 27 — https://gdpr-info.eu/art-27-gdpr/

**Processors**
- PostHog DPA — https://posthog.com/dpa
- Sentry DPA — https://sentry.io/legal/dpa/
- Modal DPA — https://modal.com/legal/dpa
- Cloudflare DPA — https://www.cloudflare.com/cloudflare-customer-dpa/
- Cloudflare R2 data location — https://developers.cloudflare.com/r2/reference/data-location/
- Neon DPA — https://neon.com/dpa
- Neon regions — https://neon.com/docs/introduction/regions

**In this repo** (`main` at `f6457aa`)
- Services: `services/motion-api/{api.py,ingest.py,retention.py,storage.py,analytics.py,ratelimit.py,owner.py,observability.py,jobstore.py,modal_app.py,motion_result.py}`, `services/motion-api/migrations/`
- Web: `apps/web/lib/copy.ts` (`privacy`), `apps/web/instrumentation-client.ts`, `apps/web/app/layout.tsx`, `apps/web/app/api/[...path]/route.ts`, `apps/web/wrangler.jsonc`
- Evaluation: `evaluation/labels/count_one.json`, `evaluation/clips.yaml`, `evaluation/README.md`
- Docs: `docs/DEPLOYMENT.md` §3.2, §5.3
