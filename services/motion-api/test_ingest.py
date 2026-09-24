"""Checks for the two pieces of ingest.py that are easy to get quietly wrong:
URL normalisation and failure classification.

No network. The live end-to-end run against the builder's own clips.yaml URLs
is separate, and its measured numbers are in docs/research/link-ingestion.md §6.

    python services/motion-api/test_ingest.py
    pytest services/motion-api/test_ingest.py
"""
from __future__ import annotations

import ingest

# --- normalisation ----------------------------------------------------------
#
# The point of the key is that two learners pasting the same dance produce the
# same string with no network access. Every row below is a form a share sheet
# or an address bar actually produces.

SAME_YOUTUBE = [
    "https://www.youtube.com/watch?v=M7FIvfx5J10",
    "https://youtube.com/watch?v=M7FIvfx5J10",
    "https://m.youtube.com/watch?v=M7FIvfx5J10",
    "https://music.youtube.com/watch?v=M7FIvfx5J10",
    "https://youtu.be/M7FIvfx5J10",
    "https://youtu.be/M7FIvfx5J10?si=AbCdEfGhIjKlMnOp",       # share-sheet tracking
    "https://www.youtube.com/watch?v=M7FIvfx5J10&t=42s",       # timestamp
    "https://www.youtube.com/watch?app=desktop&v=M7FIvfx5J10",
    "https://www.youtube.com/shorts/M7FIvfx5J10",              # a Short is the same video
    "https://www.youtube.com/embed/M7FIvfx5J10",
    "https://www.youtube.com/live/M7FIvfx5J10",
    "youtube.com/watch?v=M7FIvfx5J10",                         # pasted without a scheme
    "  https://www.youtube.com/watch?v=M7FIvfx5J10  ",         # pasted with whitespace
]

SAME_TIKTOK = [
    "https://www.tiktok.com/@jonraydybuco/video/7672198121417444628",
    "https://www.tiktok.com/@jonraydybuco/video/7672198121417444628?is_from_webapp=1&sender_device=pc",
    "https://m.tiktok.com/v/7672198121417444628",
    "https://www.tiktok.com/@someone.else/video/7672198121417444628",  # handle is not identity
]

NOT_A_VIDEO_LINK = [
    "",
    "   ",
    "not a url at all",
    "https://example.com/not-a-video",
    "https://vimeo.com/123456789",
    "https://www.youtube.com/watch?v=tooshort",
    "https://www.youtube.com/@somechannel",          # a channel, not a video
    "https://www.youtube.com/feed/subscriptions",
    "https://www.tiktok.com/@jonraydybuco",          # a profile, not a video
    "ftp://www.youtube.com/watch?v=M7FIvfx5J10",
]


def test_youtube_forms_collapse_to_one_key():
    keys = {ingest.normalize(u).key for u in SAME_YOUTUBE}
    assert keys == {"youtube:M7FIvfx5J10"}, keys
    for u in SAME_YOUTUBE:
        link = ingest.normalize(u)
        assert link.resolved and link.platform == "youtube"
        # Everything is refetched from one canonical URL, so a tracking blob in
        # the pasted string never reaches the platform.
        assert link.fetch_url == "https://www.youtube.com/watch?v=M7FIvfx5J10"


def test_tiktok_long_forms_collapse_to_one_key():
    keys = {ingest.normalize(u).key for u in SAME_TIKTOK}
    assert keys == {"tiktok:7672198121417444628"}, keys
    assert all(ingest.normalize(u).resolved for u in SAME_TIKTOK)


def test_tiktok_short_links_are_keyed_but_not_claimed_resolved():
    # A share link carries no video id, so it CANNOT be keyed canonically
    # without the network. It still dedupes for free against itself, which is
    # the common case: the same share link pasted by several learners.
    for url, code in [
        ("https://www.tiktok.com/t/ZP83Enx4b/", "ZP83Enx4b"),
        ("https://www.tiktok.com/t/ZP83Enx4b", "ZP83Enx4b"),
        ("https://www.tiktok.com/t/ZP83Enx4b/?_t=ZP-99pXAA0bS0M&_r=1", "ZP83Enx4b"),
        ("https://vm.tiktok.com/ZP83Enx4b/", "ZP83Enx4b"),
        ("https://vt.tiktok.com/ZP83Enx4b", "ZP83Enx4b"),
    ]:
        link = ingest.normalize(url)
        assert link is not None, url
        assert link.key == f"tiktok:short:{code}", (url, link.key)
        assert link.resolved is False, url


def test_non_video_links_are_refused_with_no_network():
    for url in NOT_A_VIDEO_LINK:
        assert ingest.normalize(url) is None, url


def test_canonical_key_trusts_the_extractor_not_the_host():
    # A short code that redirects somewhere unexpected must not be keyed as a
    # TikTok video just because the pasted host said tiktok.com.
    assert ingest.canonical_key("tiktok", {
        "id": "7672198121417444628", "extractor_key": "TikTok"}) == "tiktok:7672198121417444628"
    assert ingest.canonical_key("youtube", {
        "id": "M7FIvfx5J10", "extractor_key": "youtube"}) == "youtube:M7FIvfx5J10"
    assert ingest.canonical_key("tiktok", {"id": "x", "extractor_key": "generic"}) is None
    assert ingest.canonical_key("tiktok", {"extractor_key": "TikTok"}) is None


# --- failure classification -------------------------------------------------
#
# Every string on the left is either a message yt-dlp actually printed (marked
# OBSERVED, with the date) or a message quoted from yt-dlp's own extractor
# source. DESIGN.md §7h: never report a reason that was not observed.

OBSERVED = [
    # OBSERVED 2026-09-20, youtube.com/watch?v=aaaaaaaaaaa
    ("ERROR: [youtube] aaaaaaaaaaa: This video is unavailable",
     "video_unavailable", False),
    # OBSERVED 2026-09-20, tiktok.com/@nonexistentuser999/video/1111111111111111111.
    # TikTok says this for a post that does not exist, so mapping it to
    # "deleted" would be inventing a reason. It reports what was observed:
    # the platform would not serve it.
    ("ERROR: [TikTok] 1111111111111111111: Your IP address is blocked from accessing this post",
     "fetch_refused", True),
    # OBSERVED 2026-09-20, example.com/not-a-video (reaches the generic extractor)
    ("ERROR: [generic] not-a-video: Unable to download webpage: HTTP Error 404: Not Found",
     "fetch_failed", True),
]

QUOTED_FROM_YTDLP = [
    ("ERROR: [youtube] xxx: Video unavailable. The uploader has not made this video "
     "available in your country", "video_region_locked", False),
    ("ERROR: [youtube] xxx: Sign in to confirm your age. This video may be inappropriate "
     "for some users.", "video_login_required", False),
    ("ERROR: [youtube] xxx: Sign in to confirm you're not a bot. Use --cookies-from-browser",
     "video_login_required", False),
    ("ERROR: [youtube] xxx: Private video. Sign in if you've been granted access to this video",
     "video_private", False),
    ("ERROR: [youtube] xxx: This video has been removed by the uploader",
     "video_unavailable", False),
    ("ERROR: [youtube] xxx: This live event will begin in 3 hours", "video_is_live", True),
    ("ERROR: unable to download video data: HTTP Error 429: Too Many Requests",
     "fetch_rate_limited", True),
    ("ERROR: [TikTok] xxx: Unable to download webpage: HTTP Error 403: Forbidden",
     "fetch_refused", True),
]


def test_classification_matches_what_was_observed():
    for stderr, code, retryable in OBSERVED + QUOTED_FROM_YTDLP:
        got_code, message, got_retryable = ingest.classify(stderr)
        assert got_code == code, (stderr, got_code, code)
        assert got_retryable is retryable, (stderr, got_retryable, retryable)
        assert message and message[0].isupper() and message.endswith(".")
        # DESIGN.md §11: errors say what happened and what to do, never apologise.
        assert not any(w in message.lower() for w in ("sorry", "apolog", "oops")), message
        assert "!" not in message


def test_an_opaque_failure_claims_no_reason():
    # The rule that matters most. An unrecognised yt-dlp failure must say the
    # fetch did not go through and nothing more.
    for stderr in ["", "ERROR: something nobody has seen before", "Traceback (most recent call last)"]:
        code, message, retryable = ingest.classify(stderr)
        assert code == "fetch_failed", stderr
        assert retryable is True, stderr
        # It must not name a cause it did not see.
        lowered = message.lower()
        for invented in ("private", "deleted", "removed", "region", "country",
                         "age", "live", "rate", "blocked"):
            assert invented not in lowered, (stderr, message)


def test_region_and_age_beat_the_generic_unavailable_match():
    # Both real YouTube messages start with "Video unavailable", so rule order
    # is load-bearing -- a plain "unavailable" mapping would swallow them and
    # tell a learner in the wrong country that the video was deleted.
    assert ingest.classify(
        "Video unavailable. This video is not available in your country"
    )[0] == "video_region_locked"
    assert ingest.classify(
        "Video unavailable. Sign in to confirm your age"
    )[0] == "video_login_required"


def test_retryable_follows_the_schema_definition():
    # "Could re-submitting the same clip plausibly succeed?" -- not "is this
    # our fault". A region lock never changes by asking again; a rate limit does.
    never = {"video_region_locked", "video_private", "video_unavailable", "clip_too_long"}
    for _, outcome in ingest._RULES:
        code, _, retryable = outcome
        if code in never:
            assert retryable is False, code
    assert ingest.too_long_error(612.0)[2] is False
    assert "612 seconds" in ingest.too_long_error(612.0)[1]
    assert "60" in ingest.too_long_error(612.0)[1]


def test_every_produced_code_is_a_known_fetch_stage_code():
    # api.py's retry endpoint branches on this set; a code that escapes it
    # would re-spawn a GPU container looking for a file that was never fetched.
    produced = {outcome[0] for _, outcome in ingest._RULES}
    produced |= {ingest.classify("")[0], ingest.too_long_error(61.0)[0]}
    assert produced <= ingest.FETCH_STAGE_CODES, produced - ingest.FETCH_STAGE_CODES


# --- the pre-download refusal ----------------------------------------------
#
# The whole point of this gate: it decides on the probe document alone, so a
# ten-minute video is refused without a byte of media being fetched.

def test_duration_gate():
    ok = {"duration": 19.7, "live_status": "not_live"}
    ingest.check_duration(ok)  # returns, does not raise

    for probed, code in [
        ({"duration": 77.0}, "clip_too_long"),
        ({"duration": 612}, "clip_too_long"),
        ({"is_live": True, "duration": 10}, "video_is_live"),
        ({"live_status": "is_upcoming", "duration": None}, "video_is_live"),
    ]:
        try:
            ingest.check_duration(probed)
        except ingest.FetchError as e:
            assert e.code == code, (probed, e.code)
            assert e.as_job_error()["retryable"] is (code != "clip_too_long")
        else:
            raise AssertionError(f"{probed} should have been refused")

    # A missing duration is NOT a refusal: some extractors do not report one,
    # and refusing on an absent number rejects working clips for a fact nobody
    # observed. MAX_FETCH_BYTES is the backstop for that case.
    ingest.check_duration({"duration": None, "live_status": "not_live"})
    ingest.check_duration({})
    ingest.check_duration({"duration": 60.0})  # exactly the cap is allowed


# --- the invite gate --------------------------------------------------------

def test_invite_gate_fails_closed():
    import os
    old = os.environ.get("STEPWISE_INVITE_CODES")
    try:
        os.environ.pop("STEPWISE_INVITE_CODES", None)
        # Unset means OFF, not open. A fresh deploy is never a public downloader.
        assert ingest.invite_codes() == set()
        assert ingest.invite_ok("anything") is False
        assert ingest.invite_ok(None) is False

        os.environ["STEPWISE_INVITE_CODES"] = " alpha , bravo "
        assert ingest.invite_codes() == {"alpha", "bravo"}
        assert ingest.invite_ok("alpha") is True
        assert ingest.invite_ok(" bravo ") is True
        assert ingest.invite_ok("charlie") is False
        assert ingest.invite_ok("") is False
        assert ingest.invite_ok(None) is False

        os.environ["STEPWISE_INVITE_CODES"] = " , , "
        assert ingest.invite_codes() == set()
        assert ingest.invite_ok("") is False
    finally:
        if old is None:
            os.environ.pop("STEPWISE_INVITE_CODES", None)
        else:
            os.environ["STEPWISE_INVITE_CODES"] = old


def test_no_invocation_can_carry_credentials():
    # yt-dlp needs no credentials and must never be given any. --ignore-config
    # is the one that matters: without it a yt-dlp.conf on the host could
    # inject a --cookies line into a process fetching on behalf of strangers.
    for flag in ("--ignore-config", "--no-cookies", "--no-cookies-from-browser"):
        assert flag in ingest._BASE_ARGS, flag


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} checks passed")
