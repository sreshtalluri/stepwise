# Legal

Research and action items on rights, privacy and platform terms. None of it is legal advice; the
open lawyer questions are listed in each doc. New legal research goes in this folder.

- [`rights-and-privacy.md`](rights-and-privacy.md): what an uploaded dance clip creates (copyright,
  publicity, biometric statutes, GDPR) and the mitigations, ranked.
- [`legal-public-learning.md`](legal-public-learning.md): what changes when lessons become public
  learning from links (DMCA, platform terms, minors), and what to do at beta, public launch and
  library stages.
- Related, in `docs/research/`: [`link-ingestion.md`](../research/link-ingestion.md), the platform
  terms analysis for fetching TikTok and YouTube links.

## Tracker

Every action item from both docs. **R&P** = `rights-and-privacy.md`, **LPL** =
`legal-public-learning.md`. Status is one of done, partial, todo, or needs owner decision.

| # | Item | Source | Stage | Status | Where |
|---|---|---|---|---|---|
| 1 | Removal path on every lesson: deletes at once, for everyone, and takes more than copyright claims | R&P §6.1 | beta | done | `services/motion-api/api.py` `remove_lesson`; `apps/web/components/RemoveLessonDialog.tsx`; `/privacy` (`RemoveByLink`) |
| 2 | "Under 18" removal reason | LPL §5, §6(a)4 | beta | done | `api.py` `RemovalRequest.relationship` (`under_18`); `apps/web/lib/copy.ts` `removal.relationships`; `test_retention.py::test_removal_boxes_match_the_dialog` |
| 3 | `noindex` on `/lesson/*` and `/job/*`, plus `robots.txt` | LPL §5, §6(a)1 | beta | done | `apps/web/app/lesson/layout.tsx`, `apps/web/app/job/layout.tsx` (meta); `apps/web/next.config.mjs` `headers()` (`X-Robots-Tag`); `apps/web/app/robots.ts` |
| 4 | "Original by @creator on TikTok/YouTube", linked, on every link lesson | LPL §6(a)2 | beta | done | `services/motion-api/ingest.py` `credit`, stored in job-meta, served by `GET /jobs/{job_id}/source`; `apps/web/components/lesson/pieces.tsx` `CreditLine` (Desktop bar, phone stage) |
| 5 | Contact email on `/privacy` and in the footer | LPL §6(a)3; R&P §6.1 ("a monitored address") | beta | needs owner decision | TODO: owner picks an address, then add it to `apps/web/lib/copy.ts` `privacy` and the footer in `apps/web/app/layout.tsx` |
| 6 | Stop persisting `expr_params` and `pred_vertices`; stop serving `shape_params.vector` | R&P §6.2 | beta | done | `vendor/fast-sam-3d-body/tools/process_clip.py` `UNREAD_PER_FRAME_KEYS`; `motion-result.schema.json` (`vector` optional, not sent) |
| 7 | Delete the clip and reconstruction with the lesson, plus a retention ceiling | R&P §6.3 | beta | done | `services/motion-api/retention.py` (`delete_clip`, `TTL_DAYS = 180` since last opened) |
| 8 | Upload copy with no blocking checkbox | R&P §7 | beta | done | `apps/web/lib/copy.ts` (upload `rights` line) |
| 9 | Stay invite-only through the pilot | R&P §6.6 | beta | partial | Links are behind the invite gate (`ingest.invite_code_ok`); file upload is open |
| 10 | Register the DMCA agent ($6), post it, calendar the 3-year renewal | R&P §6.4; LPL §6(b)1 | before public launch | todo | |
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

**A note on item 3.** `robots.txt` disallows only `/admin` and `/api/`. Lesson and job pages are
left crawlable so crawlers can see their `noindex`; blocking them in `robots.txt` would hide the
`noindex` and still let a linked URL appear in search as a bare link.
