# Not part of upstream Fast-SAM-3D-Body -- see PROVENANCE.md.
"""Runnable self-check for process_clip.py's pure dancer-cap logic (W8).

No ffmpeg, torch, GPU, or detector needed -- refusal_reason_for is plain
logic. Which tracks count as dancers is test_track_hygiene.py's job.
Run: python tools/test_process_clip.py
"""
from process_clip import MAX_DANCERS, refusal_reason_for


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
