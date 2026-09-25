# Runbook: reports of child sexual abuse material or non-consensual intimate images

**Not legal advice.** This is the owner's working procedure, written from the statutes named below
and `system-review-2026-09.md` row 6. Confirm it with a lawyer before public launch (tracker item 30,
and lawyer question 4 in the system review). Where this page and a lawyer disagree, the lawyer wins.

## 1. What triggers it

Any of these:

- **The public removal dialog.** "Report or remove this video" has a box: *This shows sexual
  content involving a minor, or intimate images shared without consent* (`illegal_sexual_content`).
- **The owner.** `/owner` has **Remove** on each row; pick **Quarantine**
  (`POST /owner/jobs/{job_id}/remove`, `mode: "quarantine"`).
- **An email** to the help address, or anything else that tells you a lesson may be one of these.
  Open `/owner`, find the lesson and use **Remove > Quarantine**. If it is not in the queue (the
  queue shows the 50 most recent), call the endpoint with the owner key:

  ```
  curl -X POST "$API/owner/jobs/<job_id>/remove" -H "x-stepwise-owner-key: $KEY" \
       -H 'content-type: application/json' -d '{"mode":"quarantine","note":"email report, <date>"}'
  ```

**Do not use Delete, or the public dialog's other boxes, for this content.** They destroy the files at
once, and the files are evidence we may be required to keep.

The other boxes ("I am in this video", "under 18", "I own the rights", "Something else") and the
owner's **Delete** still delete everything at once. "Under 18" on its own means a minor appears in the
video, which is a privacy removal, not an abuse report.

## 2. What the system has already done when you get the alert

The alert is a Sentry event at level **fatal** titled *abuse report: lesson taken down and
quarantined; follow docs/legal/abuse-report-runbook.md*, tagged with `clip_id` and `relationship`
(also printed in the Modal web logs as `[quarantine] ABUSE REPORT`). By then:

1. The lesson is down for everyone. Status, result, assets and video all answer **410**, and the
   lesson page shows the ordinary "removed" state. Nothing says why.
2. Every file of the lesson (the uploaded video, each dancer's GLB, the MotionResult, the npz, beats,
   detections, job status and job meta, and every R2 object) has been **copied** to the Modal Volume
   `stepwise-quarantine`, checked by sha256, and only then deleted from the public places. R2 keys are
   gone, so any presigned URL already handed out stops working.
3. A manifest (`/<clip_id>/manifest.json` on that Volume) records the clip and job ids, the time, the
   reporter's relationship box and anything they typed, each file's origin, size and sha256, and a
   `preserve_until` date one year out.
4. The video's fingerprint moved from the dedupe index to a blocklist. The same video, a re-encode of
   it, or the same link is refused with the same 410 on upload.
5. Nothing will delete it: the 6-month sweeper skips removed lessons, and any later removal request,
   worker sweep or `audit_removed.py --fix` on this lesson moves late files into quarantine instead of
   deleting them.

If Sentry also shows an error tagged `stage: quarantine`, the copy failed and the files were **left
where they were** (still 410, nothing deleted). The daily sweep retries; you can retry now with
`python3 audit_removed.py --fix` or by calling the owner endpoint again.

If the alert says *reported after it was already deleted*, someone chose that box on a lesson that
had already been removed another way. There are no files. Go to step 4 and report what you know
(the ids and times).

## 3. What you do: apparent child sexual abuse material (CSAM)

A provider that obtains actual knowledge of apparent CSAM on its service must report it to NCMEC's
CyberTipline "as soon as reasonably possible" (18 U.S.C. §2258A). Treat the alert as the start of
that clock. The REPORT Act (2024) requires the reported content to be preserved for **one year**.

1. **Look as little as possible.** You need enough to judge whether the report is plausibly apparent
   CSAM; you do not need to watch it, and never watch it more than once. Do not screenshot, forward,
   copy it anywhere except the export below, or describe it to anyone except NCMEC or law enforcement.
   **Possessing or distributing it outside this reporting process is itself a crime.** If you are
   unsure whether it is CSAM, report it anyway: NCMEC decides, not us.
2. **If a child may be in immediate danger, call 911 (or local police) first.**
3. **Export the evidence** for the report, onto an encrypted disk you control:

   ```
   cd services/motion-api
   python3 quarantine.py list
   python3 quarantine.py export <clip_id> --out /Volumes/<encrypted>/cybertip
   ```

   The export re-checks every sha256 and logs the export time in the manifest.
4. **Report to the CyberTipline:** <https://report.cybertip.org>. If NCMEC offers an electronic service
   provider reporting account, register for one (it gives a report number and a way to upload files).
   What they ask for, and what we have:
   - **Who is reporting:** stepwise, the owner's name and a contact address.
   - **The incident:** type (child sexual abuse material), the date and time it was uploaded
     (`quarantined_at`, and the job-meta file's time) and when we learned of it (the alert's time).
   - **The content:** upload the exported source video (`uploads/<clip_id>.mp4`). The GLBs and the
     MotionResult are 3D data derived from it; mention they exist and upload them if asked.
   - **Where it was:** the lesson URL (`https://<site>/lesson/<job_id>`). For a pasted link, the
     original post's URL and the poster's @handle are in `results/job_<clip_id>.job-meta.json`
     (`credit`). **This is the most useful lead we have** and it points at another platform, so say
     so plainly.
   - **Who uploaded it:** we have no accounts, no names, no emails and no stored IP addresses (only a
     keyed hash whose key is deleted daily, which cannot be reversed, even by us). Say that.
   - Anything the reporter typed (`reason` in the manifest), if it helps.

   Keep the CyberTipline report number and its date (step 8): the preservation year counts from it.
5. **Delete your local export** once NCMEC has it. The quarantine Volume keeps the preserved copy.
6. **Preserve for one year from the date of the report**, not from the quarantine date. The script's
   `preserve_until` counts from quarantine, so if you reported later, wait the extra days before
   purging. If law enforcement asks you to keep it longer (they can), keep it and do not purge.
7. **Do not tip off the uploader.** Do not contact them, do not tell them why the lesson is gone, do
   not change the removed page for this lesson. The site already shows the same "removed" state as any
   other removal, and a re-upload gets the same generic 410. If they email asking why, reply only that
   the lesson was removed after a report.
8. **Record what you did**: date, report number, who you talked to, in a private note (not in this
   public repo, not in Sentry).

## 4. What you do: intimate images of an adult shared without consent (NCII)

The TAKE IT DOWN Act (2025) requires a covered platform to remove a reported non-consensual intimate
image **within 48 hours** of a valid request, and to make reasonable efforts to remove identical
copies; the platform process was due by 19 May 2026. Whether stepwise is a "covered platform" is an
open lawyer question, so act as if it is.

1. **Removal is already done** if the report came through the dialog or you used Quarantine. The
   lesson came down at once, and the blocklist refuses identical copies and re-encodes. The 48 hours
   matter for reports that arrive by **email**: use `/owner` **Remove > Quarantine** the same day.
2. A valid TAKE IT DOWN request has a signature, enough to identify the image, a good-faith statement
   that it is non-consensual, and contact details. If a request is incomplete, remove it anyway and
   ask for what is missing; do not make the person wait.
3. **Check whether anyone in it could be a minor.** If there is any doubt, it is section 3, not this one.
4. **Tell the requester** it has been removed. Do not contact the uploader.
5. **Law enforcement:** if the person asks for it, or there is extortion ("sextortion") or a threat,
   point them to local police and the FBI (<https://tips.fbi.gov>), and keep the quarantined copy
   for them. Otherwise nothing requires a report.
6. **Purging.** For adults there is no §2258A preservation duty, and the person will usually want it
   gone. Once a lawyer confirms nothing needs keeping (no police case, no litigation hold):

   ```
   python3 quarantine.py purge <clip_id> --i-understand-this-destroys-evidence \
       --adult-ncii-lawyer-cleared-early-purge
   ```

   Never use the early flag for anything that involves, or might involve, a minor.

## 5. The owner's two removal modes

`/owner` shows **Remove** on every row. It opens a dialog with two choices and an optional note:

| Mode | Use it for | What happens |
|---|---|---|
| **Delete** | Off-topic or not a dance, spam, test uploads, anything else that simply should not be here | The same instant deletion as the public dialog's ordinary boxes (`retention.delete_clip`). Tombstone relationship `owner`, your note as the reason. Cannot be undone. |
| **Quarantine** | Apparent CSAM (section 3), or intimate images shared without consent (section 4) | Taken down the same way, then preserved and alerted exactly as in section 2. Tombstone relationship `owner`, your note in the manifest. |

When unsure between the two, choose **Quarantine**: a quarantined lesson can still be purged later,
but a deleted one cannot be brought back for a report. Never quarantine content just to keep it; the
quarantine exists only for material we may have to report. A later Delete on a quarantined lesson
does not undo the quarantine.

Nothing quarantined is ever shown on `/owner` or any other page; the queue only lists live lessons.

## 6. The script

`services/motion-api/quarantine.py`, run on the owner's machine with a Modal token (the same setup as
`audit_removed.py`). It prints ids, dates and counts, never file contents.

| Command | Does |
|---|---|
| `python3 quarantine.py list` | Every quarantined lesson: when, until when to preserve it, the box picked, file count, how many times exported |
| `python3 quarantine.py export <clip_id> --out <dir>` | Writes the files and manifest to `<dir>/<clip_id>/`, re-checking each sha256; logs the export |
| `python3 quarantine.py purge <clip_id> --i-understand-this-destroys-evidence` | Deletes that lesson's quarantined files and manifest. Refuses before `preserve_until` |

Purge keeps two things: the tombstone (the link keeps answering "removed") and the blocklist entry
(hashes only, not the video), so the same video cannot come back.

**When to purge:** CSAM, one year after the CyberTipline report (section 3, step 6), and only if law
enforcement has not asked for longer. Adult NCII, when a lawyer says nothing needs keeping (section 4).

Who can reach the quarantine: anyone with access to the Modal workspace. Keep that list to the owner.

## 7. Open questions for the lawyer

- Is stepwise a TAKE IT DOWN Act covered platform, and is the dialog plus email a sufficient process?
- Does the preservation duty also cover the derived 3D data (GLBs, MotionResult), or only the video?
- Is quarantine-at-report (before a person has looked) the right trigger, given that anyone with a
  lesson link can pick the box?
- Should NCMEC's hash-sharing programmes be used to check uploads before they are processed?

## Sources

- 18 U.S.C. §2258A (reporting requirements of providers), as amended by the REPORT Act (2024):
  CyberTipline reports and 1-year preservation.
- TAKE IT DOWN Act, Pub. L. 119-12 (May 2025): 48-hour removal of non-consensual intimate images.
- `system-review-2026-09.md` row 6 and lawyer question 4.
- Code: `services/motion-api/retention.py` (`quarantine_clip`, `is_blocked`), `api.py`
  (`remove_lesson`, `owner_remove`), `quarantine.py`; tests in `test_retention.py` and `test_owner.py`.
