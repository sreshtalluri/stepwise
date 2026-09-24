# Not part of upstream Fast-SAM-3D-Body -- see PROVENANCE.md.
"""Runnable self-check for process_clip.py's pure dancer-cap logic (W8).

No ffmpeg, torch, GPU, or detector needed -- select_confident_tracks and
refusal_reason_for are plain Counter/set logic, tested here with synthetic
per-frame track-id counts. Run: python tools/test_process_clip.py
"""
from collections import Counter

from process_clip import (
    CONFIDENT_MIN_FRAMES,
    MAX_DANCERS,
    refusal_reason_for,
    select_confident_tracks,
)


def test_track_below_min_frames_is_not_confident():
    counts = Counter({1: CONFIDENT_MIN_FRAMES - 1})
    assert select_confident_tracks(counts) == set()


def test_track_at_min_frames_is_confident():
    counts = Counter({1: CONFIDENT_MIN_FRAMES})
    assert select_confident_tracks(counts) == {1}


def test_flaky_false_detection_does_not_count_as_a_dancer():
    # A one-frame false-positive track alongside two real, well-tracked dancers.
    counts = Counter({1: 40, 2: 38, 99: 1})
    assert select_confident_tracks(counts) == {1, 2}


def test_exactly_at_cap_is_not_refused():
    confident = set(range(MAX_DANCERS))
    assert refusal_reason_for(len(confident)) is None


def test_one_over_cap_is_refused():
    confident = set(range(MAX_DANCERS + 1))
    assert refusal_reason_for(len(confident)) == "too_many_dancers"


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")
