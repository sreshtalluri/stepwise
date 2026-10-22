# beat-labeler

A local page for checking the beat models' tempo and count 1 against your ear,
one lesson at a time, and saving what's right. Temporary research tooling.

```
cd tools/beat-labeler
uv run --project ../../packages/beat-detect/python python prep.py   # once: runs the models
python3 server.py                                                   # http://127.0.0.1:8765
```

`prep.py` needs `data/media/<job_id>.mp4` (from `/api/jobs/<id>/video`) and
`data/queue.json` (`GET /owner/queue`). Labels land in `data/labels.json`. All
of `data/` is git-ignored: this repo is public and holds no lesson ids or video.

The scoreboard counts a model right on a clip when its tempo is within 3% of
yours and its count 1 is on the same beat of the bar (within 70 ms), the same
rule as `packages/beat-detect/python/tests/test_count_one_labels.py`.
