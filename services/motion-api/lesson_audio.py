"""A lesson's song as its own small file: plain AAC-LC in an .m4a.

Why it exists (measured 2026-11-12, on a TikTok lesson whose audio is HE-AACv2
with an edit list skipping 7106 samples of encoder delay):

* The lesson page plays the music through Web Audio, from `decodeAudioData`,
  and browsers do not agree where HE-AAC starts. Each decode of that mp4
  against ffmpeg's (which is the `<video>` timeline):

      Chromium decodeAudioData               0.0 ms
      WebKit 27.2 decodeAudioData (macOS)  -117.6 ms  (the music 118 ms EARLY)
      afconvert (AudioToolbox)              +43.5 ms

  WebKit skips the edit list's delay and then Apple's own 5186 samples. The
  click and the counts are on the video's timeline, so in Safari they sounded
  late against the music. The same audio as AAC-LC: 0.0 ms in WebKit, in
  Chromium and in afconvert. Not measured on iOS itself; on the owner's iPhone
  the click was late, and shifting the music 44 ms earlier made it worse.
* The page fetched the whole video a second time just for its audio (7.4 MB
  for that lesson). This file is 0.9 MB, so the audio clock is ready that much
  sooner on a phone.

ffmpeg is imageio-ffmpeg's pinned 7.x build, never the system one: Debian
bookworm's 5.1 double-trims HE-AAC priming (see beat_detect/propose.py), which
would bake a different offset in.
"""
from __future__ import annotations

import os
import subprocess
import tempfile

BITRATE = "160k"


def extract(video_path: str) -> str | None:
    """The clip's first audio track as AAC-LC in a temp .m4a the caller deletes.
    None when there is nothing to make it from (no audio track, a file ffmpeg
    cannot read, no ffmpeg): the lesson then plays the video's own sound, as
    every lesson did before."""
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:  # noqa: BLE001
        print(f"[audio] no ffmpeg ({type(e).__name__}: {e})")
        return None
    fd, out = tempfile.mkstemp(suffix=".m4a")
    os.close(fd)
    try:
        done = subprocess.run(
            [exe, "-y", "-v", "error", "-i", video_path, "-vn", "-map", "0:a:0",
             "-c:a", "aac", "-b:a", BITRATE, "-movflags", "+faststart", out],
            capture_output=True, timeout=120)
        if done.returncode == 0 and os.path.getsize(out) > 0:
            return out
        print(f"[audio] not extracted: {done.stderr.decode(errors='replace').strip()[-200:]}")
    except Exception as e:  # noqa: BLE001
        print(f"[audio] not extracted ({type(e).__name__}: {e})")
    os.unlink(out)
    return None
