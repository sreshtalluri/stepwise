"""Tests for URL normalization and video ID extraction."""

from __future__ import annotations

import pytest

from pipeline.utils.url_normalizer import (
    InvalidURLError,
    UnsupportedPlatformError,
    canonical_url,
    extract_video_id,
    is_tiktok_shortlink,
    url_hash,
)


class TestYouTubeExtraction:
    def test_standard_watch_url(self):
        platform, vid = extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert platform == "youtube"
        assert vid == "dQw4w9WgXcQ"

    def test_watch_url_without_www(self):
        platform, vid = extract_video_id("https://youtube.com/watch?v=dQw4w9WgXcQ")
        assert platform == "youtube"
        assert vid == "dQw4w9WgXcQ"

    def test_short_url(self):
        platform, vid = extract_video_id("https://youtu.be/dQw4w9WgXcQ")
        assert platform == "youtube"
        assert vid == "dQw4w9WgXcQ"

    def test_shorts_url(self):
        platform, vid = extract_video_id("https://youtube.com/shorts/dQw4w9WgXcQ")
        assert platform == "youtube"
        assert vid == "dQw4w9WgXcQ"

    def test_embed_url(self):
        platform, vid = extract_video_id("https://youtube.com/embed/dQw4w9WgXcQ")
        assert platform == "youtube"
        assert vid == "dQw4w9WgXcQ"

    def test_watch_with_extra_params(self):
        platform, vid = extract_video_id(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42&list=PLtest"
        )
        assert platform == "youtube"
        assert vid == "dQw4w9WgXcQ"


class TestTikTokExtraction:
    def test_standard_tiktok_url(self):
        platform, vid = extract_video_id(
            "https://www.tiktok.com/@user123/video/7234567890123456789"
        )
        assert platform == "tiktok"
        assert vid == "7234567890123456789"

    def test_tiktok_without_www(self):
        platform, vid = extract_video_id(
            "https://tiktok.com/@dancer/video/7234567890123456789"
        )
        assert platform == "tiktok"
        assert vid == "7234567890123456789"

    def test_is_tiktok_shortlink(self):
        assert is_tiktok_shortlink("https://vm.tiktok.com/ZMRabcdef/")
        assert not is_tiktok_shortlink("https://tiktok.com/@user/video/123")
        assert not is_tiktok_shortlink("https://youtube.com/watch?v=abc")


class TestInstagramExtraction:
    def test_reel_url(self):
        platform, vid = extract_video_id("https://www.instagram.com/reel/CxYz12345/")
        assert platform == "instagram"
        assert vid == "CxYz12345"

    def test_post_url(self):
        platform, vid = extract_video_id("https://instagram.com/p/CxYz12345/")
        assert platform == "instagram"
        assert vid == "CxYz12345"


class TestURLHash:
    def test_same_video_different_formats_same_hash(self):
        h1 = url_hash("https://youtube.com/watch?v=dQw4w9WgXcQ")
        h2 = url_hash("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        h3 = url_hash("https://youtu.be/dQw4w9WgXcQ")
        h4 = url_hash("https://youtube.com/shorts/dQw4w9WgXcQ")
        assert h1 == h2 == h3 == h4

    def test_different_videos_different_hashes(self):
        h1 = url_hash("https://youtube.com/watch?v=dQw4w9WgXcQ")
        h2 = url_hash("https://youtube.com/watch?v=xxxxxxxxxxx")
        assert h1 != h2

    def test_hash_is_sha256_hex(self):
        h = url_hash("https://youtube.com/watch?v=dQw4w9WgXcQ")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


class TestCanonicalURL:
    def test_youtube_canonical(self):
        assert canonical_url("youtube", "abc") == "https://youtube.com/watch?v=abc"

    def test_tiktok_canonical(self):
        assert canonical_url("tiktok", "123") == "https://tiktok.com/v/123"

    def test_instagram_canonical(self):
        assert canonical_url("instagram", "xyz") == "https://instagram.com/reel/xyz"


class TestErrors:
    def test_invalid_url(self):
        with pytest.raises(InvalidURLError):
            extract_video_id("not-a-url")

    def test_unsupported_platform(self):
        with pytest.raises(UnsupportedPlatformError):
            extract_video_id("https://vimeo.com/12345")
