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

## Known gap: downbeat, not just beat (relevant to A5)

librosa's `beat_track` returns evenly-spaced *beats*, not *downbeats* (which
beat starts the musical phrase / dance count). `count_one_s` here is simply
**the first detected beat**, not a modeled downbeat. madmom's
`DBNDownBeatTrackingProcessor` does model this; we didn't use it (licence,
above). Practically: the proposed `secondsPerCount` (tempo) is usually right,
but `countOneS` (where count 1 actually falls) can legitimately be off by up
to one beat even when confidence is high. This is exactly the kind of error
A5's "tap on the beat" correction UI needs to make cheap to fix — this module
does not attempt to resolve that UI question, only to flag that its downbeat
guess is weaker than its tempo guess.

## Real-audio test results (2026-09-18)

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
