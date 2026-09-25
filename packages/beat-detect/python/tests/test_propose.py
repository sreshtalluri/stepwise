"""Unit tests run on recorded or synthesized beat-tracker output (the
`fake_model` fixture), so they need neither torch nor the 81 MB checkpoint.
`test_real_model_*` runs Beat This! itself and skips unless the model and its
cached weights are present."""
import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from beat_detect import propose
from beat_detect.propose import propose_grid

SR = 22050
FIXTURES = Path(__file__).parent / "fixtures"
RECORDED = json.loads((FIXTURES / "beat-this-recorded.json").read_text())


@pytest.fixture
def fake_model(monkeypatch):
    """Stand in for Beat This!: `fake_model(beats, downbeats)`."""
    def use(beats, downbeats):
        monkeypatch.setattr(propose, "_track_beats",
                            lambda y, sr: (np.asarray(beats, float), np.asarray(downbeats, float)))
    return use


def _render(path, duration_s, hats=(), kicks=(), claps=()):
    """Synthesized public-domain audio: a 55 Hz kick, a hi-hat (high-passed
    noise) and a louder broadband clap at the given times."""
    y = np.zeros(int(duration_s * SR), dtype=np.float32)
    n = np.arange(int(0.12 * SR))
    kick = (np.sin(2 * np.pi * 55 * n / SR) * np.exp(-n / (0.03 * SR))).astype(np.float32)
    noise = np.random.default_rng(0).standard_normal(int(0.03 * SR)).astype(np.float32)
    hat = np.diff(noise[: int(0.02 * SR)] * 0.3, prepend=0).astype(np.float32)
    for times, sound in ((hats, hat), (kicks, kick), (claps, noise * 1.5)):
        for t in times:
            i = int(t * SR)
            y[i:i + len(sound)] += sound[: max(0, len(y) - i)]
    sf.write(str(path), y, SR)
    return path


def test_propose_grid_on_synthesized_click_track(tmp_path, fake_model):
    bpm, duration_s = 120.0, 20.0
    clicks = np.arange(0, duration_s, 60 / bpm)
    fake_model(clicks, clicks[::4])
    wav = _render(tmp_path / "click.wav", duration_s, hats=clicks)

    result = propose_grid(wav, clip_duration_s=duration_s)

    assert abs(result.bpm - bpm) < 0.01
    assert result.confidence > 0.9
    assert result.count_total in (40, 41)  # 20 s / 0.5 s, float rounding
    assert set(result.to_grid()) == {"countOneS", "secondsPerCount", "countTotal"}


def test_to_grid_requires_clip_duration(tmp_path, fake_model):
    clicks = np.arange(0, 10, 0.6)
    fake_model(clicks, clicks[::4])
    result = propose_grid(_render(tmp_path / "click.wav", 10.0, hats=clicks))  # no clip_duration_s
    assert result.count_total is None
    with pytest.raises(ValueError):
        result.to_grid()


def _solo02_shape():
    """solo-02: 115.07 BPM, three pickup beats, then a kick on every
    downbeat. The owner's count 1 is the first kick (1.905 s on the real clip)."""
    bpm, first_beat, duration_s = 115.07, 0.34, 32.0
    beats = first_beat + 60 / bpm * np.arange(int((duration_s - first_beat) * bpm / 60))
    return bpm, duration_s, beats


def test_solo02_shape_tempo_and_downbeat(tmp_path, fake_model):
    bpm, duration_s, beats = _solo02_shape()
    wav = _render(tmp_path / "solo02.wav", duration_s, hats=beats, kicks=beats[3::4])
    # Model output quantized to its 50 fps frames, like the real thing.
    fake_model(np.round(beats * 50) / 50, np.round(beats[3::4] * 50) / 50)

    result = propose_grid(wav, clip_duration_s=duration_s)

    true_one = beats[3]
    assert abs(result.bpm - bpm) < 0.1, result.bpm
    assert abs(result.count_one_s - true_one) < 0.03, result.count_one_s
    # "Try another 1": the three pickup beats before it, as whole-count shifts.
    assert sorted(a.shift_counts for a in result.count_one_alternates) == [-3, -2, -1]
    # No drift: count 57 (the last full eight) still lands on its beat.
    count_57 = result.count_one_s + 56 * result.seconds_per_count
    assert abs(count_57 - (true_one + 56 * 60 / bpm)) < 0.03, count_57
    assert result.warnings == []


def test_bhangra_grid_lands_on_the_beat_not_between(tmp_path, fake_model):
    """Regression, lesson job_5716ecd3 (bhangra, 94.8 BPM): the librosa grid
    locked onto the off-beat, where the dhol and claps carry more onset energy
    than the beat, so every count sat ~300 ms off (count 1 at 2.26 s). The
    audio here is synthesized the same way -- kicks on the bar downbeats,
    louder claps halfway between beats -- around Beat This!'s recorded beats
    for the real clip, whose bar downbeats all four models put on 2.57 + 2.52n."""
    rec = RECORDED["bhangra"]
    beats = np.array(rec["beats"])
    wav = _render(tmp_path / "bhangra.wav", 48.0, hats=beats, kicks=beats[3::4],
                  claps=(beats[:-1] + beats[1:]) / 2)
    fake_model(beats, rec["downbeats"])

    result = propose_grid(wav, clip_duration_s=47.7)

    assert abs(result.count_one_s - 2.58) < 0.07, result.count_one_s
    assert abs(result.count_one_s - rec["prod_count_one_s_before"]) > 0.25
    grid = result.count_one_s + result.seconds_per_count * np.arange(-3, result.count_total)
    assert np.abs(grid[:, None] - beats[None, :]).min(axis=1).max() < 0.05  # every count on a beat
    assert result.warnings == []


def test_solo07_drifting_tempo_and_skipped_beat_still_hits_the_label(tmp_path, fake_model):
    """solo-07 speeds up (~125 -> 129 BPM) and Beat This! skips the beat at
    ~0.98 s. The old fixed grid drifted and put count 1 at 1.358 s (label
    1.030 s); Beat This!'s own downbeats are half a bar off (0.02 s). Kicks on
    the labelled bar phase: the least-squares grid through the recorded beats
    plus the kick rule land on the label, and the model's pick is the first
    "try another 1"."""
    rec = RECORDED["solo-07"]
    beats = np.array(rec["beats"])
    _, _, idx = propose._fit_grid(beats)
    assert list(idx[:4]) == [0, 1, 3, 4]  # the skipped beat keeps its count
    wav = _render(tmp_path / "solo07.wav", 23.6, hats=beats, kicks=beats[idx % 4 == 2])
    fake_model(beats, rec["downbeats"])

    result = propose_grid(wav, clip_duration_s=23.58)

    assert abs(result.count_one_s - rec["label_count_one_s"]) < 0.07, result.count_one_s
    assert result.count_one_alternates[0].shift_counts == -2  # the model's downbeat, 0.02 s
    assert result.warnings == []


def test_weak_kick_margin_defers_to_the_model_downbeat(tmp_path, fake_model):
    """No kick at all: the kick rule has nothing to go on, so the model's
    majority downbeat decides, and the warning says count 1 is a weak guess."""
    beats = np.arange(0.3, 20, 0.5)
    fake_model(beats, beats[1::4])
    result = propose_grid(_render(tmp_path / "hats.wav", 20.0, hats=beats), clip_duration_s=20.0)
    assert abs(result.count_one_s - beats[1]) < 0.01
    assert any("weak guess" in w for w in result.warnings)


def test_real_model_on_synthesized_solo02_shape(tmp_path):
    """The one test that runs Beat This! itself. Skipped unless torch,
    beat-this and the cached final0 checkpoint are all present (CI caches it;
    the Modal image bakes it in)."""
    pytest.importorskip("beat_this")
    if not (Path.home() / ".cache/torch/hub/checkpoints/beat_this-final0.ckpt").exists():
        pytest.skip("final0 checkpoint not cached")
    bpm, duration_s, beats = _solo02_shape()
    wav = _render(tmp_path / "solo02.wav", duration_s, hats=beats, kicks=beats[3::4])

    result = propose_grid(wav, clip_duration_s=duration_s)

    assert abs(result.bpm - bpm) < 0.5, result.bpm
    assert abs(result.count_one_s - beats[3]) < 0.06, result.count_one_s


def test_extract_audio_trims_he_aac_priming_once():
    """The decoded track must be exactly as long as the container says.

    Fixture: a synthesized click, HE-AAC (the codec TikTok uses) in .mp4,
    encoded with macOS AudioToolbox (`-c:a aac_at -profile:a 4`), whose edit
    list trims 2112 priming samples and declares 137151 samples at 44.1 kHz.
    Debian bookworm's ffmpeg 5.1 trimmed the priming twice: 3.062 s here, and
    on solo-02 every beat came out 115 ms early (count 1 at 1.789 s instead
    of 1.905 s). imageio-ffmpeg's 7.x decodes 3.110 s."""
    out = propose._extract_audio(FIXTURES / "he-aac-click.mp4")
    try:
        z, zsr = sf.read(str(out))
    finally:
        out.unlink()
    assert abs(len(z) / zsr - 137151 / 44100) < 0.005, len(z) / zsr
