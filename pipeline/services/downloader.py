"""yt-dlp wrapper with URL validation and video duration checks."""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

from pipeline.utils.url_normalizer import (
    extract_video_id,
    is_tiktok_shortlink,
    url_hash,
    InvalidURLError,
    UnsupportedPlatformError,
)


class VideoTooLongError(Exception):
    """Raised when video exceeds the 2-minute limit."""


class DownloadError(Exception):
    """Raised when yt-dlp fails to download the video."""


class VideoInfo:
    """Metadata about a downloaded video."""

    def __init__(
        self,
        video_path: Path,
        audio_path: Path,
        duration_seconds: float,
        fps: float,
        total_frames: int,
        video_id: str,
        platform: str,
        source_url: str,
        hash: str,
        direct_video_url: str | None = None,
    ):
        self.video_path = video_path
        self.audio_path = audio_path
        self.duration_seconds = duration_seconds
        self.fps = fps
        self.total_frames = total_frames
        self.video_id = video_id
        self.platform = platform
        self.source_url = source_url
        self.hash = hash
        self.direct_video_url = direct_video_url


MAX_DURATION_SECONDS = 120


async def resolve_tiktok_shortlink(url: str) -> str:
    """Resolve vm.tiktok.com redirect to get the canonical URL."""
    import httpx

    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.head(url)
        return str(resp.url)


async def download_video(url: str, output_dir: str | None = None) -> VideoInfo:
    """Download video from URL using yt-dlp.

    Args:
        url: Video URL (YouTube, TikTok, Instagram).
        output_dir: Directory for downloaded files. Uses tempdir if None.

    Returns:
        VideoInfo with paths to video and audio files, plus metadata.

    Raises:
        InvalidURLError: If URL cannot be parsed.
        UnsupportedPlatformError: If platform is not supported.
        VideoTooLongError: If video exceeds 2 minutes.
        DownloadError: If download fails.
    """
    # Resolve TikTok short links first
    if is_tiktok_shortlink(url):
        url = await resolve_tiktok_shortlink(url)

    platform, video_id = extract_video_id(url)
    computed_hash = url_hash(url)

    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="stepwise_")

    video_path = os.path.join(output_dir, "video.mp4")
    audio_path = os.path.join(output_dir, "audio.wav")

    # First, probe duration, fps, and direct video URL without downloading
    probe_cmd = [
        "yt-dlp",
        "--no-download",
        "--print", "duration",
        "--print", "fps",
        "--print", "url",
        "--no-check-certificates",
        "--socket-timeout", "15",
        "--no-warnings",
        url,
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *probe_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
    except asyncio.TimeoutError:
        proc.kill()
        raise DownloadError("Video probe timed out — TikTok may be blocking this request. Try again.")

    if proc.returncode != 0:
        raise DownloadError(f"Failed to probe video: {stderr.decode()[:200]}")

    lines = stdout.decode().strip().split("\n")
    try:
        duration = float(lines[0]) if lines[0] and lines[0] != "NA" else 0.0
        fps = float(lines[1]) if len(lines) > 1 and lines[1] and lines[1] != "NA" else 30.0
        direct_video_url = lines[2].strip() if len(lines) > 2 and lines[2].strip().startswith("http") else None
    except (ValueError, IndexError):
        raise DownloadError(f"Failed to parse video metadata: {stdout.decode()}")

    if duration > MAX_DURATION_SECONDS:
        raise VideoTooLongError(
            f"Video is {duration:.1f}s, max allowed is {MAX_DURATION_SECONDS}s"
        )

    # Download video — use simpler format selection for TikTok compatibility
    # TikTok videos are single-stream (no separate video+audio merge needed)
    dl_cmd = [
        "yt-dlp",
        "-f", "best[ext=mp4]/best",
        "-o", video_path,
        "--no-check-certificates",
        "--socket-timeout", "30",
        "--retries", "3",
        "--no-warnings",
        url,
    ]

    proc = await asyncio.create_subprocess_exec(
        *dl_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise DownloadError(f"Failed to download video: {stderr.decode()}")

    # Extract audio with ffmpeg
    audio_cmd = [
        "ffmpeg", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le", "-ar", "22050", "-ac", "1",
        audio_path, "-y",
    ]

    proc = await asyncio.create_subprocess_exec(
        *audio_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()

    total_frames = max(1, int(duration * fps))

    return VideoInfo(
        video_path=Path(video_path),
        audio_path=Path(audio_path),
        duration_seconds=duration,
        fps=fps,
        total_frames=total_frames,
        video_id=video_id,
        platform=platform,
        source_url=url,
        hash=computed_hash,
        direct_video_url=direct_video_url,
    )
