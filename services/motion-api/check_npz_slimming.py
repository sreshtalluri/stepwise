"""Does dropping `pred_vertices`/`expr_params` change the MotionResult?

`caching-retention` slims the npz on save (process_clip._strip_unread) and
claims two things:

  1. `skel_state` is untouched, and
  2. the MotionResult rebuilt from the stripped npz is byte-identical to the
     one rebuilt from the fat one.

Claim 2 is the one worth checking on the MERGED code rather than on the branch,
because the merged builder reads more of the npz than the branch's did (the
real floor solve and the real intrinsics both read arrays the branch's copy
never opened). If any of those newly-read arrays had been in the stripped set,
the slimming would have silently changed the served document.

Pure numpy, no GPU, no Modal. Run:

    PYTHONPATH=. python check_npz_slimming.py
"""
from __future__ import annotations

import io
import json
import sys

import numpy as np

sys.path.insert(0, ".")
sys.path.insert(0, "vendor/fast-sam-3d-body/tools")

import motion_result  # noqa: E402
from process_clip import UNREAD_PER_FRAME_KEYS, _strip_unread  # noqa: E402

N_FRAMES, N_JOINTS, TRACK = 24, 127, 1
rng = np.random.default_rng(7)


def _person() -> dict:
    skel = np.zeros((N_JOINTS, 8), dtype=np.float32)
    skel[:, 0:3] = rng.normal(0, 40, (N_JOINTS, 3))
    q = rng.normal(0, 1, (N_JOINTS, 4))
    skel[:, 3:7] = q / np.linalg.norm(q, axis=1, keepdims=True)
    skel[:, 7] = 1.0
    return {
        "skel_state": skel,
        "shape_params": np.asarray(rng.normal(0, 1, 45), dtype=np.float32),
        "hand_crop_rect": [10.0, 20.0, 110.0, 120.0],
        "foot_crop_rect": [30.0, 900.0, 130.0, 1000.0],
        "keypoints_2d": np.asarray(rng.normal(300, 50, (17, 3)), dtype=np.float32),
        # The two the slimming drops. pred_vertices is 94.8% of a real npz.
        "pred_vertices": np.asarray(rng.normal(0, 1, (18439, 3)), dtype=np.float32),
        "expr_params": np.asarray(rng.normal(0, 1, 72), dtype=np.float32),
    }


def _npz_bytes(per_frame: list) -> bytes:
    buf = io.BytesIO()
    np.savez_compressed(
        buf,
        refused=False,
        sample_times_s=np.arange(N_FRAMES) / 15.0,
        per_frame=np.array(per_frame, dtype=object),
        raw_detections=np.array([{TRACK: {"bbox": [100.0, 200.0, 400.0, 900.0], "score": 0.9}}
                                 for _ in range(N_FRAMES)], dtype=object),
        confident_track_ids=np.array([TRACK], dtype=np.int64),
        frame_width=576,
        frame_height=1024,
    )
    return buf.getvalue()


MANIFEST = {"fps": 15.0, "glb_paths": {str(TRACK): f"clip_track{TRACK}.glb"}}

fat = [{TRACK: _person()} for _ in range(N_FRAMES)]
slim = _strip_unread(fat)

# 1. skel_state (and everything else that is read) survives untouched.
for i, (f, s) in enumerate(zip(fat, slim)):
    assert np.array_equal(f[TRACK]["skel_state"], s[TRACK]["skel_state"]), f"skel_state differs at frame {i}"
    for k in ("keypoints_2d",):
        assert np.array_equal(f[TRACK][k], s[TRACK][k]), f"{k} differs at frame {i}"
    for k in ("hand_crop_rect", "foot_crop_rect"):
        assert f[TRACK][k] == s[TRACK][k], f"{k} differs at frame {i}"
    assert set(f[TRACK]) - set(s[TRACK]) == set(UNREAD_PER_FRAME_KEYS)

fat_bytes, slim_bytes = _npz_bytes(fat), _npz_bytes(slim)

# 2. The merged builder produces a byte-identical document from either.
doc_fat = motion_result.build_motion_result("job_x", "clip_x", fat_bytes, MANIFEST, None)
doc_slim = motion_result.build_motion_result("job_x", "clip_x", slim_bytes, MANIFEST, None)
a = json.dumps(doc_fat, sort_keys=True, separators=(",", ":"))
b = json.dumps(doc_slim, sort_keys=True, separators=(",", ":"))
assert a == b, "MotionResult CHANGED when the npz was slimmed"

# 3. And it is a real document, not an empty one that trivially matches.
p = doc_slim["persons"][0]
assert len(p["samples"]) == N_FRAMES and len(p["samples"][0]["joints"]) == N_JOINTS
assert any(r is not None for r in p["crop_rects"]["hands"]), "crop rects lost"
assert p["shape_params"] == {"source": "default_assumed"}, "standard surface, no vector"
assert "vector" not in p["shape_params"], "shape vector is being served again"

print(f"npz {len(fat_bytes):,} -> {len(slim_bytes):,} bytes "
      f"({100 * (1 - len(slim_bytes) / len(fat_bytes)):.1f}% smaller)")
print(f"MotionResult identical: {len(a):,} chars, {N_FRAMES} samples x {N_JOINTS} joints")
print("OK: slimming drops only", UNREAD_PER_FRAME_KEYS, "and changes no served value")
