"""The one runnable check for fingerprint.py: does it actually catch the
re-encodes it claims to, and does it actually refuse everything else?

Generates its own near-duplicates with ffmpeg from whatever real clips it is
pointed at, so the thresholds in fingerprint.py are measured rather than
asserted. Run with the eval clips for the real numbers:

    modal volume get stepwise-eval /solo-01.mp4 /tmp/fpclips/solo-01.mp4   # x4
    STEPWISE_FP_CLIPS=/tmp/fpclips python3 -m pytest test_fingerprint.py -s

With no clips available it synthesises two moving-gradient videos instead, so
the logic still has a check in CI without shipping video into the repo
(evaluation/clips.yaml: the manifest is versioned, the videos never are).
"""
from __future__ import annotations

import itertools
import os
import subprocess
import tempfile

import pytest

import fingerprint as fp

pytestmark = pytest.mark.skipif(not fp.ffmpeg_available(), reason="needs ffmpeg + ffprobe")

# Each of these is something a clip in the wild has actually been through.
# (name, ffmpeg args, is_the_same_dance)
VARIANTS = [
    ("reencode", ["-c:v", "libx264", "-crf", "30", "-preset", "veryfast", "-an"], True),
    ("fps24", ["-r", "24", "-c:v", "libx264", "-crf", "26", "-an"], True),
    ("scale70", ["-vf", "scale=trunc(iw*0.7/2)*2:trunc(ih*0.7/2)*2",
                 "-c:v", "libx264", "-crf", "24", "-an"], True),
    ("crop5", ["-vf", "crop=trunc(iw*0.90/2)*2:trunc(ih*0.90/2)*2,scale=576:1024",
               "-c:v", "libx264", "-crf", "24", "-an"], True),
    ("bright", ["-vf", "eq=brightness=0.10:contrast=1.15",
                "-c:v", "libx264", "-crf", "24", "-an"], True),
    # Not duplicates, and both are traps. A mirror passes the aHash gate; a
    # 2s trim passes BOTH perceptual gates and is caught only by duration.
    ("mirror", ["-vf", "hflip", "-c:v", "libx264", "-crf", "24", "-an"], False),
    ("trim2s", ["-ss", "2", "-c:v", "libx264", "-crf", "24", "-an"], False),
]


def _synth(path: str, seed: int) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
         # `decimals` is a `testsrc` option, not a `testsrc2` one -- ffmpeg
         # rejects the whole filtergraph with "Option not found", so this
         # generator raised CalledProcessError and test_separation could never
         # run on any ffmpeg. Dropped rather than swapped for `testsrc`: its
         # default is 0, so it was asking for the default anyway, and the
         # clip's per-seed content comes from the `rotate` below regardless.
         "-i", f"testsrc2=size=576x1024:rate=30:duration=12,"
               f"rotate=a={seed}*PI/6+t/{seed + 2}", "-c:v", "libx264", "-crf", "20", path],
        check=True,
    )


def _sources(tmp: str) -> list[str]:
    d = os.environ.get("STEPWISE_FP_CLIPS")
    if d and os.path.isdir(d):
        found = sorted(os.path.join(d, f) for f in os.listdir(d) if f.endswith(".mp4"))
        if len(found) >= 2:
            return found
    out = []
    for i in (1, 2, 3):
        p = os.path.join(tmp, f"synth-{i}.mp4")
        _synth(p, i)
        out.append(p)
    return out


def _variant(src: str, tmp: str, name: str, args: list[str]) -> str:
    dst = os.path.join(tmp, f"{os.path.basename(src)[:-4]}__{name}.mp4")
    pre = ["-ss", "2"] if name == "trim2s" else []
    subprocess.run(["ffmpeg", "-y", "-v", "error", *pre, "-i", src, *args, dst], check=True)
    return dst


def test_separation():
    with tempfile.TemporaryDirectory() as tmp:
        sources = _sources(tmp)
        prints: dict[str, dict] = {}
        same_dance: dict[str, str] = {}  # key -> which source it came from
        for src in sources:
            key = os.path.basename(src)[:-4]
            prints[key] = fp.fingerprint(src)
            same_dance[key] = key
            for name, args, is_dupe in VARIANTS:
                vkey = f"{key}__{name}"
                prints[vkey] = fp.fingerprint(_variant(src, tmp, name, args))
                same_dance[vkey] = key if is_dupe else vkey

        assert all(p["frames"] > 0 for p in prints.values()), "ffmpeg decoded nothing"

        worst_true = -1.0
        best_false = 999.0
        failures = []
        for a, b in itertools.combinations(sorted(prints), 2):
            fa, fb = prints[a], prints[b]
            expect = same_dance[a] == same_dance[b]
            got = fp.same_clip(fa, fb)
            ha = fp.mean_hamming(fa["ahash"], fb["ahash"])
            hd = fp.mean_hamming(fa["dhash"], fb["dhash"])
            if expect:
                worst_true = max(worst_true, hd)
            else:
                best_false = min(best_false, hd)
            # A false POSITIVE is the failure that matters: it serves one
            # dancer's reconstruction for another dancer's upload. A false
            # negative just costs one more GPU run, so it is reported, not
            # failed on -- see the crop ceiling in the module docstring.
            if got and not expect:
                failures.append(f"FALSE POSITIVE {a} ~ {b}  aHash={ha:.2f} dHash={hd:.2f}")
            if expect and not got:
                print(f"  missed (costs one GPU run): {a} ~ {b} aHash={ha:.2f} dHash={hd:.2f}")

        print(f"\n  worst true-duplicate dHash: {worst_true:.2f} "
              f"(threshold {fp.MATCH_MAX_DHASH_BITS})")
        print(f"  closest non-duplicate dHash: {best_false:.2f}")
        assert not failures, "\n".join(failures)


def test_exact_bytes_match_without_ffmpeg():
    # The sha256 path must stand on its own: it is the only dedupe available
    # on a host with no ffmpeg, and it must never need a perceptual hash.
    a = {"sha256": "a" * 64, "frames": 0, "ahash": "", "dhash": "", "duration_s": None}
    assert fp.same_clip(a, dict(a))
    b = dict(a, sha256="b" * 64)
    assert not fp.same_clip(a, b), "no perceptual evidence must mean no match, not a guess"
