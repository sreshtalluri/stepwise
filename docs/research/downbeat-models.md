# Downbeat models: upgrade now or later? (2026-09-24)

**Short answer: upgrade now, and use Beat This! (`final0`) for the beats only.**
Keep our kick heuristic to choose which beat of the bar is count 1, and keep the
alternates. Beat This! is MIT (code and weights), runs on CPU in under a second
per clip, and needs no GPU.

"Count 1 is bad" turned out to be two separate problems:

1. **The beat grid itself is wrong.** On the bhangra lesson every count we show
   falls about 300 ms off the beat, halfway between beats. On solo-07 the grid
   drifts up to 237 ms off. Every model we tested fixes both. This is the
   part a model solves outright.
2. **Which beat of the bar is "1".** The models disagree with each other on 3
   of 8 clips, and none of them is right on every labelled clip. On the 4
   labelled clips, Beat This!'s beats with our kick rule for phase got all 4
   right. No model on its own did that except `small0`, and that looks like luck.

## Clips and labels

- **Labelled** (the owner's count 1, from the labelling page on 2026-09-23):
  solo-01 1.292, solo-02 1.905, group-synced-01 1.120, solo-07 1.030. Only
  count 1 is labelled. There are no labelled beats.
- **Unlabelled.** Four real lessons, with audio from `/api/jobs/<id>/video` on
  the live site: bhangra `job_5716…`, `job_345b…`, `job_b822…`, `job_a106…`.
- **Metric.** A method passes if its count 1 lands within ±70 ms of the label.
  For the models, count 1 is the first downbeat at or after the first beat
  heard, the same rule production uses. With no labelled beats, the beat
  F-measure below (±70 ms) is scored against Beat This! `final0`. That makes it
  a measure of agreement, not accuracy.
- **How it was run.** Locally on an M4 CPU, in a throwaway uv venv. The audio is
  mono WAV extracted with the pinned imageio-ffmpeg, the same decoder
  production uses.

## Results: labelled clips (count 1 within 70 ms)

| method | solo-01 | solo-02 | group-synced-01 | solo-07 | score |
|---|---|---|---|---|---|
| current (librosa grid + kick) | 1.292 ✓ | 1.905 ✓ | 1.120 ✓ | 1.358 ✗ (+328 ms, drift) | 3/4 |
| Beat This! final0 | 1.28 ✓ | 1.88 ✓ | 1.10 ✓ | 0.04 ✗ (half a bar early) | 3/4 |
| Beat This! final0 + DBN | 1.28 ✓ | 1.88 ✓ | 1.10 ✓ | 0.04 ✗ | 3/4 |
| Beat This! small0 | 1.26 ✓ | 1.88 ✓ | 1.12 ✓ | 1.00 ✓ | 4/4 |
| madmom RNN+DBN (non-commercial) | 1.26 ✓ | 1.87 ✓ | 2.09 ✗ (half a bar) | 0.97 ✓ | 3/4 |
| BeatNet offline | 0.00 ✗ | 1.88 ✓ | 0.10 ✗ | 0.02 ✗ | 1/4 |
| All-In-One (2026-09-23 run) | bar phase ✓ | ✓ | ✗ (half a bar) | ✓ | 3/4 phase† |
| **Beat This! beats + our kick phase** | **1.28 ✓** | **1.88 ✓** | **1.10 ✓** | **0.98 ✓** | **4/4** |
| Beat This! beats + its majority downbeat phase | 1.28 ✓ | 1.88 ✓ | 1.10 ✓ | 0.04 ✗ | 3/4 |

† All-In-One's beat output started 2–6 s into these clips, so its literal
"first downbeat" misses count 1 on 3 of 4. The phase column only asks whether
its downbeats line up with the label bar after bar.

## Results: is our beat grid on the beat? (F-measure vs Beat This!)

| clip | current grid F | worst gap to a model beat | cause |
|---|---|---|---|
| solo-01, solo-02, group-synced-01, 345b, b822, a106 | 0.99–1.00 | 38–52 ms | fine |
| solo-07 | 0.52 | 237 ms | tempo speeds up (125 to 129 BPM). One fixed grid can't follow it. |
| **bhangra 5716** | **0.00** | **319 ms** | The tempo is right (94.8 BPM) but the phase is half a beat off. `_refine_grid` locks onto the off-beat, where the dhol and claps have more onset energy than the beat. |

Beat This!, madmom and BeatNet agree with each other on the beats (F ≥ 0.96
on every clip). The disagreements are all about bar phase.

A single least-squares grid fitted through Beat This!'s beats is within 28 ms
on 7 clips and within 88 ms on solo-07. So the current contract
(`countOneS` plus a constant `secondsPerCount`) is good enough for now.

## Unlabelled lessons: count 1 side by side (to check by ear)

| lesson | BPM | current (prod) | BT final0 | BT + DBN | madmom (NC) | BeatNet | **BT beats + kick** |
|---|---|---|---|---|---|---|---|
| bhangra `job_5716ecd3…` (47.7 s) | 94 | 2.26 (off-beat) | 0.70 | 0.06 | 2.57 | 2.56 | **2.58** |
| `job_345b747b…` (35.5 s) | 103 | 1.32 | 1.30 | 1.30 | 1.30 | 1.30 | **1.30** |
| `job_b8223229…` (14.4 s) | 150 | 1.11 | 1.48 | 1.48 | 1.08 | 0.68 | **1.08** |
| `job_a10682e7…` (13.1 s) | 115 | 1.04 (warned weak) | 2.06 | 2.06 | 1.00 | 2.06 | **1.00** |

- **Bhangra.** All four models put the bar downbeats on 2.57 + 2.52n. Beat
  This!'s 0.70 and 0.06 come from a 3-beat pickup bar at the start. The
  production value of 2.26 isn't on any beat.
- **b822 and a106** are where Beat This! and the kick rule disagree: one beat
  apart on b822, half a bar apart on a106. They need labels. They're the
  cheapest way to find out whether the kick rule holds up.

## Licences and cost

| model | code | weights | commercial OK? | CPU cost, 15–60 s clip | downbeats? | tempo drift |
|---|---|---|---|---|---|---|
| **Beat This!** (CPJKU, ISMIR 2024), PyPI `beat-this` 1.1.0 | MIT | **MIT.** The README says "The code and the published model weights are released under the MIT license." | **Yes.** The README notes that some training audio is copyrighted and that assessing that is the user's call. The usual caveat for trained models. | ~1 s load; 0.1–0.7 s inference (M4, all threads); 1.1 s single-threaded on 48 s; ~550 MB RSS. Checkpoints: final0 81 MB, small0 8 MB. | yes | yes (frame-wise, no fixed tempo) |
| madmom RNN+DBN | BSD | **CC BY-NC-SA 4.0** | **No** (weights) | ~1–3 s | yes | yes |
| All-In-One (mir-aidj) | MIT | not stated separately | unclear | 80–130 s per clip on 8 Modal CPUs. Needs demucs source separation, NATTEN and madmom. | yes, plus sections | yes |
| BeatNet | CC BY 4.0 | CC BY 4.0 | yes, with attribution | ~0.2 s | yes | yes |
| Masked-diffusion beat tracking (Foscarin et al., ISMIR 2026, arXiv 2608.04624) | not released as far as I found | n/a | n/a | iterative, so slower than Beat This! | yes | yes |

The DBN step for Beat This! needs madmom's code, which is BSD, not its weights.
It changed nothing here except the bhangra's pickup bar, so skip it and
leave madmom out of the image. BeatNet is licence-clean but scored 1/4 on
count 1, and it drags in madmom and pyaudio. No 2025–26 release I found
beats Beat This! with usable weights. C++ and Rust ports of Beat This! exist
if we ever want it outside Python.

## Recommendation: upgrade now

It fixes a whole class of wrong grids (off-beat and drifting ones) that no
amount of "try another 1" can fix, since every alternate sits on the same
wrong grid. It costs no GPU and about a second of CPU, and the licence is clean.

What to integrate (production code wasn't touched in this task):

1. **Beats.** `beat_this.inference.File2Beats("final0", device="cpu", dbn=False)`
   on the WAV we already extract with imageio-ffmpeg. Fit `seconds_per_count`
   and the phase with a least-squares line through its beats. This replaces
   `librosa.beat_track` + `_refine_grid`.
2. **Count 1.** Keep `_count_one`'s kick rule, but run it on the model's beats:
   the beat-of-the-bar with the most low-band accent, then the first such beat
   after the music starts. Use the model's own majority downbeat phase as the
   tiebreak when the kick margin is under 1.1, which is the existing
   "weak guess" warning.
3. **Alternates.** Keep `count_one_alternates` (the other three beats of the
   bar). Put the model's downbeat pick first when it differs from the kick
   pick. When the two picks differ, the second guess is usually the other
   one. solo-07 is the only labelled clip where they differ, and there the
   kick pick was right.
4. **Modal image.** Add CPU-only `torch` + `torchaudio` (from the PyTorch CPU
   index, ~200 MB), plus `beat-this==1.1.0` and its small dependencies (einops,
   rotary-embedding-torch, soxr). Download `final0.ckpt` at image build time
   so no job fetches it from JKU's server. No GPU and no madmom. Add the
   licence line to the credits/NOTICE.
5. **Before trusting it more,** label b822 and a106 with the existing
   labelling page (and the bhangra, to confirm 2.58). With 4 labels, 4/4
   against 3/4 is suggestive, not proof.

Later, only if a drifting clip still looks wrong at about 90 ms: pass
per-beat times (`beat_times_s`) through the contract instead of one constant
`secondsPerCount`.
