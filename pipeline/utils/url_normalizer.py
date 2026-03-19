"""URL canonicalization per platform (TikTok, YouTube, Instagram)."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import urlparse, parse_qs

import httpx


class UnsupportedPlatformError(Exception):
    """Raised when the URL is from an unsupported platform."""


class InvalidURLError(Exception):
    """Raised when the URL cannot be parsed."""


# Patterns for extracting video IDs
_YOUTUBE_ID_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?.*v=|shorts/|embed/)|youtu\.be/)"
    r"([a-zA-Z0-9_-]{11})"
)

_TIKTOK_ID_RE = re.compile(
    r"tiktok\.com/(?:@[\w.]+/video/|v/)(\d+)"
)

_INSTAGRAM_ID_RE = re.compile(
    r"instagram\.com/(?:reel|p)/([a-zA-Z0-9_-]+)"
)


def _strip_www(host: str) -> str:
    if host.startswith("www."):
        return host[4:]
    return host


def _extract_youtube_id(url: str) -> str | None:
    """Extract YouTube video ID from various URL formats."""
    parsed = urlparse(url)
    host = _strip_www(parsed.hostname or "")

    if host in ("youtube.com", "youtu.be"):
        # Handle youtube.com/watch?v=ID
        if host == "youtube.com" and parsed.path == "/watch":
            qs = parse_qs(parsed.query)
            v = qs.get("v")
            if v and len(v[0]) == 11:
                return v[0]

        # Handle youtu.be/ID, youtube.com/shorts/ID, youtube.com/embed/ID
        m = _YOUTUBE_ID_RE.search(url)
        if m:
            return m.group(1)

    return None


def _extract_tiktok_id(url: str) -> str | None:
    """Extract TikTok video ID."""
    parsed = urlparse(url)
    host = _strip_www(parsed.hostname or "")

    # vm.tiktok.com short links need redirect resolution (handled externally)
    # but if we see a resolved URL with the ID, extract it
    if "tiktok.com" in host:
        m = _TIKTOK_ID_RE.search(url)
        if m:
            return m.group(1)
    return None


def _extract_instagram_id(url: str) -> str | None:
    """Extract Instagram reel/post ID."""
    parsed = urlparse(url)
    host = _strip_www(parsed.hostname or "")

    if "instagram.com" in host:
        m = _INSTAGRAM_ID_RE.search(url)
        if m:
            return m.group(1)
    return None


def is_tiktok_shortlink(url: str) -> bool:
    """Check if URL is a TikTok short link that needs redirect resolution.

    Covers: vm.tiktok.com/*, tiktok.com/t/*, www.tiktok.com/t/*
    """
    parsed = urlparse(url)
    host = _strip_www(parsed.hostname or "")
    if host == "vm.tiktok.com":
        return True
    if host == "tiktok.com" and parsed.path.startswith("/t/"):
        return True
    return False


async def resolve_shortlink(url: str) -> str:
    """Follow redirects on a short link to get the final URL."""
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
            resp = await client.head(url)
            return str(resp.url)
    except Exception as e:
        raise InvalidURLError(f"Failed to resolve short link: {url}") from e


def extract_video_id(url: str) -> tuple[str, str]:
    """Extract canonical video ID and platform from URL.

    Returns:
        Tuple of (platform, video_id).

    Raises:
        InvalidURLError: If the URL cannot be parsed.
        UnsupportedPlatformError: If the platform is not supported.
    """
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.hostname:
            raise InvalidURLError(f"Cannot parse URL: {url}")
    except Exception as e:
        raise InvalidURLError(f"Cannot parse URL: {url}") from e

    yt_id = _extract_youtube_id(url)
    if yt_id:
        return ("youtube", yt_id)

    tt_id = _extract_tiktok_id(url)
    if tt_id:
        return ("tiktok", tt_id)

    ig_id = _extract_instagram_id(url)
    if ig_id:
        return ("instagram", ig_id)

    # If it's a TikTok short link, we can't extract the ID without resolving
    # the redirect. Return a special marker so the caller knows to resolve first.
    if is_tiktok_shortlink(url):
        raise UnsupportedPlatformError(
            f"SHORTLINK:{url}"
        )

    raise UnsupportedPlatformError(
        f"Unsupported platform: {parsed.hostname}"
    )


def canonical_url(platform: str, video_id: str) -> str:
    """Build canonical URL from platform and video ID."""
    if platform == "youtube":
        return f"https://youtube.com/watch?v={video_id}"
    elif platform == "tiktok":
        return f"https://tiktok.com/v/{video_id}"
    elif platform == "instagram":
        return f"https://instagram.com/reel/{video_id}"
    raise UnsupportedPlatformError(f"Unknown platform: {platform}")


def url_hash(url: str) -> str:
    """Compute SHA-256 hash of the canonical URL form.

    This is used as the R2 cache key.
    """
    platform, video_id = extract_video_id(url)
    canon = canonical_url(platform, video_id)
    return hashlib.sha256(canon.encode()).hexdigest()
