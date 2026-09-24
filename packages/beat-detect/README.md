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

## Libraries: Beat This! for beats, librosa for the kick rule

- **Beat This!** (CPJKU, ISMIR 2024; PyPI `beat-this==1.1.0`, checkpoint
  `final0`, CPU, no DBN) finds the beats. Code **and** weights are MIT: its
  README says "The code and the published model weights are released under
  the MIT license." Needs CPU-only `torch` + `torchaudio`; ~1 s to import and
  load once per process, then 0.2-0.7 s per 15-50 s clip.
- **librosa** (ISC) supplies the low-band onset envelope for the kick rule
  and decodes the WAV.
- **Not used:** madmom's RNN downbeat weights are CC BY-NC-SA 4.0
  (non-commercial), so they are out. madmom's *code* is BSD, but we only
  needed it for Beat This!'s optional DBN, which changed nothing on our clips.
  BeatNet (CC BY 4.0) scored 1/4 on labelled count 1 and drags in madmom and
  pyaudio. The comparison is `docs/research/downbeat-models.md` (branch
  `research/downbeat-models`).

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

## How the grid is chosen (2026-09-24)

1. **Beats.** Beat This! returns beat and downbeat times. `_fit_grid` fits
   the least-squares constant grid (`phase + secondsPerCount * n`) through
   the beats. Each beat's count number steps by its rounded gap, so a beat the
   model skipped keeps its count. This replaces `librosa.beat_track` +
   `_refine_grid`, which on the bhangra lesson locked onto the off-beat (the
   dhol and claps are louder there) and put every count ~300 ms off.
2. **Count 1.** `_count_one` finds the bar downbeat as the beat-of-the-bar
   (count number mod 4) with the strongest low-band (<150 Hz, kick) onsets at
   the model's beats. Count 1 is the first such beat from the first beat the
   model heard. When no beat of the bar is >=10% ahead of the runner-up, the
   kick rule is a coin toss: the model's majority downbeat decides instead
   and the "weak guess" warning fires.
3. **Alternates.** The other three beats of that bar ride along as
   `count_one_alternates` for "try another 1". When the kick rule and the
   model disagree, the pick that lost goes first; the rest follow by accent.

Labelled clips (the owner's count 1, labelling page 2026-09-23), pass = within
70 ms, measured end to end from the mp4 through `propose_grid`:

| clip | label | old (librosa grid + kick) | new count 1 | BPM | worst beat off the grid |
|---|---|---|---|---|---|
| solo-01 | 1.292 | 1.292 ✓ | 1.268 ✓ | 141.00 | 28 ms |
| solo-02 | 1.905 | 1.905 ✓ | 1.888 ✓ | 115.07 | 15 ms |
| group-synced-01 | 1.120 | 1.120 ✓ | 1.101 ✓ | 120.01 | 18 ms |
| solo-07 | 1.030 | 1.358 ✗ (drift) | 1.052 ✓ | 126.83 | 86 ms (speeds up 125 -> 129) |

Beat This!'s own first downbeat alone misses solo-07 by half a bar (0.04 s),
which is why the kick rule still picks the phase.

Known gaps: one constant tempo per clip (a drifting track sits up to ~90 ms
off at its ends; the upgrade is per-beat times in the contract), and which of
two bars starts the 8-count phrase is not modelled. "Set count 1" stays the
override.

Labelling protocol: in the app, open the lesson, scrub to where the dancer
counts 1, press "Set count 1 here". The structure is saved in
`localStorage["stepwise.lesson-structure.v1.<lessonId>"]`; copy
`grid.countOneS` per lesson from the browser console.

## Layout

```
python/beat_detect/propose.py                 propose_grid(), ProposedGrid, TempoAlternate
python/tests/test_propose.py                  unit tests on recorded/synthesized model output
python/tests/fixtures/beat-this-recorded.json Beat This! beats for bhangra-5716 and solo-07 (times only)
```

## Running

```
cd python
uv sync
uv run pytest
```
