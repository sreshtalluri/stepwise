"""lesson_audio.extract and modal_app.publish_lesson_audio.

    cd services/motion-api && python -m pytest test_lesson_audio.py -q

What cannot be tested here is the reason the file exists: Apple's decoder
placing HE-AAC 43.5 ms late (lesson_audio.py). No free encoder makes HE-AAC and
CI has no Apple decoder. What is tested is what must stay true for the fix to
hold: the output is AAC-LC, and its sound sits where the source's did.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import lesson_audio  # noqa: E402
import storage  # noqa: E402

pytest.importorskip("imageio_ffmpeg", reason="lesson_audio needs imageio-ffmpeg's pinned ffmpeg")
pytestmark = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
                                reason="needs ffmpeg + ffprobe to build and read the sample clips")

SR = 44100


def _clip(path, audio=True):
    """2 s of test picture; with `audio`, silence then a tone from 0.5 s on, as MP3."""
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=64x64:rate=10:duration=2"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"aevalsrc='0.5*sin(2*PI*880*t)*gte(t,0.5)':d=2:s={SR}", "-c:a", "libmp3lame"]
    subprocess.run(cmd + ["-c:v", "mpeg4", str(path)], check=True)
    return str(path)


def _tone_starts_at(path) -> float:
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return float(np.argmax(np.abs(np.frombuffer(raw, dtype=np.float32)) > 0.1)) / SR


def test_the_audio_comes_out_as_aac_lc_with_its_sound_where_it_was(tmp_path):
    src = _clip(tmp_path / "clip.mp4")
    out = lesson_audio.extract(src)
    try:
        probe = json.loads(subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,profile", "-of", "json", out],
            capture_output=True, check=True).stdout)["streams"]
        assert [(s["codec_type"], s["codec_name"], s["profile"]) for s in probe] == [("audio", "aac", "LC")]
        assert abs(_tone_starts_at(out) - _tone_starts_at(src)) < 0.003
        assert os.path.getsize(out) < os.path.getsize(src)
    finally:
        os.unlink(out)


def test_nothing_to_extract_is_none_not_an_error(tmp_path):
    assert lesson_audio.extract(_clip(tmp_path / "silent.mp4", audio=False)) is None
    junk = tmp_path / "junk.mp4"
    junk.write_bytes(b"not a video")
    assert lesson_audio.extract(str(junk)) is None
    assert lesson_audio.extract(str(tmp_path / "missing.mp4")) is None


def test_the_audio_has_its_own_asset_id_and_goes_with_the_lesson_on_removal():
    storage._self_check()


@pytest.fixture
def publish(monkeypatch, tmp_path):
    import modal_app
    import retention
    puts, made = [], []

    def extract(video_path):
        p = tmp_path / f"{len(made)}.m4a"
        p.write_bytes(b"aac")
        made.append(p)
        return str(p)

    monkeypatch.setattr(lesson_audio, "extract", extract)
    monkeypatch.setattr(storage, "enabled", lambda: True)
    monkeypatch.setattr(storage, "put_file", lambda key, path, content_type, **k: puts.append((key, content_type)) or key)
    monkeypatch.setattr(retention, "ensure_not_removed", lambda vol, clip_id, reload=False: None)
    return modal_app.publish_lesson_audio, puts, made, monkeypatch, retention


def test_publish_puts_one_object_and_leaves_no_temp_file(publish):
    run, puts, made, _, _ = publish
    assert run("abc", "/x/abc.mp4") == "video/abc.audio.m4a"
    assert puts == [("video/abc.audio.m4a", "audio/mp4")]
    assert not made[0].exists()


def test_a_storage_failure_costs_the_audio_file_and_nothing_else(publish):
    run, puts, made, monkeypatch, _ = publish

    def boom(*a, **k):
        raise RuntimeError("r2 blip")

    monkeypatch.setattr(storage, "put_file", boom)
    assert run("abc", "/x/abc.mp4") is None
    assert not made[0].exists()


def test_a_removed_lesson_gets_no_audio_published(publish):
    run, puts, made, monkeypatch, retention = publish

    def removed(vol, clip_id, reload=False):
        raise retention.Removed(clip_id)

    monkeypatch.setattr(retention, "ensure_not_removed", removed)
    with pytest.raises(retention.Removed):
        run("abc", "/x/abc.mp4")
    assert puts == [] and not made[0].exists()
