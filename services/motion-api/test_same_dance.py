"""dance_shift_s on synthetic signatures: a trim is found with its shift, a
different or mirrored dance is not, and a short shared stretch does not link."""
import numpy as np

import fingerprint as fp


def _sig(n, seed):
    return np.random.default_rng(seed).integers(0, 256, (n, 8), dtype=np.uint8)


def _shift(a, b):
    return fp.dance_shift_s(a.tobytes(), b.tobytes())


def test_trim_found_with_shift():
    full = _sig(330, 1)
    piece = full[30:180].copy()  # starts 3 s in
    piece[::7] ^= 1  # a re-encode flips a few bits
    assert _shift(full, piece) == -3.0  # t in full = t in piece + 3
    assert _shift(piece, full) == 3.0
    assert _shift(full, full) == 0.0


def test_different_dances_do_not_link():
    assert _shift(_sig(300, 1), _sig(300, 2)) is None
    a = _sig(300, 3)
    mirrored = np.packbits(~np.unpackbits(a, axis=1).astype(bool), axis=1)
    assert _shift(a, mirrored) is None


def test_short_shared_stretch_does_not_link():
    a, b = _sig(300, 4), _sig(300, 5)
    b[:60] = a[240:]  # 6 s in common, a fifth of either
    assert _shift(a, b) is None
