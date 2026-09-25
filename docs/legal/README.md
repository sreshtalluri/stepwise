# Legal

Research and action items on rights, privacy and platform terms. None of it is legal advice; the
open lawyer questions are listed in each doc. New legal research goes in this folder.

- [`rights-and-privacy.md`](rights-and-privacy.md): what an uploaded dance clip creates (copyright,
  publicity, biometric statutes, GDPR) and the mitigations, ranked.
- [`legal-public-learning.md`](legal-public-learning.md): what changes when lessons become public
  learning from links (DMCA, platform terms, minors), and what to do at beta, public launch and
  library stages.
- [`system-review-2026-09.md`](system-review-2026-09.md): the code on `main` (2026-09-25) checked
  against the law and the two docs above, one moving part at a time, including where `/privacy`
  no longer matches the code.
- [`abuse-report-runbook.md`](abuse-report-runbook.md): what the owner does when a lesson is
  reported as child sexual abuse material or intimate images shared without consent (preserve,
  report to NCMEC, 48-hour removal), and how to use `quarantine.py`.
- Related, in `docs/research/`: [`link-ingestion.md`](../research/link-ingestion.md), the platform
  terms analysis for fetching TikTok and YouTube links.

## Tracker

Every action item from the docs. **R&P** = `rights-and-privacy.md`, **LPL** =
`legal-public-learning.md`, **SR** = `system-review-2026-09.md` (§3 row numbers). Status is one of done, partial, todo, or needs owner decision.

| # | Item | Source | Stage | Status | Where |
|---|---|---|---|---|---|
| 1 | Removal path on every lesson: deletes at once, for everyone, and takes more than copyright claims | R&P §6.1 | beta | done | `services/motion-api/api.py` `remove_lesson`; `apps/web/components/RemoveLessonDialog.tsx`; `/privacy` (`RemoveByLink`) |
| 2 | "Under 18" removal reason | LPL §5, §6(a)4 | beta | done | `api.py` `RemovalRequest.relationship` (`under_18`); `apps/web/lib/copy.ts` `removal.relationships`; `test_retention.py::test_removal_boxes_match_the_dialog` |
| 3 | `noindex` on `/lesson/*` and `/job/*`, plus `robots.txt` | LPL §5, §6(a)1 | beta | done | `apps/web/app/lesson/layout.tsx`, `apps/web/app/job/layout.tsx` (meta); `apps/web/next.config.mjs` `headers()` (`X-Robots-Tag`); `apps/web/app/robots.ts` |
| 4 | "Original by @creator on TikTok/YouTube", linked, on every link lesson | LPL §6(a)2 | beta | done | `services/motion-api/ingest.py` `credit`, stored in job-meta, served by `GET /jobs/{job_id}/source`; `apps/web/components/lesson/pieces.tsx` `CreditLine` (Desktop bar, phone stage) |
| 5 | Contact email on `/privacy` and in the footer | LPL §6(a)3; R&P §6.1 ("a monitored address") | beta | done (2026-09-24) | `stepwisedance.help@gmail.com`, forwards to the owner; `apps/web/lib/copy.ts` `privacy.contact` + removal section, footer in `apps/web/app/layout.tsx`. Move to a domain address once one exists |
| 6 | Stop persisting `expr_params` and `pred_vertices`; stop serving `shape_params.vector` | R&P §6.2; SR row 7 | beta | partial (2026-09-25: the vector is out of the JSON, but since `8f4ae48` each GLB is shaped to the dancer's estimated proportions, see item 28) | `vendor/fast-sam-3d-body/tools/process_clip.py` `UNREAD_PER_FRAME_KEYS`; `motion-result.schema.json` (`vector` optional, not sent) |
| 7 | Delete the clip and reconstruction with the lesson, plus a retention ceiling | R&P §6.3 | beta | done | `services/motion-api/retention.py` (`delete_clip`, `TTL_DAYS = 180` since last opened) |
| 8 | Upload copy with no blocking checkbox | R&P §7 | beta | done | `apps/web/lib/copy.ts` (upload `rights` line) |
| 9 | Stay invite-only through the pilot | R&P §6.6 | beta | partial | Links are behind the invite gate (`ingest.invite_code_ok`); file upload is open |
| 10 | Register the DMCA agent ($6), post it, calendar the 3-year renewal | R&P §6.4; LPL §6(b)1; SR rows 3, 5 | **beta** (moved 2026-09-25: file upload is open to anyone today) | todo | |
| 11 | Lawyer-reviewed Terms: user representation (fetch and host), licence to us, repeat-infringer policy, counter-notice | R&P §6.4, §6.5, §8.1; LPL §6(b)2 | before public launch | todo | |
| 12 | Privacy notice | R&P §6.5 | before public launch | partial | `/privacy` exists (`apps/web/app/privacy/page.tsx`); not lawyer-reviewed |
| 13 | Creator tokens; link-lesson deletion requires one (or randomise link-lesson IDs) | LPL §5, §6(b)3 | before public launch | todo | Link clip_ids are derived from the source URL today (`api.py` `_clip_id_for_source`) |
| 14 | Embed-first for links: delete the fetched MP4 after processing | LPL §6(b)4 | before public launch | todo | |
| 15 | Per-host fetch rate limits | LPL §6(b)5 | before public launch | todo | Per-IP limits exist (`ratelimit.py`); none per host |
| 16 | DSA point of contact, decide on an EU representative, one-page Ofcom risk assessment | LPL §6(b)6; R&P §8.2 | before public launch | todo | |
| 17 | Lessons unlisted by default | LPL §6(b)7 | before public launch | done | No public index; item 3 keeps them out of search |
| 18 | Lawyer questions: SAM licence compliance clause, DPIA / Art. 30 / Art. 27 | R&P §8.2–8.3; LPL §7 | before public launch | todo | |
| 19 | Keep ads off lesson pages; no child-directed creative | LPL §6 (Revenue) | before public launch | done | No ads anywhere |
| 20 | Never build a feature that finds or matches a person; no automated age estimation | LPL §5; R&P §6.7 | always | done | Nothing like it exists |
| 21 | Permissioned inventory only: creator opt-in and verification, "Made with permission" badge, written licence for registered choreography | LPL §6(c)1 | before library | todo | |
| 22 | Publication gate: "everyone in this is 18+ and agreed"; under-18-flagged lessons never listed | LPL §5, §6(c)2; R&P §7a | before library | todo | |
| 23 | List only embedded originals, never hosted copies | LPL §6(c)3 | before library | todo | |
| 24 | Revenue share, or at least traffic back to the creator | LPL §6(c)4 | before library | needs owner decision | Item 4 sends traffic back today |
| 25 | Right of publicity review before any paid tier or marketing use | R&P §8.4; LPL §5 | before library | todo | |
| 26 | `/privacy` says the rate-limit IP hash key "changes every day"; `ratelimit._ip_hash` used a fixed key; now uses the daily random analytics salt | SR row 19 | beta | done (2026-09-25) | `services/motion-api/ratelimit.py` `_ip_hash`; `apps/web/lib/copy.ts` `privacy` |
| 27 | `/privacy`: say that usage notes and removal rows about a removed lesson stay until they expire (Neon 13 months, PostHog its own period); mention backend performance traces (10%) or turn them off; name Neon | SR rows 18, 20, 24 | beta | done (2026-09-25) | `apps/web/lib/copy.ts` `privacy`; `observability.py` `traces_sample_rate` |
| 28 | Body shape baked into every GLB: say so on `/privacy`, update R&P §2, then decide whether to keep it or coarsen it | SR row 7; R&P §6.7 | beta (copy) / before public launch (decision) | needs owner decision | `modal_app.py` `_character_with_shape`; `export-manifest.json` `shape_params` |
| 29 | Remove live lesson `job_id`s from the public repo's eval labels (use opaque ids) | SR row 22 | beta | done (2026-09-25) | `evaluation/labels/count_one.json` |
| 30 | CSAM / intimate-image runbook: preserve and report to NCMEC (18 U.S.C. §2258A, 1-year preservation) instead of instant deletion; 48-hour NCII removal (TAKE IT DOWN Act) | SR row 6 | beta | partial | [`abuse-report-runbook.md`](abuse-report-runbook.md). Removal dialog box `illegal_sexual_content` and `/owner` Remove > Quarantine take the lesson down and move its bytes to the `stepwise-quarantine` Volume (`retention.quarantine_clip`, manifest + sha256, blocklist, Sentry fatal alert); every other reason still deletes at once. `services/motion-api/quarantine.py` lists, exports and purges. Open: lawyer review (covered-platform status, runbook), NCMEC ESP registration |
| 31 | Processor register: DPA, region and transfer mechanism for Modal, Cloudflare, Neon, PostHog and Sentry; confirm PostHog "Discard client IP data", the Sentry region and IP storage,  | SR rows 18, 20, 24 | beta | todo | |
| 32 | Self-host fonts (Google Fonts and Fontshare get the visitor's IP today) | SR row 24 | before public launch | todo | `apps/web/app/layout.tsx`, `global-error.tsx` |
| 33 | YouTube links and §1201 (*Yout v. RIAA* pending): ask counsel; consider TikTok-only links or YouTube via download-then-upload | SR row 1 | before public launch | needs owner decision | `ingest.ALLOWED_HOSTS` |
| 34 | A DMCA-shaped option in the removal flow (§512(c)(3) fields go to email); cap the tombstone free text's retention and say so | SR row 16 | before public launch | todo | `api.py` `RemovalRequest`; `retention.write_tombstone` |
| 35 | Retention rule for the `stepwise-eval` Volume (TikToks marked `rights: untested`, kept indefinitely) | SR row 23 | before public launch | todo | `evaluation/fetch.py`, `modal_app.py` `eval_clips` |
| 36 | Share clip: silent export only, with sound added inside TikTok; marketing uses only `permission-granted` clips and Commercial Music Library or royalty-free audio | SR rows 12, 13 | before library | todo | DESIGN §7g (not built) |

**A note on item 3.** `robots.txt` disallows only `/api/`. Lesson and job pages are
left crawlable so crawlers can see their `noindex`; blocking them in `robots.txt` would hide the
`noindex` and still let a linked URL appear in search as a bare link.
