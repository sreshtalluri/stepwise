"""Perceptual video fingerprint — so a trending dance is reconstructed once.

WHY THIS AND NOT A LIBRARY
--------------------------
The bar (docs/LICENSES.md): stepwise will be a public platform, so a
non-commercial or copyleft licence on a fingerprint library is disqualifying.
What was considered:

  * `videohash` (MIT) — collapses a whole clip into ONE 64-bit hash of a frame
    collage. Licence fine, algorithm not: discarding the temporal axis is
    exactly what makes two different dances of similar length, framing and
    palette collide, and a collision here means serving someone a
    reconstruction of a dance they did not upload.
  * `ImageHash` (BSD-2) + our own temporal layer — fine licence, but it is a
    Pillow + scipy dependency for ~15 lines of DCT that numpy already does, in
    a service whose whole point is a small dependency surface
    (requirements-api.txt: fastapi, modal, numpy, jsonschema, pydantic).
  * TMK+PDQF (Meta ThreatExchange, BSD-3) — genuinely the right tool, built
    for video copy detection under re-encode/rescale. It is a C++ build with
    no maintained Python wheel, and it would be the third Meta licence in the
    tree. Revisit if the measured numbers below stop holding at scale; it
    replaces exactly the two public functions here.

So: **DCT perceptual hash (pHash) per sampled frame, compared as a sequence.**
Written here in numpy, licence `MIT` (this repo's own, see LICENSE) — no new
dependency at all beyond an `ffmpeg` binary on PATH, which the pipeline
already requires (tools/process_clip.py shells out to it).

ffmpeg does the decode, the greyscale conversion and the resize in one filter
chain, so this file never decodes a video frame itself.

THE DIRECTION THAT MATTERS
--------------------------
False positives are the dangerous direction. Reconstructing the same dance
twice costs $0.06–0.08 of GPU time; serving dancer B's body to someone who
uploaded dancer A's clip is the worst failure this product can produce
(DESIGN.md §7a2 says the same thing about identity swaps at a crossing).

So every gate below is set from the measured *negatives* and the positives are
allowed to fall where they fall. Three gates, each rejecting on its own:

  1. **Duration.** Cheap, and it is what separates "the same dance" from
     "a different excerpt of the same dance".
  2. **Discriminability (`self_spread`).** How much a clip's own frames differ
     from each other. A clip whose frames all look alike carries almost no
     information in a frame-hash sequence, so a low distance against it is not
     evidence of anything. Measured: `group-synced-01` (fixed wide camera, six
     dancers in a line) has self_spread 0.102, and its time-REVERSED copy
     scores 0.113 while a legitimate 10%-crop copy scores 0.111 — the two
     distributions interleave, and no threshold can separate them. The honest
     answer is to refuse to dedupe that clip at all and pay for the
     reconstruction.
  3. **Distance.** Mean normalised Hamming over aligned frames, plus a 95th
     percentile gate so "identical for 90% of the clip, different ending"
     cannot pass on a good mean.

Measured behaviour on the four real eval clips and 68 generated variants:
**0 false positives in 226 negative pairs, 37/56 true near-duplicates caught.**
Full table and what the misses cost: docs/research/dedupe-measurements.md.
"""
from __future__ import annotations

import hashlib
import subprocess
from typing import Optional

import numpy as np

SAMPLE_FPS = 2.0      # frames per second pulled out of the clip for hashing
THUMB = 32            # ffmpeg resizes each frame to THUMB x THUMB, greyscale
MAX_SECONDS = 60.0    # the PRD's clip cap; never hash more than the pipeline runs
FP_VERSION = 1        # bump if any constant here changes; old fingerprints stop comparing

# --- gates, every one set from measurement (docs/research/dedupe-measurements.md) ---
DURATION_TOLERANCE_S = 0.6
# 0.102 (group-synced-01, undedupable) < 0.15 < 0.205 (solo-07, the least
# varied clip that still discriminates). ponytail: this is the
# weakest-supported constant in the file — four clips is not a distribution.
# Revisit once real uploads exist; moving it UP only ever costs GPU money,
# moving it down is what risks a wrong match.
MIN_SELF_SPREAD = 0.15
# worst accepted true duplicate 0.170 | 0.180 | 0.250 closest rejected non-duplicate
MAX_MEAN_DISTANCE = 0.18
# worst accepted true duplicate 0.250 | 0.280 | 0.344 closest rejected non-duplicate
MAX_P95_DISTANCE = 0.28


def _dct_matrix(n: int) -> np.ndarray:
    """Orthonormal DCT-II basis. A 32x32 matmul either side is cheaper than
    depending on scipy.fft for one call."""
    k = np.arange(n)[:, None]
    x = (2 * np.arange(n)[None, :] + 1) * np.pi / (2 * n)
    m = np.cos(k * x)
    m[0] *= np.sqrt(0.5)
    return m * np.sqrt(2.0 / n)


_DCT = _dct_matrix(THUMB)


def _decode_thumbnails(video_path: str) -> np.ndarray:
    """(N, THUMB, THUMB) uint8 — greyscale, square-normalised frames at SAMPLE_FPS.

    scale=THUMB:THUMB deliberately ignores aspect ratio: a re-upload that was
    resized to a different aspect should still line up, and the DCT's
    low-frequency block is where the surviving signal is anyway. The cost of
    that choice is measured: a letterboxed re-upload ("screenrec" in the
    measurements) is NOT caught, because padding moves the content inside the
    square.
    """
    proc = subprocess.run(
        [
            "ffmpeg", "-v", "error", "-i", video_path,
            "-t", str(MAX_SECONDS),
            "-vf", f"fps={SAMPLE_FPS},scale={THUMB}:{THUMB}",
            "-pix_fmt", "gray", "-f", "rawvideo", "-",
        ],
        capture_output=True,
        check=True,
    )
    buf = np.frombuffer(proc.stdout, dtype=np.uint8)
    n = buf.size // (THUMB * THUMB)
    if n < 2:
        raise ValueError("clip has too few decodable frames to fingerprint")
    return buf[: n * THUMB * THUMB].reshape(n, THUMB, THUMB)


def _phash_bits(frames: np.ndarray) -> np.ndarray:
    """(N, 64) bool — the classic DCT hash, one per frame.

    Top-left 8x8 of the DCT is the low-frequency structure that survives
    re-encoding; the DC term is excluded from the median because it encodes
    overall brightness, which is the thing a re-upload changes most.

    (numpy on macOS/Accelerate raises spurious over/divide FPE flags from this
    stacked matmul. Verified against a per-frame loop: values are identical and
    finite. Not a bug worth working around.)
    """
    x = frames.astype(np.float64)
    coeffs = _DCT @ x @ _DCT.T                     # (N, 32, 32)
    block = coeffs[:, :8, :8].reshape(len(x), 64)  # (N, 64)
    med = np.median(block[:, 1:], axis=1, keepdims=True)
    return block > med


def _self_spread(bits: np.ndarray) -> float:
    """Mean pairwise Hamming distance between a clip's OWN frame hashes.

    This is the clip's discriminability: how much information its fingerprint
    actually carries. See gate 2 in the module docstring.
    """
    i = np.arange(len(bits))
    d = (bits[i[:, None]] != bits[i[None, :]]).mean(axis=2)
    return float(d[np.triu_indices(len(bits), 1)].mean())


def _pack(bits: np.ndarray) -> list[str]:
    return [b.tobytes().hex() for b in np.packbits(bits, axis=1)]


def _unpack(hexes: list[str]) -> np.ndarray:
    raw = np.frombuffer(b"".join(bytes.fromhex(h) for h in hexes), dtype=np.uint8)
    return np.unpackbits(raw.reshape(len(hexes), 8), axis=1).astype(bool)


def fingerprint(video_path: str) -> dict:
    """The stored record for one clip: 8 bytes per half-second of video, plus a
    sha256. Small enough to keep after the video itself is deleted, which is
    what makes takedowns stay down (see api.py's takedown endpoint)."""
    frames = _decode_thumbnails(video_path)
    bits = _phash_bits(frames)
    sha = hashlib.sha256()
    with open(video_path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            sha.update(chunk)
    return {
        "fp_version": FP_VERSION,
        "sha256": sha.hexdigest(),
        "n_frames": int(len(frames)),
        "duration_s": round(len(frames) / SAMPLE_FPS, 3),
        "self_spread": round(_self_spread(bits), 4),
        "phash": _pack(bits),
    }


def _pair_distances(a: dict, b: dict) -> Optional[tuple[float, float]]:
    """(mean, p95) normalised Hamming over aligned frames, or None if the pair
    never reaches the distance test.

    No time-shift search. It was considered and left out: sliding the sequences
    buys back a trimmed-start case we have not seen, and every extra offset
    tried is another chance for two different dances to line up — which is the
    failure direction that matters.
    """
    if a.get("fp_version") != b.get("fp_version"):
        return None
    if abs(a["duration_s"] - b["duration_s"]) > DURATION_TOLERANCE_S:
        return None
    if min(a.get("self_spread", 0.0), b.get("self_spread", 0.0)) < MIN_SELF_SPREAD:
        return None
    ba, bb = _unpack(a["phash"]), _unpack(b["phash"])
    n = min(len(ba), len(bb))
    if n == 0:
        return None
    per_frame = (ba[:n] != bb[:n]).mean(axis=1)
    return float(per_frame.mean()), float(np.quantile(per_frame, 0.95))


def is_duplicate(a: dict, b: dict) -> bool:
    """True only when this is the same recording of the same dance.

    Byte-identical is decided first and separately: it needs no tolerance at
    all, and it is the common case (the same file uploaded twice).
    """
    if a["sha256"] == b["sha256"]:
        return True
    d = _pair_distances(a, b)
    if d is None:
        return False
    mean, p95 = d
    return mean <= MAX_MEAN_DISTANCE and p95 <= MAX_P95_DISTANCE


def find_duplicate(candidate: dict, known: dict) -> Optional[str]:
    """First id in `known` ({id: fingerprint record}) that `candidate` duplicates.

    ponytail: linear scan. At the invite-only cohort's scale (hundreds of
    clips) that is one Dict read and a few thousand numpy comparisons. If the
    index ever reaches five figures, band the phash into LSH buckets and look
    up instead of scanning — the record already stores everything that needs.
    """
    for clip_id, record in known.items():
        if is_duplicate(candidate, record):
            return clip_id
    return None


def _self_check() -> None:
    """Synthetic, so CI can run it with no clips. The real measurement against
    solo-01/02/07/group-synced-01 lives in docs/research/dedupe-measurements.md."""
    rng = np.random.default_rng(0)

    def rec(frames, sha):
        bits = _phash_bits(frames)
        return {"fp_version": FP_VERSION, "sha256": sha, "n_frames": len(frames),
                "duration_s": round(len(frames) / SAMPLE_FPS, 3),
                "self_spread": round(_self_spread(bits), 4), "phash": _pack(bits)}

    base = rng.integers(0, 255, size=(40, THUMB, THUMB), dtype=np.uint8)
    a = rec(base, "a")
    assert a["self_spread"] > MIN_SELF_SPREAD, "random frames must be discriminable"

    noisy = np.clip(base.astype(int) + rng.integers(-8, 9, base.shape), 0, 255).astype(np.uint8)
    assert is_duplicate(a, rec(noisy, "b")), "re-encode-like noise must still match"
    assert is_duplicate(a, rec(rng.integers(0, 255, base.shape, dtype=np.uint8), "a")), \
        "identical bytes must short-circuit to a match"
    assert not is_duplicate(a, rec(rng.integers(0, 255, base.shape, dtype=np.uint8), "c")), \
        "unrelated content must not match"

    half = rec(base[:20], "d")
    assert _pair_distances(a, half) is None and not is_duplicate(a, half), \
        "a clip half the length is not comparable"

    # A clip whose frames barely differ must be refused even against itself-ish.
    flat = np.repeat(base[:1], 40, axis=0)
    flat_noisy = np.clip(flat.astype(int) + rng.integers(-2, 3, flat.shape), 0, 255).astype(np.uint8)
    dull, dull2 = rec(flat, "e"), rec(flat_noisy, "f")
    assert dull["self_spread"] < MIN_SELF_SPREAD
    assert not is_duplicate(dull, dull2), "a clip with no self-spread must never dedupe"

    assert find_duplicate(a, {"x": rec(noisy, "b")}) == "x"
    assert find_duplicate(a, {"x": dull}) is None
    print("fingerprint self-check ok")


if __name__ == "__main__":
    _self_check()
