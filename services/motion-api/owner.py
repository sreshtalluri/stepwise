"""The owner's count-1 tool: who may use it, and the grid maths it runs.

Brute force until a better downbeat model exists. The beat detector's GRID is
right; its count 1 is sometimes off by exactly one beat (fast, ~150 BPM
songs). So the owner listens, picks the real 1, and `POST /owner/jobs/{job_id}/
count-one` moves only the phase: seconds_per_count, bpm and every other field
stay the detector's (api.py owns the endpoints; this file is the pure part).

Auth is one shared key, `STEPWISE_OWNER_KEY` (Modal Secret `stepwise-owner`),
sent as `x-stepwise-owner-key`. Unset -> the endpoints do not exist (404).
"""
from __future__ import annotations

import hmac
import os
import threading
import time

HEADER = "x-stepwise-owner-key"


def configured() -> bool:
    return bool(os.environ.get("STEPWISE_OWNER_KEY"))


def key_ok(headers) -> bool:
    key = os.environ.get("STEPWISE_OWNER_KEY")
    if not key:
        return False
    # Bytes, not str: compare_digest raises on non-ASCII str, and the header
    # is attacker-controlled.
    return hmac.compare_digest((headers.get(HEADER) or "").encode(), key.encode())


# ip -> monotonic times of recent bad keys.
# ponytail: per replica, in memory; a guesser spread over many replicas gets
# MAX_FAILS each. The key is 192 random bits, so this only has to stop noise.
MAX_FAILS = 10
FAIL_WINDOW_S = 600.0
_FAILS: dict[str, list[float]] = {}
_FAILS_LOCK = threading.Lock()


def locked_out(ip: str) -> bool:
    now = time.monotonic()
    with _FAILS_LOCK:
        recent = [t for t in _FAILS.get(ip, []) if now - t < FAIL_WINDOW_S]
        _FAILS[ip] = recent
        return len(recent) >= MAX_FAILS


def record_failure(ip: str) -> None:
    with _FAILS_LOCK:
        _FAILS.setdefault(ip, []).append(time.monotonic())


class OffGrid(ValueError):
    """The requested count 1 does not land on this clip's timeline."""


def snap(count_one_s: float, spc: float, requested_s: float, end_s: float) -> tuple[float, int]:
    """The grid beat nearest `requested_s` -> (seconds, beats from count_one_s).

    The grid is `count_one_s + k * spc` for every integer k, so the owner can
    pick a beat before the detector's 1 as easily as one after it."""
    k = round((requested_s - count_one_s) / spc)
    t = count_one_s + k * spc
    if t < 0:  # rounded onto the beat before the clip starts
        k += 1
        t += spc
    if t > end_s:
        raise OffGrid(f"{requested_s:.3f} s is past the end of the clip ({end_s:.3f} s)")
    return round(t, 6), k


def set_count_one(pc: dict, requested_s: float, end_s: float) -> dict:
    """`proposed_counts` with count 1 moved to the grid beat nearest
    `requested_s`, marked `count_one_source: "owner"`, `count_one_confidence: 1`.

    The pick it replaces becomes the first alternate (the second guess), the
    other alternates follow with `shift_counts` measured from the new 1, and an
    alternate on the same beat of the bar as the new 1 is dropped: it is no
    longer an alternative. `count_total` is re-derived with the contract's
    formula (validate.py), since it depends on where count 1 sits.
    """
    spc = float(pc["seconds_per_count"])
    old = float(pc["count_one_s"])
    new, k = snap(old, spc, float(requested_s), end_s)
    olds = pc.get("count_one_alternates") or []
    alts = []
    if k % 4:
        # Alternates are the bar's other three beats with their share of the
        # kick accent (beat_detect._count_one), so the old pick's share is what
        # they leave over. Approximate when some were cut off by the clip's end.
        share = max(0.0, min(1.0, 1.0 - sum(float(a["confidence"]) for a in olds)))
        alts.append({"count_one_s": old, "shift_counts": -k, "confidence": round(share, 3)})
    for a in olds:
        shift = round((float(a["count_one_s"]) - new) / spc)
        if shift % 4:
            alts.append(dict(a, shift_counts=shift))
    alts = [a for a in alts if 0 <= a["count_one_s"] <= end_s][:3]
    out = {key: v for key, v in pc.items() if key != "count_one_alternates"}
    # count_one_confidence is how sure the producer is which beat is 1; a person
    # decided it, so 1 -- otherwise the lesson would still call it a guess
    # (apps/web LessonViewer `oneUnsure`) on exactly the clips that were fixed.
    out.update(count_one_s=new, count_total=max(1, int((end_s - new) // spc) + 1),
               count_one_source="owner", count_one_confidence=1.0)
    if alts:
        out["count_one_alternates"] = alts
    return out


def labels_path(clip_id: str) -> str:
    """One labels file per lesson, beside its other artifacts: removal sweeps
    everything named `{clip_id}.*` (retention.clip_artifact_paths), and a
    count 1 is derived from the person's audio just as `beats.json` is.
    Evaluation gathers them by listing `*.count-one-labels.json`."""
    return f"/{clip_id}.count-one-labels.json"


def _self_check() -> None:
    pc = {"count_one_s": 1.439, "seconds_per_count": 0.4, "count_total": 1, "confidence": 0.8,
          "bpm": 150.0, "alternates": [], "warnings": [],
          "count_one_alternates": [{"count_one_s": 1.839, "shift_counts": 1, "confidence": 0.3},
                                   {"count_one_s": 2.239, "shift_counts": 2, "confidence": 0.2},
                                   {"count_one_s": 2.639, "shift_counts": 3, "confidence": 0.1}]}
    out = set_count_one(pc, 1.85, 10.0)
    assert out["count_one_s"] == 1.839 and out["count_one_source"] == "owner"
    assert [a["shift_counts"] for a in out["count_one_alternates"]] == [-1, 1, 2]
    assert snap(0.3, 0.4, 0.0, 5.0) == (0.3, 0)
    print("owner: count-1 maths ok")


if __name__ == "__main__":
    _self_check()
