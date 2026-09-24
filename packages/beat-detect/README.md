# beat-detect

Standalone, UI-free automatic beat/downbeat **proposal** for a clip's audio
(W11, `docs/TASKS.md`). Not a picker screen, not wired into
`packages/navigation`'s `LessonNavigator.tsx` — that's a later integration
(`docs/OPEN-DECISIONS.md` A5, still open).

## Why this exists

`packages/navigation/src/core.ts` already has a manual path
(`gridFromTaps()` — the learner taps along with the music) that produces a
`CountGrid`. This package produces the *same shape*, `{countOneS,
secondsPerCount, countTotal}`, automatically, so a future UI can pre-fill the
tap-in flow with a starting guess instead of an arbitrary default. **Manual
always wins** — this is enforced by naming (`propose_grid`, not
`detect_grid`/`get_grid`) and by shape (confidence + alternates travel
alongside the grid, never replacing it).

## Library choice: librosa, not madmom, not BeatNet

- **BeatNet**: excluded per ground rules (unmaintained, no clear licence).
- **madmom**: more accurate downbeat tracking (has a real DBN downbeat
  model), but its licence is murkier — BSD-2-Clause with some
  GPL-derived internals in older releases, and per-file license
  auditing would be needed before shipping. Not done here.
- **librosa** (used): `ISC` licence, confirmed from the installed
  package's own `METADATA` (`License: ISC`,
  `License :: OSI Approved :: ISC License (ISCL)`). Clearly licensed, at
  the cost of accuracy: librosa's `beat_track` finds *beats*, not
  *downbeats* — see "Known gap" below.

## Output shape

```python
from beat_detect import propose_grid

result = propose_grid("clip.mp4", clip_duration_s=19.7)
result.to_grid()  # -> {"countOneS": 0.09, "secondsPerCount": 0.418, "countTotal": 47}

result.confidence   # 0..1 — this module's own trust in the proposal
result.bpm          # informational
result.alternates   # [TempoAlternate("double-time", ...), TempoAlternate("half-time", ...)]
result.warnings     # e.g. tempo outside the plausible dance-practice band
```

`to_grid()` raises if `clip_duration_s` wasn't supplied at call time (no
`count_total` to report) — same reasoning as `endS` in `core.ts`: the caller
owns the clip's true end, this module never invents one.

## How the grid is chosen (2026-09-23)

1. **Tempo.** librosa's `beat_track` reading is only a starting point: its
   tempo is quantized to whole 512-sample lags (near 115-120 BPM the only
   values are 112.3 / 117.5 / 123.0 / 129.2), and a 2% error drifts the grid
   half a beat off within ~25 counts. `_refine_grid` searches +-6% around it
   for the constant spacing and phase that land on the most onset energy
   (6 ms envelope, 0.5 ms / 4 ms steps).
2. **Count 1.** `_count_one` finds the bar downbeat as the beat-of-the-bar
   (mod 4) with the strongest low-band (<150 Hz, kick) onsets, then puts
   count 1 on the EARLIEST strong beat (that downbeat, or the beat half a bar
   from it) after the music starts. It warns when no phase is >=10% ahead of
   the runner-up. The other three beats of the bar ride along as
   `count_one_alternates` (strongest accent first) for "try another 1".

   Why not the downbeat itself: on solo-02, the only clip with an owner label,
   the dancer's 1 is 0.862 s, and Beat This! (with and without DBN), madmom's
   RNN+DBN and the kick heuristic all put the bar downbeat at 1.88-1.905 s,
   exactly half a bar late. The earliest-strong-beat rule gets solo-02 right,
   but it is fitted to ONE label and moves count 1 two beats earlier than the
   music models on solo-01 (0.44 vs 1.29) and solo-07 (0.43 vs 1.36). Label
   more clips (below) before trusting either rule.

   Labelling protocol: in the app, open the lesson, scrub to where the dancer
   counts 1, press "Set count 1 here". The structure is saved in
   `localStorage["stepwise.lesson-structure.v1.<lessonId>"]`; copy
   `grid.countOneS` per lesson from the browser console. Score a rule by its
   error in beats modulo 8 (`((pred - truth) / spc)` rounded, mod 8, folded to
   -4..+4): 0 is right, +-2 is the half-bar error, +-4 the bar error.

Checked against Beat This! (CPJKU, run offline as a reference, not shipped):

| clip | ref BPM | old BPM / count 1 | new BPM / count 1 | ref first downbeat | new max beat error |
|---|---|---|---|---|---|
| solo-02 | 115.07 | 117.45 / 1.300 (prod) | 115.01 / 1.905 | 1.88 | 40 ms (old 257 ms) |
| solo-01 | 142.11 | 143.55 / 0.070 | 141.05 / 1.292 | 1.28 | 43 ms (old 210 ms) |
| group-synced-01 | 120.01 | 117.45 / 0.627 | 119.95 / 1.120 | 1.10 | 52 ms (old 245 ms) |
| solo-07 | 125 -> 129 (speeds up) | 129.20 / 0.070 | 129.02 / 1.358 (warns) | 1.94 | 237 ms (old 462 ms) |

Known gaps: a track that changes tempo (solo-07) cannot fit one constant
grid; and which of two bars starts the 8-count phrase is not modelled --
count 1 is the first strong beat. The dancer's joint speed (15 fps
MotionResult) was tried as a phase cue and did not separate the beats of the
bar on any clip, so it is not used. "Set count 1" stays the override.

## Real-audio test results (2026-09-18, before the refinement above)

`evaluation/clips.yaml`'s actual video files live in the Modal Volume
`stepwise-eval`, not in git. This session had `modal` already authenticated
and found real clips already cached locally at `~/.stepwise-clips/`
(`solo-01`, `solo-02`, `solo-07`, `group-synced-01` — fetched by a prior
session), so testing used those instead of re-fetching or falling back to
synthetic audio only:

| clip | duration | BPM | seconds/count | countOneS | countTotal | confidence |
|---|---|---|---|---|---|---|
| solo-01 | 19.71s | 143.6 | 0.418 | 0.093 | 47 | 0.93 |
| solo-02 | 32.53s | 117.5 | 0.511 | 0.070 | 64 | 0.91 |
| solo-07 | 23.58s | 129.2 | 0.464 | 0.070 | 51 | 0.94 |
| group-synced-01 | 33.08s | 117.5 | 0.511 | 0.627 | 64 | 0.95 |

All four landed inside the 70-180 BPM plausible-dance-tempo band, so no
half/double warning fired on any of them, and all four report high
confidence (0.91-0.95) — the beat intervals librosa found were very regular
(low coefficient of variation) on all four clips. **I could not verify these
against my own ear** — this session has no audio playback, so "is this
where I'd actually tap count 1" (the report's requested measure) could not
be checked subjectively. That's a real gap: high algorithmic regularity
doesn't rule out a consistent half/double-time lock, only *inconsistent*
tempo tracking, which none of these four clips exhibited. The synthetic
click-track test (`tests/python/test_propose.py`) covers the case this
module is explicitly weakest at self-detecting: it does not independently
confirm downbeat placement on human-danced (non-metronomic) music.

Additionally ran against a synthesized 120 BPM click track (public-domain,
generated in-test, no external asset) as the unit test fixture — confirms
the pipeline (ffmpeg extraction skipped since it's already audio → librosa →
confidence scoring) end to end on a case with a known, exact answer.

## Layout

```
python/beat_detect/propose.py    propose_grid(), ProposedGrid, TempoAlternate
python/tests/test_propose.py     synthesized-click-track self-check
```

## Running

```
cd python
uv sync
uv run pytest
```
