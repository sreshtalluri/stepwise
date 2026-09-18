import numpy as np
import soundfile as sf

from beat_detect.propose import propose_grid


def _write_click_track(path, bpm: float, duration_s: float, sr: int = 22050) -> None:
    """Synthesized public-domain test signal: a metronome click track.
    No copyrighted audio needed to sanity-check the beat tracker."""
    spc = 60.0 / bpm
    n_samples = int(duration_s * sr)
    y = np.zeros(n_samples, dtype=np.float32)
    t = 0.0
    click = np.sin(2 * np.pi * 1000 * np.arange(int(0.02 * sr)) / sr).astype(np.float32)
    while t < duration_s:
        i = int(t * sr)
        end = min(i + len(click), n_samples)
        y[i:end] += click[: end - i]
        t += spc
    sf.write(str(path), y, sr)


def test_propose_grid_on_synthesized_click_track(tmp_path):
    bpm = 120.0
    duration_s = 20.0
    wav_path = tmp_path / "click.wav"
    _write_click_track(wav_path, bpm=bpm, duration_s=duration_s)

    result = propose_grid(wav_path, clip_duration_s=duration_s)

    # A clean, perfectly regular click track is the easiest possible case:
    # expect a confident, accurate proposal.
    assert abs(result.bpm - bpm) < 3 or abs(result.bpm - bpm / 2) < 3 or abs(result.bpm - bpm * 2) < 3
    assert result.confidence > 0.7
    assert result.count_total is not None
    assert result.count_total > 1
    grid = result.to_grid()
    assert set(grid.keys()) == {"countOneS", "secondsPerCount", "countTotal"}


def test_to_grid_requires_clip_duration(tmp_path):
    wav_path = tmp_path / "click.wav"
    _write_click_track(wav_path, bpm=100.0, duration_s=10.0)
    result = propose_grid(wav_path)  # no clip_duration_s
    assert result.count_total is None
    try:
        result.to_grid()
        assert False, "expected ValueError"
    except ValueError:
        pass
