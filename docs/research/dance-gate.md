# Dance gate: refusing non-dance videos before we keep them

Research on `research/dance-gate`, 2026-09-25. It adds no production code. The prototype and
measurement scripts are in `tools/research/dance_gate/`. No videos are committed, and neither are
lesson ids, because the repo is public and a job id is the lesson's link.

## 1. Summary

**The owner's requirement:** check every incoming video at the very start. If it isn't a dance,
refuse it before any byte is stored and before any GPU work is spent on it.

**Recommendation: a CPU gate we run ourselves, with no third party.** It makes two checks:

1. **Does it look like dance?** We run [CLIP ViT-B/32](https://huggingface.co/openai/clip-vit-base-patch32)
   zero-shot on 8 frames spread across the clip. The prompts are 6 dance prompts against 19 other
   prompts. We refuse when P(dance) < **0.4**.
2. **Does anything move?** We take the median frame-to-frame difference of 2 fps grey thumbnails over
   the first 16 s. We refuse when it is < **0.1**, which means a still photo or frozen frame over music.

Anything else passes. A borderline dance goes through, and the cost of letting one through is a
single $0.08 GPU run.

**Measured on 36 dances, 87 non-dance clips and 17 ambiguous clips:**

- **No real dance was refused** (0 of 36). That includes all 12 of our own clips.
- **76% of non-dance clips were refused** (66 of 87).
- It takes **1.0–1.7 s per clip on a warm 2-CPU Modal container**, about $0.0001 per clip.
- The first call on a cold container adds about 7 s of model load. That load overlaps the GPU cold
  start that the upload already triggers.
- Adding a pose check (RTMO-s: "is there a person" and "do they move") raises refusals to **84%**,
  still with 0 false refusals. It costs about **5 s more per clip** on Modal CPU, so it is v1.1 at the
  earliest.

**Rollout: shadow mode first.** For one to two weeks we log the scores (numbers only) and refuse
nothing. Then we set the enforced threshold below the lowest score any real lesson got. The margin
today is thin. The lowest-scoring real dance is at 0.536, and our own lowest is 0.548.

**Nudity and sexual content:** we log a [NudeNet](https://github.com/notAI-tech/NudeNet) score (MIT
licence, 0.07–0.2 s) at the same gate, in shadow mode. At a threshold of ≥ 0.7 it flagged none of the
140 clips, and 36 of those are dances. At ≥ 0.5 it flagged one real dance rehearsal. **We did not
measure recall**, because we deliberately collected no explicit test content. Enforcing it (refuse and
discard, never quarantine) needs a legal decision first. See §6.

**What else we tested:**

- A vision-language model we host ourselves (SmolVLM2-500M) is about as accurate as CLIP, at 10× the
  latency.
- A Kinetics action classifier and X-CLIP are worse at zero false refusals.
- Our own signals alone (pose, music, rhythm) are cheap but weak.
- A third-party VLM (Claude, Gemini) or a moderation service would put frames of identifiable people
  in front of a new processor. Nothing we measured needs one.

## 2. The test set

The fetch script is `tools/research/dance_gate/fetch.sh`. Labels come from looking at contact sheets,
not from search terms. `relabel.py` records 17 corrections, for example a fairground ride called
"Break Dancer" and a hula hoop found by searching "hula".

| Set | Count | What it contains |
|---|---|---|
| **Positives: ours** | 12 | Our 6 real lessons' source videos, the 4 eval clips from the `stepwise-eval` Volume (solo and group), and 2 lessons with the audio stripped (a muted dance must still pass). |
| **Positives: Wikimedia Commons** | 24 | Folk (4 countries), ballet (including a 1903 film), Bharatanatyam, breaking, contemporary, flamenco, Irish, salsa, tap, waltz, street, a dance-fitness class, and a line dance. Filming is from far away, crowded, low-light, or half-body. |
| **Negatives: Commons** | 83 | Talking heads and vlogs, lectures, cooking, basketball, running, yoga, workouts, gymnastics, karate, walking, pets, gameplay and screen recordings, singing, guitar, concerts, skateboarding, beach volleyball, traffic, nature, a parade. Hard cases: sign language, jump rope, shadow boxing, tai chi, juggling, hula hoop, a conductor, drummers, makeup tutorials, stretching, jumping jacks, and selfie videos. |
| **Negatives: derived from our lessons** | 4 | Three dancers' frames frozen for 12 s over the lesson's own music, a stand-in for "a person standing still with music". Also a lesson's 4.4 s walk-in, with no dance in it. |
| **Ambiguous** (not scored) | 17 | Zumba, cheerleading, aerobics, a fire-hoop act, a moshing crowd, a conga line, and documentaries with a little dance in them. The table reports how many of these each rule refuses. |

Commons clips are cut to at most 20 s at 360p. `manifest.json` records each clip's source page,
licence and author.

**Gaps.** Phone-filmed TikTok-style non-dance is the real hard case: lip-sync, "get ready with me",
someone talking to the camera in their room. It is covered only by the Commons talking-head and selfie
clips and by the synthetic frozen frames. No openly licensed pool of that content exists. Shadow mode
(§5) exists to close this gap on real traffic.

All thresholds were chosen on this same set, so the numbers above are optimistic. The rules have one
or two parameters each, and we picked round numbers with margin rather than fitting them.

## 3. What we measured

Timings are CPU with 2 threads, on an M4 laptop unless noted. "Refused at 0 false refusals" means
the threshold set at the lowest score any positive got. It is the best a method can do while
refusing no dancer on this set. "Precision" is the share of clips let through that are dances. It is
low only because this set is 70% negatives; real uploads are mostly dances.

| Option | What it is | AUC | Non-dance refused at 0 false refusals | Speed per clip | Licence | Privacy |
|---|---|---|---|---|---|---|
| **A. Our own signals** (pose, music, rhythm, as one hand-tuned score) | RTMO-s at 8 fps plus Beat This! beats and limb-speed autocorrelation | 0.87 | 37% | 8 s pose + 0.2 s audio for 20 s of video | Apache-2.0 (RTMO); Beat This! is already in use | Nothing leaves us |
| A-lite: "no person" or "the person never moves" only | RTMO-s, 32 frames (2 fps, first 16 s) | – | 43% (0 false refusals) | 1.6 s (M4); **5.3 s on Modal 2-CPU** | Apache-2.0 | Nothing leaves us |
| **B1. Kinetics-400 classifier** (torchvision MViT-v2-S, summed probability of its 17 dance classes) | 3 × 16-frame windows | 0.94 | 18% (a group folk dance scored 0.006) | 2.6 s | BSD-3 code; weights trained on Kinetics (YouTube). Note that VideoMAE's Kinetics checkpoint is CC BY-NC. | Nothing leaves us |
| **B2. X-CLIP B/32**, zero-shot video-text | 8 frames | 0.93 | 63% | 0.3 s | MIT | Nothing leaves us |
| **B3. CLIP ViT-B/32**, zero-shot, 8 frames averaged | image-text | 0.94 | **79%** | **0.3 s** (M4); **0.5 s on Modal** | MIT (see note below) | Nothing leaves us |
| **C1. SmolVLM2-500M-Video**, self-hosted | Asks "is a person dancing? yes/no" on 4 frames and reads P(yes) | 0.94 | **82%** | 2.5 s, and about 2 GB of RAM | Apache-2.0 | Nothing leaves us |
| C2. Claude (`claude-haiku-4-5`, `claude-sonnet-5`), Gemini | Hosted VLM on about 8 frames | **not measured**: no API key in the environment, and none was fetched | – | About 1–3 s of network time | Commercial API | **Frames of people go to a new processor.** Needs a /privacy disclosure and a DPA. Cost is about $0.002 per clip (Haiku 4.5) or $0.004 (Sonnet 5): roughly 1.7k input tokens at about w×h/750 tokens per image. |
| **Recommended: B3 + stillness** | CLIP < 0.4, or frame difference < 0.1 | – | **76% (0 false refusals, precision 0.63)** | 0.26 s (M4); **1.0–1.7 s warm on Modal 2-CPU** | MIT | Nothing leaves us |
| Recommended + A-lite (v1.1) | adds "no person" and "nobody moves" | – | **84% (0 false refusals, precision 0.72)** | 1.9 s (M4); about 6–7 s on Modal | as above | Nothing leaves us |

Findings behind the table:

- **Appearance models are fooled by a dancer who isn't moving.** CLIP gives the frozen-frame clips a
  dance probability of 0.83–0.99, and SmolVLM gives them 0.66–0.79. The stillness check catches all
  three because their frame difference is exactly 0.0. The lowest real dance scores 0.46: a group
  filmed from far away in a field. A pose-based "nobody moves" check catches them too, but costs 5 s.
- **Music can only ever add evidence; its absence is never a reason to refuse.** 23 of 36 dances have
  a regular beat track (Beat This! found at least 8 beats with inter-beat CV < 0.25). So do 12 of 87
  non-dance clips. The other 13 dances are silent, muted, or crowd noise. Music did not earn a place
  in the gate. Beat This! is fast (0.2 s median) if it is ever wanted.
- **Beat-locked limb rhythm is weak here too.** The median autocorrelation peak is 0.33 for dances and
  0.18 for non-dance, which is too much overlap to use. This matches §7 of
  `step-by-step-learning.md`: it separates dancing from walking on one lesson but not in general.
- **What still gets through** (at 0.4, no pose), 21 clips:
  - gymnastics, hula hoop, juggling, jump rope, karate, tai chi, yoga, stretching;
  - a workout in space;
  - sign language;
  - a singer, a guitar close-up, festival drummers, clapping hands;
  - a fairground ride;
  - the walk-in. These are rhythmic body activities that people rarely upload to a dance site, and
  each costs one GPU run. The lesson's own not-dancing trim handles walk-ins.
- **Ambiguous clips:** the gate refuses 7 of 17. They are:
  - both aerobics clips;
  - a documentary;
  - a moshing crowd;
  - a 1927 film's title cards;
  - a parade float;
  - a teacher explaining hand gestures to the camera.

  Zumba, cheerleading, the conga line and the fire-hoop act pass. Whether aerobics counts as a dance
  is a product decision, and the shadow logs will show how often it comes up.
- **CLIP licence note.** The weights are MIT-licensed, but OpenAI's model card calls deployed use "out
  of scope" pending the deployer's own evaluation. This document is that evaluation. OpenCLIP's
  LAION-trained ViT-B/32 (MIT) is a drop-in alternative. Re-run `run.sh` before switching.
- **Not tested:** InternVideo2 and ViCLIP. They are large and GPU-oriented, and CLIP already holds 0
  false refusals at 0.3 s.

**Reproduce.** Run `sh tools/research/dance_gate/fetch.sh` (it needs lesson ids in
`.data/jobs.txt`), then `sh run.sh` for the per-method table, then `sh run.sh gate` to run the
recommended gate end to end. `modal run modal_bench.py` measures the Modal CPU latency. Total Modal
spend for this research was a few cents: two ephemeral runs, with nothing deployed.

## 4. Where the gate runs

```
upload/link → temp file (already) → fingerprint + dedupe (already)
            → GATE  ← new: nothing has been written yet
            → _store_and_dispatch: rate-limit charge, job_created, uploads Volume, R2, index, GPU hand-off
```

- **Placement: first thing in `_store_and_dispatch`.** Both front doors already end there, after
  dedupe and before `_limited(charge_as=…)`, `_created`, `uploads_volume.batch_upload` and
  `_publish_video`. One call covers files and links. A dedupe hit skips the gate, which is correct
  because that video was already accepted once.
- **It runs as its own Modal function, `gate_clip`** (CPU, `cpu=2`, 2 GiB, `min_containers=0`). The
  web container stays out of it: it serves up to 100 concurrent inputs on a small CPU share, and it
  deliberately has no torch. The web container already has ffmpeg and numpy. It decodes what the gate
  needs itself, in memory:
  - 8 JPEG frames at 224 px (about 150 KB in total);
  - 32 grey 160×90 thumbnails (about 460 KB).

  It then calls `gate_clip.remote(...)` with those bytes. The video file never leaves the web
  container. The frames exist only as that call's input.
- **Model packaging.** Export CLIP's image tower to ONNX and pin it by sha256, as RTMO is today.
  Precompute the 25 prompt embeddings (25 × 512 floats) at build time. The runtime image is then
  `onnxruntime` plus `numpy` plus `pillow`, with no torch.
- **Failure policy: fail open.** On a timeout (about 15 s) or an error, log it and accept the clip.
  A gate outage must not become a site outage, and the requirement favours dancers.
- **Pre-warm.** `_prewarm_gpu` starts a GPU container before the request body is read, so it is
  already warming while the gate runs. A refused request ends without a job. The middleware already
  releases the container on that path (`put(token, {"cancel": True})`), and the container scales down
  after Modal's idle window, about $0.03. That is cheaper than the $0.08 run it replaces, and it keeps
  about 30 s of cold start off every real lesson. Moving the pre-warm after the gate would put that
  30 s back on every real lesson, so only do it if refusals become a large share of uploads.
- **Discarding the bytes.** On refusal, raise before any write. `upload_clip` and `ingest_clip_link`
  already `os.unlink(tmp_path)` in `finally`. For a pasted link, the URL is not stored either: the
  index entry and `source_key` are only written by `_store_and_dispatch`. Nothing is written to the
  uploads Volume, R2, the index, jobstore or `job_created`.
- **Rate limit.** A refusal is not charged as a dispatch. If someone loops non-dance uploads to burn
  pre-warms, count refusals with the existing `ratelimit.check` path. Don't build that until it
  happens.

## 5. What the user sees, analytics, and privacy

**The refusal.** It uses the existing `_refuse` shape: HTTP 422 with
`{"error": {"code", "message", "retryable": false}}`. The processing and failure screens already show
a non-retryable message verbatim, so the web app needs no change beyond copy.

- `not_a_dance` (CLIP, or stillness): "This doesn't look like a dance video, so we didn't keep it.
  Stepwise makes lessons from videos of someone dancing, with their whole body in view. If it is a
  dance, try a clip where the dancer is clearly visible, or email stepwisedance.help@gmail.com."
- `content_not_allowed` (NudeNet, only once enforcement is approved): "We can't make a lesson from
  this video." Keep it deliberately plain.

**There is no owner review queue for `not_a_dance`.** A queue would mean keeping the video, which is
exactly what the owner doesn't want. Users contest by email. The shadow-mode scores are what keep
false refusals near zero.

**Analytics.** Add `clip_refused` to `SERVER_EVENTS` with these props:

- `source`: file or link;
- `code`;
- `reason`: `looks_like_something_else`, `nothing_moves`, or `nudity`;
- `dance`: rounded to 0.05;
- `still`: rounded to 0.1;
- `nsfw`: rounded to 0.05;
- `seconds`.

No job id, because no job exists. During shadow mode, add the same three scores to `job_created`, so
the lowest score any accepted real lesson got is a SQL query. The event carries nothing from the video
itself.

**/privacy.** Add one item near "One lesson per video":

> "Before we keep a video, a program on our own servers looks at a few frames to check that someone
> is dancing in it (and that it isn't sexual content). If not, we refuse it and delete it straight
> away. We keep only a note that a clip was refused, why, and the check's scores. We keep no picture,
> file or link."

No new processor is involved, because Modal already processes every upload. If a hosted VLM or a
moderation service were ever added, it would need to be named on /privacy, and it would need a DPA
entry in the processor register (`legal/README.md` row 31). The CLIP and NudeNet outputs are
class scores, not identification, so the biometric analysis in `legal/rights-and-privacy.md` §4 is
unchanged. NudeNet's face classes are ignored.

## 6. Safety: nudity and sexual content

| Option | Measured false positives on our 140 clips | Speed | Cost | Privacy |
|---|---|---|---|---|
| **NudeNet 3.4** (detector, "exposed" classes, max over 8 frames) | ≥ 0.5: **2** (a real dance rehearsal at 0.50, rice cooking at 0.58). ≥ 0.7: **0** | 0.07 s (M4), 0.17 s (Modal) | free, MIT | stays with us |
| Falconsai `nsfw_image_detection` (ViT classifier) | ≥ 0.5: **3**, including a grizzly-bear selfie at 0.995 | 0.9 s | free, Apache-2.0 | stays with us |
| AWS Rekognition moderation, Google SafeSearch, Hive | not measured (list prices are roughly $1–1.5 per 1k images) | network | per image | **new processor: frames of people leave us.** Needs /privacy and a DPA. |

**Recall was not measured.** We did not collect explicit test content.

**Recommendation.**

1. Ship NudeNet in shadow mode with the dance gate.
2. After review, enforce **refuse and discard at ≥ 0.7 on at least 2 of the 8 frames**, using the
   `content_not_allowed` message.
3. **Do not quarantine flagged content.** Storing it for review is the one action that turns a
   classifier guess into us holding sexual material.

Two things to confirm with counsel before enforcing (neither is settled here):

- US providers' reporting duty (18 U.S.C. § 2258A) is triggered by actual knowledge of CSAM. A
  classifier score is not that. Refusing without storing keeps it that way.
- **A nudity model is not a CSAM detector.** Hash matching (PhotoDNA, Thorn Safer) is the industry
  tool. Cloudflare's CSAM Scanning Tool covers images served through its cache, not videos we
  process on Modal.

**Link to the abuse runbook.** `legal/abuse-report-runbook.md` is still in progress. The gate stops
content at the door. The runbook covers reports about lessons that already exist, and flagged uploads
never become lessons. The runbook should say this: "the upload gate refuses likely nudity and keeps
no copy; reports about published lessons follow this runbook".

## 7. Implementation plan

| Step | What | Effort |
|---|---|---|
| 1 | `services/motion-api/dance_gate.py`: frame extraction (ffmpeg, in memory), `decide()`, and a small `test_dance_gate.py` covering the decision rule and fail-open. The logic is `gate.py` minus torch. | 0.5 d |
| 2 | `gate_image` and the `gate_clip` Modal function: ONNX CLIP image tower plus precomputed prompt embeddings, and NudeNet ONNX. Pin both files' sha256 at build, as RTMO is. | 1 d |
| 3 | `api.py`: call the gate first in `_store_and_dispatch`. Controlled by `STEPWISE_DANCE_GATE=off\|shadow\|enforce` (default `shadow`), with a separate `STEPWISE_NSFW_GATE=off\|shadow\|enforce` (default `shadow`). The refusal codes go through `_refuse`. Timeout, then fail open. | 0.5 d |
| 4 | `analytics.py`: add `clip_refused` and the shadow scores on `job_created`. Write a query for "lowest score of an accepted real lesson". | 0.5 d |
| 5 | Copy: add the two messages to `copy.ts` and the /privacy item. Add a line to the runbook. | 0.25 d |
| 6 | Shadow for 1–2 weeks. Look at the lowest-scoring accepted lessons by hand. Set the enforced thresholds, then switch to `enforce`. NSFW enforcement waits for §6's legal check. | 1–2 weeks elapsed, about 0.5 d of work |
| later | Add the A-lite pose check (+8 points of refusals, about +5 s) only if shadow logs show clips with no person, or frozen people, getting through. Add a hosted VLM as a second opinion for the 0.3–0.5 band only if that band is large, and only with the /privacy and DPA changes above. | – |

**About 3 days of work, plus the shadow period.**
