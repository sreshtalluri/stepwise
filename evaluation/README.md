# Evaluation clips

## Where things live, and why

| What | Where | Why there |
|---|---|---|
| The **manifest** (`clips.yaml`) | **In git** | Text. Diffable, reviewable, and it records *why* each clip exists. |
| The **videos** | **Modal Volume `stepwise-eval`** | Large binaries, and other people's work. Never in git. Every GPU run reads the same bytes without re-downloading. |
| A **local cache** | `~/.stepwise-clips/` | Working copies. Gitignored. |
| **Labels** (`labels/*.json`) | **In git** | Hand-labelled ground truth, including for uploaded lessons that are not in `clips.yaml` (keyed by job id). `labels/count_one.json`: the owner's count 1, scored by `packages/beat-detect/python/tests/test_count_one_labels.py`. Never the video. |

The manifest is the artifact that matters. A clip is not "an interesting video" —
it is a **hypothesis about where the pipeline breaks**, and the `why:` field
records that. Six months from now the URL may be dead; the reasoning still tells
you what to replace it with.

## Usage

```sh
uv tool install yt-dlp          # one time
pip install pyyaml              # one time

python evaluation/fetch.py --list       # manifest status
python evaluation/fetch.py solo-03      # fetch one
python evaluation/fetch.py --all        # fetch everything with a URL
python evaluation/fetch.py --status     # what is actually in the Volume
```

Then in a Modal function, mount it alongside the weights:

```python
clips = modal.Volume.from_name("stepwise-eval", create_if_missing=True)

@app.function(volumes={"/weights": weights, "/clips": clips}, gpu=GPU_TIER)
def run_eval(clip_id: str):
    path = f"/clips/{clip_id}.mp4"
```

## Rights — read this before making anything public

Three different situations, and they are not the same:

1. **Private pipeline testing.** Downloading a clip to check whether the
   reconstruction works. Defensible. Keep it in the private Volume, do not
   redistribute, do not commit it.
2. **A public demo.** The landing page shows a live lesson to strangers. This
   needs **explicit permission from the dancer**, recorded in the manifest.
3. **Anything a user uploads.** Their responsibility, stated in the ToS — but
   the upload screen must say it in plain language, once.

Set `rights:` honestly on every entry:

- `untested` — downloaded for private testing, no permission sought. **Never public.**
- `personal-test-only` — deliberately kept private.
- `permission-granted` — the dancer said yes. Record who and when in `notes:`.
- `needs-permission` — earmarked for public use, not cleared yet.

The `demo-public` entry is the one that must reach `permission-granted`. The
easiest source is the community this is launching into — the dance school, the
DJ's teams. Ask one person, get a yes in writing, and you have a demo clip that
is both legally clean and genuinely from the audience you are building for.

## What the set is designed to prove

Ten **core** clips covering the MVP assumption (one dancer, front camera, ≤60s,
steady, no cuts), spanning fast motion, a full turn with the back to camera, low
light, loose clothing, a small subject, floor work, self-occlusion, length, and
symmetric choreography.

Three **stress** clips that are expected to be hard. Their value is proving the
product degrades *honestly*. `stress-cropped-feet` has a deliberately negative
success criterion: **no foot may ever be drawn solid**, and grounding must report
`none` rather than inventing a floor.

Two **violators** that must be *refused*, not processed — a duet with different
roles, and a clip with hard cuts. A system that confidently mangles these is
worse than one that declines them.

One **demo** clip for the public landing page, which needs real permission.
