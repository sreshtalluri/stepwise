from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from mesh_api.adapters.base import VideoProbe
from mesh_api.models import LicenseFlag, ModelDescriptor


class VideoIngestError(RuntimeError):
    pass


class YtDlpFfmpegVideoIngestor:
    """Production-oriented scaffold for URL/download and local-video probing.

    This adapter is intentionally not the default in tests because it depends on
    external binaries and network/storage configuration. It defines the seam the
    real GPU worker should use: social/direct URL or local/upload ref in, probed
    metadata and normalized local reference out.
    """

    descriptor = ModelDescriptor(name="yt-dlp + ffprobe video ingestor", version="0.1.0", adapter="yt-dlp-ffprobe")
    license_flags = [
        LicenseFlag(
            component="yt-dlp",
            license="Unlicense/public-domain-style project license",
            commercial_use="unknown",
            note="Check platform terms of service for YouTube/TikTok/Instagram download use before production.",
        ),
        LicenseFlag(
            component="ffmpeg/ffprobe",
            license="LGPL/GPL build dependent",
            commercial_use="unknown",
            note="Confirm the deployed FFmpeg build license and enabled codecs.",
        ),
    ]

    def __init__(self, work_dir: str | Path = "/tmp/stepwise-ingest") -> None:
        self.work_dir = Path(work_dir)

    def probe(self, source_ref: str) -> VideoProbe:
        local_path = self._resolve_local_video(source_ref)
        metadata = self._ffprobe(local_path)
        return VideoProbe(
            source_url=source_ref,
            playback_url=local_path.as_uri() if local_path.is_absolute() else str(local_path),
            duration_seconds=metadata["duration_seconds"],
            fps=metadata["fps"],
            width=metadata["width"],
            height=metadata["height"],
            local_ref=str(local_path),
        )

    def _resolve_local_video(self, source_ref: str) -> Path:
        if source_ref.startswith("upload://"):
            # In production this should resolve the upload ref to object storage or
            # a worker-local path. The mock API keeps upload bytes in-memory, so a
            # production deployment must replace this branch.
            raise VideoIngestError("upload:// refs must be resolved by storage before using YtDlpFfmpegVideoIngestor")
        path = Path(source_ref)
        if path.exists():
            return path.resolve()
        if source_ref.startswith("http://") or source_ref.startswith("https://"):
            return self._download_url(source_ref)
        raise VideoIngestError(f"Unsupported video source: {source_ref}")

    def _download_url(self, source_url: str) -> Path:
        if shutil.which("yt-dlp") is None:
            raise VideoIngestError("yt-dlp is not installed in the worker image")
        self.work_dir.mkdir(parents=True, exist_ok=True)
        output_template = str(self.work_dir / "%(id)s.%(ext)s")
        subprocess.run(
            ["yt-dlp", "--no-playlist", "--merge-output-format", "mp4", "-o", output_template, source_url],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        candidates = sorted(self.work_dir.glob("*.mp4"), key=lambda item: item.stat().st_mtime, reverse=True)
        if not candidates:
            raise VideoIngestError("yt-dlp completed but no mp4 output was found")
        return candidates[0].resolve()

    def _ffprobe(self, path: Path) -> dict:
        if shutil.which("ffprobe") is None:
            raise VideoIngestError("ffprobe is not installed in the worker image")
        completed = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height,r_frame_rate:format=duration",
                "-of",
                "json",
                str(path),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        data = json.loads(completed.stdout)
        stream = data["streams"][0]
        numerator, denominator = (int(part) for part in stream.get("r_frame_rate", "30/1").split("/"))
        fps = numerator / denominator if denominator else 30.0
        return {
            "duration_seconds": float(data["format"]["duration"]),
            "fps": fps,
            "width": int(stream["width"]),
            "height": int(stream["height"]),
        }
