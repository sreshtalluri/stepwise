"""Content-addressed clip identity: skip a $0.06-0.08 / 2-4 minute GPU
reconstruction when the same dance has already been reconstructed.

Two hashes, deliberately, because they answer different questions:

  * **sha256 of the file bytes** -- exact. Catches the single most common
    duplicate by far (the same file uploaded twice: a retry, a second person
    sharing the same download, the same user on a second device). Free, no
    decoding, zero false-positive risk.

  * **A perceptual hash sequence over frames sampled at fixed wall-clock
    times** -- catches re-encodes, rescales and light crops, which is what a
    clip that has been round-tripped through a phone, a messaging app or a
    re-download actually looks like. Costs one ffmpeg decode.

Why a hand-written hash and no new dependency (docs/research/grounding-models.md
section 1.5-1.6 sets the bar: anything that *ships* must be commercially
usable on all four axes -- code licence, weights licence, asset licence and
training-data terms):

  * The `pHash` C library is GPL-3.0 and `videohash` is likewise copyleft;
    both are off the table for a product that ships.
  * `imagehash` (BSD-2) would be usable but drags in Pillow + scipy for what
    is four lines of numpy, and numpy is already a dependency (api.py reads
    the npz with it).
  * A learned video embedding would put us straight back into axis 4, the
    training-data axis that disqualified most of the grounding survey.

So: the two constructions below are textbook and unencumbered -- an average
hash over an 8x8 luma grid ("aHash") and a horizontal-gradient hash ("dHash",
Krawetz's construction, published as a method, not as licensed source). Both
are reimplemented here from their description in a few lines of numpy. No
third-party code, no new licence obligation, nothing to record in
docs/LICENSES.md.

Frames are decoded by invoking the `ffmpeg` *binary* as a subprocess. That is
not linking, so ffmpeg's LGPL/GPL build options do not reach this repo, and
nothing is redistributed. ffmpeg is optional: without it the module degrades
to exact-sha256 dedupe only, which is still correct -- it just matches less.

**The asymmetry that sets every threshold here.** A false negative costs one
unnecessary GPU run: $0.08 and three minutes, and nobody notices. A false
positive serves dancer A's reconstruction to someone who uploaded dancer B --
wrong body, wrong motion, and a privacy failure, because a takedown on A's
clip would now also be reaching B's lesson. The two are not remotely
comparable, so the thresholds below are set well below the measured floor for
distinct clips rather than at the midpoint. See test_fingerprint.py for the
measured separation on real clips and real near-duplicates.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess

import numpy as np

# Frames are sampled at fixed *wall-clock* offsets, never at fixed frame
# indices: a re-encode routinely changes fps (30 -> 24, or a variable-rate
# phone capture normalised to constant), so frame 90 is not the same moment
# but t=3.0s is.
#
# The offsets are duration/MAX_SAMPLES apart, so the samples span the WHOLE
# clip rather than its first 24 seconds. That matters for false positives: a
# fixed 1.5s interval over 16 samples leaves the back half of a 40s clip
# unhashed, and two different dances that open the same way would collide
# there. Spacing by duration is still re-encode-stable because the duration
# gate below already requires the two durations to agree within 0.5s, so
# sample i lands within 0.5/16 = 31ms of the same moment in both clips.
MAX_SAMPLES = 16
FALLBACK_INTERVAL_S = 1.5  # only when ffprobe could not read a duration
GRID = 8  # 8x8 luma grid -> 64 bits per frame per hash

# Two clips are the same clip only if their durations agree this closely. A
# re-encode preserves duration to within a frame or two; a trim does not, and
# a trimmed clip is genuinely a different lesson (different counts, different
# parts), not a duplicate.
DURATION_TOLERANCE_S = 0.5

# Mean Hamming distance per frame, over 64 bits, below which two clips are
# called the same. BOTH must pass. The two numbers differ because the two
# hashes have genuinely different scales on real footage. Measured over the
# four real eval clips (solo-01, solo-02, solo-07, group-synced-01) and eight
# generated variants of each, 486 cross-clip pairs (test_fingerprint.py):
#
#                    worst TRUE duplicate    closest FALSE pair
#                    we intend to catch      (duration-compatible)
#   aHash            5.81  (solo-07, 5% crop)   5.44  (solo-07 vs its mirror)
#   dHash            9.94  (solo-07, 5% crop)  23.62  (solo-01 vs its mirror)
#
# Read the aHash row again: its closest false pair (5.44) is BELOW its worst
# true pair (5.81). aHash cannot separate these clips at any threshold. dHash
# can, with a 2.4x margin, and the conjunction is what makes aHash harmless --
# a mirrored clip passes the aHash gate and is stopped dead by dHash (23.62).
# Keep both; deleting the aHash gate would not break any measured case, but it
# is the cheap second opinion that catches whatever dHash alone would miss.
#
# A mirrored clip must NOT dedupe to its original: left and right are the
# whole point of a dance lesson, and serving the mirrored reconstruction would
# teach every step backwards.
#
# Measured ceiling, stated rather than hidden: a crop of 10% off every side
# (19% of the frame area) lands at dHash 14.06-16.38 and is NOT caught. That
# is a false negative -- it costs one extra GPU run, about $0.08 -- and
# raising the threshold to 17 to catch it would leave only a 1.4x margin to
# the mirror at 23.62, which is the wrong trade (see module docstring).
MATCH_MAX_AHASH_BITS = 8.0
MATCH_MAX_DHASH_BITS = 12.0

_FFMPEG = shutil.which("ffmpeg")
_FFPROBE = shutil.which("ffprobe")


def ffmpeg_available() -> bool:
    return bool(_FFMPEG and _FFPROBE)


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def probe_duration_s(path: str) -> float | None:
    if not _FFPROBE:
        return None
    try:
        out = subprocess.run(
            [_FFPROBE, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True, timeout=60, check=True,
        ).stdout.strip()
        return float(out)
    except (subprocess.SubprocessError, ValueError):
        return None


def _decode_grid_frames(path: str, n: int, duration_s: float | None) -> np.ndarray | None:
    """Decode up to `n` frames as (n, GRID, GRID+1) uint8 luma.

    One ffmpeg invocation, not one per frame. The extra column is what dHash
    needs (GRID horizontal comparisons requires GRID+1 samples); aHash uses
    the leading GRID columns of the same buffer, so both hashes come out of a
    single decode.

    `scale` here squashes to a fixed grid, ignoring aspect ratio, which is
    deliberate: a 576x1024 clip re-encoded to 480x854 must land on the same
    grid, and a letterboxed/pillarboxed variant should too.
    """
    if not _FFMPEG:
        return None
    w, h = GRID + 1, GRID
    interval = duration_s / n if duration_s and duration_s > 0 else FALLBACK_INTERVAL_S
    cmd = [
        _FFMPEG, "-v", "error", "-i", path,
        "-vf", f"fps=1/{interval:.6f},scale={w}:{h}:flags=area,format=gray",
        "-frames:v", str(n), "-f", "rawvideo", "-",
    ]
    try:
        raw = subprocess.run(cmd, capture_output=True, timeout=300, check=True).stdout
    except subprocess.SubprocessError:
        return None
    frame_bytes = w * h
    count = len(raw) // frame_bytes
    if count == 0:
        return None
    return np.frombuffer(raw[: count * frame_bytes], dtype=np.uint8).reshape(count, h, w)


def _ahash(grid: np.ndarray) -> int:
    """Average hash: bit set where the cell is above the frame's own mean.
    Invariant to global brightness/contrast scaling, which is most of what a
    re-encode does to the luma plane."""
    cells = grid[:, : GRID].astype(np.float64)
    bits = cells > cells.mean()
    return int("".join("1" if b else "0" for b in bits.ravel()), 2)


def _dhash(grid: np.ndarray) -> int:
    """Difference hash: bit set where each cell is brighter than its right
    neighbour. Encodes local gradient direction rather than absolute level."""
    bits = grid[:, 1:].astype(np.int16) > grid[:, : GRID].astype(np.int16)
    return int("".join("1" if b else "0" for b in bits.ravel()), 2)


def fingerprint(path: str) -> dict:
    """Everything identity-related about a clip file, in one pass.

    Returns a dict that is JSON-safe and small enough to live in a filename
    (see api.py's index): `sha256`, `duration_s`, and two hex hash sequences.
    `frames` is 0 when ffmpeg is unavailable or the decode failed -- the
    caller must then fall back to exact-sha256 matching only.
    """
    duration_s = probe_duration_s(path)
    grids = _decode_grid_frames(path, MAX_SAMPLES, duration_s)
    ahash: list[int] = []
    dhash: list[int] = []
    if grids is not None:
        for g in grids:
            ahash.append(_ahash(g))
            dhash.append(_dhash(g))
    return {
        "sha256": sha256_file(path),
        "duration_s": duration_s,
        "frames": len(ahash),
        "ahash": "".join(f"{v:016x}" for v in ahash),
        "dhash": "".join(f"{v:016x}" for v in dhash),
    }


def _unpack(hex_seq: str) -> list[int]:
    return [int(hex_seq[i:i + 16], 16) for i in range(0, len(hex_seq), 16)]


def mean_hamming(a_hex: str, b_hex: str) -> float | None:
    """Mean per-frame Hamming distance over the frames the two clips share.

    None when either side has no perceptual frames. Compares frame i to frame
    i because both were sampled at the same wall-clock offsets; that is what
    makes this sensitive to *when* something happens, not just to what the
    clip looks like on average -- two different dances in the same studio with
    the same dancer are the case this has to separate, and a single aggregate
    hash would not.
    """
    a, b = _unpack(a_hex), _unpack(b_hex)
    n = min(len(a), len(b))
    if n == 0:
        return None
    return sum(bin(a[i] ^ b[i]).count("1") for i in range(n)) / n


def same_clip(fp_a: dict, fp_b: dict) -> bool:
    """Is B the same recording as A, allowing for a re-encode?

    Exact byte equality short-circuits. Otherwise all three gates must pass:
    duration, aHash and dHash.

    The duration gate is not a formality -- it is load-bearing. A clip trimmed
    by two seconds sits at dHash 5.57 against its own original (measured on
    solo-07), which is *inside* the perceptual threshold. Duration is the only
    thing that separates "the same recording, re-encoded" from "the first 90%
    of the same recording", and those are different lessons: different counts,
    different parts.
    """
    if fp_a.get("sha256") and fp_a["sha256"] == fp_b.get("sha256"):
        return True
    if not fp_a.get("frames") or not fp_b.get("frames"):
        return False  # no perceptual evidence -> not a match, never a guess
    da, db = fp_a.get("duration_s"), fp_b.get("duration_s")
    if da is None or db is None or abs(da - db) > DURATION_TOLERANCE_S:
        return False
    ha = mean_hamming(fp_a["ahash"], fp_b["ahash"])
    hd = mean_hamming(fp_a["dhash"], fp_b["dhash"])
    if ha is None or hd is None:
        return False
    return ha <= MATCH_MAX_AHASH_BITS and hd <= MATCH_MAX_DHASH_BITS
