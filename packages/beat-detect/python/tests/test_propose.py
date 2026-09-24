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


def test_solo02_shape_tempo_and_downbeat(tmp_path):
    """The case the owner caught on solo-02: a track at 115.07 BPM whose first
    three beats are a pickup (bar beats 2-4) and whose first downbeat is at
    1.884 s (Beat This! puts it at 1.88). The old proposal read 117.45 BPM
    (librosa's nearest quantized tempo) with count 1 on the first heard beat,
    so the grid was a beat early and drifted half a beat off by count 25.
    Synthesized: a kick on every downbeat, a hi-hat on every beat."""
    sr, bpm, first_beat, duration_s = 22050, 115.07, 0.32, 32.0
    spc = 60.0 / bpm
    y = np.zeros(int(duration_s * sr), dtype=np.float32)
    n = np.arange(int(0.12 * sr))
    kick = (np.sin(2 * np.pi * 55 * n / sr) * np.exp(-n / (0.03 * sr))).astype(np.float32)
    hat = (np.random.default_rng(0).standard_normal(int(0.02 * sr)) * 0.3).astype(np.float32)
    hat = np.diff(hat, prepend=0).astype(np.float32)  # high-passed noise
    beats = first_beat + spc * np.arange(int((duration_s - first_beat) / spc))
    for k, t in enumerate(beats):
        i = int(t * sr)
        y[i:i + len(hat)] += hat[: len(y) - i]
        if k % 4 == 3:  # pickup of 3, then every 4th beat is a downbeat
            y[i:i + len(kick)] += kick[: len(y) - i]
    wav = tmp_path / "solo02-shape.wav"
    sf.write(str(wav), y, sr)

    result = propose_grid(wav, clip_duration_s=duration_s)

    true_one = beats[3]
    assert abs(result.bpm - bpm) < 0.5, result.bpm
    assert abs(result.count_one_s - true_one) < 0.04, result.count_one_s
    # No drift: count 57 (the last full eight) still lands on its beat.
    count_57 = result.count_one_s + 56 * result.seconds_per_count
    assert abs(count_57 - (true_one + 56 * spc)) < 0.06, count_57
    assert result.warnings == []
