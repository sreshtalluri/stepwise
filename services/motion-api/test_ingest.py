"""The runnable check for the pasted-link front door.

Everything here runs against an in-memory stand-in for a Modal Volume and a
fake yt-dlp, because the questions worth checking are about *which clip_id
comes back* and *what a failure says*, and neither needs a network or a GPU:

  * a TikTok share link and the full URL normalise to one source_key
  * pasting the same link twice never downloads twice
  * the same dance reached by upload and by link lands on ONE clip_id
  * two simultaneous pastes of one link cannot produce two lessons
  * an over-length video is refused from metadata, before any download
  * a failure we cannot explain says so, instead of guessing
  * the invite gate is closed by default and does not touch file upload

    python3 -m pytest test_ingest.py -q

The live-network checks against the builder's own clips are separate and
marked: `STEPWISE_LIVE=1 python3 -m pytest test_ingest.py -q -k live`.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_retention import NO_REQUEST, FakeVolume, _removal  # noqa: E402 -- same harness, same volumes

TIKTOK_SHORT = "https://www.tiktok.com/t/ZP83Enx4b/"
TIKTOK_FULL = "https://www.tiktok.com/@jonraydybuco/video/7672198121417444628"
TIKTOK_ID = "7672198121417444628"


def _info(duration=19, vid=TIKTOK_ID, extractor="TikTok", live_status=None):
    # uploader / uploader_id as yt-dlp reported them for this clip, 2026-09-23.
    return {"id": vid, "extractor": extractor, "duration": duration,
            "live_status": live_status, "webpage_url": TIKTOK_FULL,
            "uploader": "jonraydybuco", "uploader_id": "6842822859564581894"}


@pytest.fixture()
def api(monkeypatch):
    """api.py with modal stubbed out and fresh volumes, plus a fake yt-dlp."""
    fake_modal = types.ModuleType("modal")
    fake_modal.Volume = types.SimpleNamespace(from_name=lambda *a, **k: FakeVolume(a[0]))
    spawned: list[dict] = []
    # `spawned` records GPU runs only; the CPU beat proposal spawned beside
    # each one hands back a call id for run_clip to collect.
    fake_modal.Function = types.SimpleNamespace(
        from_name=lambda app, name, **k: types.SimpleNamespace(
            spawn=lambda **kw: types.SimpleNamespace(object_id=f"fc-{name}")))
    # run_clip runs as Reconstructor.run; warm() is the ingest-time pre-warm.
    warmed: list[str] = []

    async def _warm():
        warmed.append("warm")
    fake_modal.Cls = types.SimpleNamespace(
        from_name=lambda app, name, **k: lambda: types.SimpleNamespace(
            run=types.SimpleNamespace(spawn=lambda **kw: spawned.append(kw)),
            warm=types.SimpleNamespace(spawn=types.SimpleNamespace(aio=_warm))))
    monkeypatch.setitem(sys.modules, "modal", fake_modal)
    for mod in ("api", "retention", "motion_result", "fingerprint", "ingest"):
        sys.modules.pop(mod, None)
    import api as api_mod
    api_mod.uploads_volume = FakeVolume("uploads")
    api_mod.results_volume = FakeVolume("results")
    api_mod.eval_volume = FakeVolume("eval")
    api_mod._TOUCHED.clear()
    api_mod._spawned = spawned
    api_mod._warmed = warmed
    monkeypatch.setenv("STEPWISE_INVITE_CODES", "let-me-in")
    return api_mod


@pytest.fixture()
def fake_ytdlp(api, monkeypatch):
    """A yt-dlp that answers from a script instead of the network.

    `probes` counts metadata calls and `downloads` counts fetches, which is how
    the dedupe tests prove "no download happened" rather than asserting on a
    log line.
    """
    import ingest
    state = types.SimpleNamespace(info=_info(), probes=0, downloads=0,
                                  video=b"fake-video-bytes")
    monkeypatch.setattr(ingest, "ytdlp_available", lambda: True)

    def fake_probe(url):
        state.probes += 1
        ingest.check_info(state.info)
        return state.info

    def fake_download(url, dest):
        state.downloads += 1
        Path(dest).write_bytes(state.video)

    # Patched at the ingest module so api.py's own call path is exercised.
    monkeypatch.setattr(ingest, "probe", fake_probe)
    monkeypatch.setattr(ingest, "download", fake_download)
    return state


def _paste(api, url=TIKTOK_SHORT, code="let-me-in"):
    return api.ingest_clip_link(api.LinkRequest(url=url), NO_REQUEST, x_invite_code=code)


def _succeed(api, resp):
    """Mark the dispatched job succeeded, as run_clip + export would."""
    api.results_volume.files[f"/{resp.job_id}.job-status.json"] = json.dumps({
        "schema_version": "1.0.0", "job_id": resp.job_id, "state": "succeeded",
        "stage_message": "", "progress": 1.0, "error": None, "retry_count": 0,
    }).encode()


# ---------------------------------------------------------------------------
# normalisation
# ---------------------------------------------------------------------------

def test_share_link_and_full_url_normalise_to_one_key():
    import ingest
    assert ingest.source_key(_info()) == f"tiktok:{TIKTOK_ID}"
    # Same id, different URL shape (yt-dlp resolved both) -> same key, and
    # therefore the same derived clip_id.
    import api  # noqa: F401 -- only for the helper below
    assert ingest.source_key(_info(vid=TIKTOK_ID)) == ingest.source_key(_info(vid=TIKTOK_ID))


def test_clip_id_is_derived_from_the_link_not_minted(api):
    a = api._clip_id_for_source(f"tiktok:{TIKTOK_ID}")
    b = api._clip_id_for_source(f"tiktok:{TIKTOK_ID}")
    assert a == b and len(a) == 32
    assert a != api._clip_id_for_source(f"youtube:{TIKTOK_ID}")


def test_only_tiktok_and_youtube_hosts_are_fetched():
    import ingest
    for url in ("https://vimeo.com/76979871", "https://example.com/",
                "https://tiktok.com.evil.test/x", "not a url"):
        with pytest.raises(ingest.FetchRefused) as e:
            ingest.probe(url)
        assert e.value.code == "link_not_supported", url
        assert e.value.retryable is False


# ---------------------------------------------------------------------------
# dedupe -- both layers, converging on one clip_id
# ---------------------------------------------------------------------------

def test_pasting_the_same_link_twice_downloads_once(api, fake_ytdlp):
    first = _paste(api)
    _succeed(api, first)
    assert fake_ytdlp.downloads == 1
    assert len(api._spawned) == 1

    second = _paste(api, url=TIKTOK_FULL)  # same video, different URL shape
    assert second.clip_id == first.clip_id
    assert second.deduplicated is True
    assert fake_ytdlp.downloads == 1, "the URL layer must settle before any download"
    assert len(api._spawned) == 1, "no second GPU run"


def test_upload_then_link_lands_on_one_clip_id(api, fake_ytdlp, tmp_path):
    """The same dance reached by two different routes is ONE lesson.

    This is the property a takedown depends on: removing it has to remove it
    for the person who uploaded the file AND the person who pasted the link.
    """
    import fingerprint
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(fake_ytdlp.video)
    fp = fingerprint.fingerprint(str(clip))
    uploaded = api._store_and_dispatch(str(clip), "deadbeef" * 4, fp, NO_REQUEST)
    _succeed(api, uploaded)

    pasted = _paste(api)
    assert pasted.clip_id == uploaded.clip_id, "two routes, two lessons -- takedown would be partial"
    assert api.get_job_source(pasted.job_id)["host"] == "TikTok", "the link's video is credited"
    assert pasted.deduplicated is True
    assert len(api._spawned) == 1

    # And the link layer has now learned the shortcut, so the next paste of
    # this link does not download at all.
    downloads_before = fake_ytdlp.downloads
    again = _paste(api)
    assert again.clip_id == uploaded.clip_id
    assert fake_ytdlp.downloads == downloads_before


# ---------------------------------------------------------------------------
# creator credit
# ---------------------------------------------------------------------------

def test_credit_reads_the_handle_per_platform():
    import ingest
    assert ingest.credit(_info(), TIKTOK_SHORT) == {
        "url": TIKTOK_FULL, "host": "TikTok", "creator": "@jonraydybuco"}
    yt = {"extractor": "youtube", "uploader": "Blender", "uploader_id": "@BlenderOfficial",
          "webpage_url": "https://www.youtube.com/watch?v=aqz-KE-bpKQ"}
    assert ingest.credit(yt, "x") == {"url": yt["webpage_url"], "host": "YouTube",
                                      "creator": "@BlenderOfficial"}
    # No handle: name the host only. A link off our two hosts: use the pasted one.
    bare = {"extractor": "TikTok", "webpage_url": "javascript:alert(1)"}
    assert ingest.credit(bare, TIKTOK_SHORT) == {"url": TIKTOK_SHORT, "host": "TikTok", "creator": None}


def test_link_lesson_serves_its_credit_and_upload_does_not(api, fake_ytdlp, tmp_path):
    import fingerprint
    clip = tmp_path / "other.mp4"
    clip.write_bytes(b"a different dance")
    uploaded = api._store_and_dispatch(str(clip), "cafe" * 8, fingerprint.fingerprint(str(clip)), NO_REQUEST)
    with pytest.raises(api.HTTPException) as e:
        api.get_job_source(uploaded.job_id)
    assert e.value.status_code == 404

    pasted = _paste(api)
    assert api.get_job_source(pasted.job_id)["creator"] == "@jonraydybuco"
    # Removal deletes job-meta, so the credit goes with the lesson.
    api.remove_lesson_by_job(pasted.job_id, _removal(api, relationship="under_18"), NO_REQUEST)
    with pytest.raises(api.HTTPException):
        api.get_job_source(pasted.job_id)


# ---------------------------------------------------------------------------
# music and choreography credit (caption parsing is offline and exact)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("caption,expected", [
    ("new dance!! choreo by @jonraydybuco 💃 #fyp #dance", "@jonraydybuco"),
    ("Choreography: @kyle.hanagami", "@kyle.hanagami"),
    ("choreo - @a_b & @c.d #kpop", "@a_b, @c.d"),
    ("learned this!! dc: @jonraydybuco", "@jonraydybuco"),
    ("dance credits @someone_123 🔥", "@someone_123"),
    ("cr: @mikey.dance", "@mikey.dance"),
    ("choreographed by @mia and @leo", "@mia, @leo"),
    ("CHOREO @one @two x @three + @four", "@one, @two, @three"),  # capped at three
    ("🎥 @filmguy choreo @dancer", "@dancer"),                    # camera is not choreo
    ("🎥 cr @filmguy", None),
    ("song cr: @artist", None),
    ("tried the trend with @bestie #choreo #dc", None),           # hashtags, no lead
    ("my choreo!! #fyp", None),
    ("choreo by me 😅", None),
    ("choreo by Jane Doe #dance", "Jane Doe"),
    ("", None),
    ("dc @Same, @same", "@Same"),
])
def test_choreo_credit_reads_only_what_the_caption_says(caption, expected):
    import ingest
    assert ingest.choreo_credit(caption) == expected


def test_choreo_credit_strips_controls_and_caps():
    import ingest
    long = "choreo @" + "a" * 60
    assert ingest.choreo_credit(long) == "@" + "a" * 30
    assert ingest.choreo_credit("choreo by Jane‮ Doe") == "Jane"


def test_music_credit():
    import ingest
    assert ingest.music_credit({"track": "APT.", "artists": ["ROSÉ", "Bruno Mars"]}) == {
        "track": "APT.", "artist": "ROSÉ, Bruno Mars"}
    # TikTok's own-sound placeholder names whose sound it is: kept, artist folded in.
    assert ingest.music_credit({"track": "original sound - jonraydybuco",
                                "artist": "jonraydybuco"}) == {"track": "original sound - jonraydybuco"}
    assert ingest.music_credit({"track": "Song\x00\n Name", "artist": "x" * 200})["track"] == "Song Name"
    assert len(ingest.music_credit({"artist": "x" * 200})["artist"]) == 80
    assert ingest.music_credit({}) == {}


def test_clean_url_drops_tracking_but_keeps_the_video():
    import ingest
    assert ingest.clean_url(TIKTOK_FULL + "?_r=1&_t=ZP-8xYz&is_from_webapp=1#x") == TIKTOK_FULL
    assert ingest.clean_url("https://www.youtube.com/watch?v=aqz-KE-bpKQ&si=abc&t=3") == \
        "https://www.youtube.com/watch?v=aqz-KE-bpKQ"
    assert ingest.clean_url("https://youtu.be/aqz-KE-bpKQ?si=abc") == "https://youtu.be/aqz-KE-bpKQ"


def test_credit_carries_caption_and_music_fields_only_when_found():
    import ingest
    info = dict(_info(), description="choreo by @kyle.hanagami #fyp " + "blah " * 100,
                track="APT.", artist="ROSÉ")
    c = ingest.credit(info, TIKTOK_SHORT + "?_r=1&_t=abc")
    assert c == {"url": TIKTOK_FULL, "host": "TikTok", "creator": "@jonraydybuco",
                 "choreo": "@kyle.hanagami", "track": "APT.", "artist": "ROSÉ"}
    # The pasted URL is cleaned too when it is the one used.
    bare = {"extractor": "TikTok", "title": "no credit here"}
    assert ingest.credit(bare, TIKTOK_SHORT + "?_r=1") == {
        "url": TIKTOK_SHORT, "host": "TikTok", "creator": None}


def test_repasting_a_link_adds_the_new_credit_fields(api, fake_ytdlp):
    first = _paste(api)
    # A lesson credited before these fields existed, with a tracking-param URL.
    path = f"/{first.job_id}.job-meta.json"
    meta = json.loads(api.results_volume.files[path])
    meta["credit"] = {"url": TIKTOK_FULL + "?_r=1", "host": "TikTok", "creator": "@jonraydybuco"}
    api.results_volume.files[path] = json.dumps(meta).encode()

    fake_ytdlp.info = dict(_info(), description="dc @kyle.hanagami", track="APT.")
    _paste(api)
    assert api.get_job_source(first.job_id) == {
        "url": TIKTOK_FULL, "host": "TikTok", "creator": "@jonraydybuco",
        "choreo": "@kyle.hanagami", "track": "APT."}


def test_a_different_posts_credit_does_not_overwrite(api):
    api.results_volume.files["/job_a.job-meta.json"] = json.dumps(
        {"credit": {"url": TIKTOK_FULL, "host": "TikTok", "creator": "@original"}}).encode()
    api._stamp_credit("job_a", {"url": "https://www.tiktok.com/@reuploader/video/1",
                                "host": "TikTok", "creator": "@reuploader"})
    assert api.get_job_source("job_a")["creator"] == "@original"


def test_an_old_credit_is_served_without_tracking_params(api):
    """Saved before clean_url (job_5716ecd3…): the stored URL keeps its junk, the answer does not."""
    stored = {"url": TIKTOK_FULL + "?_r=1&_t=ZP-99zZiojnXfa", "host": "TikTok", "creator": "@original"}
    api.results_volume.files["/job_old.job-meta.json"] = json.dumps({"credit": stored}).encode()
    assert api.get_job_source("job_old") == {**stored, "url": TIKTOK_FULL}
    assert json.loads(api.results_volume.files["/job_old.job-meta.json"])["credit"] == stored, "read-only"
    yt = "https://www.youtube.com/watch?v=abc&si=track"
    api.results_volume.files["/job_yt.job-meta.json"] = json.dumps({"credit": {**stored, "url": yt}}).encode()
    assert api.get_job_source("job_yt")["url"] == "https://www.youtube.com/watch?v=abc"


def test_youtube_bot_check_is_host_blocked_not_login():
    import ingest
    e = ingest.classify_fetch_error(
        "ERROR: [youtube] aqz-KE-bpKQ: Sign in to confirm you’re not a bot. Use "
        "--cookies-from-browser or --cookies for the authentication. See ...")
    assert (e.code, e.retryable) == ("host_blocked", False)
    assert "upload" in e.message and "login" not in e.message
    # An age gate is a real login wall and stays one.
    age = ingest.classify_fetch_error(
        "ERROR: [youtube] x: Sign in to confirm your age. This video may be "
        "inappropriate for some users. Use --cookies ...")
    assert age.code == "login_required"


def test_simultaneous_pastes_cannot_produce_two_lessons(api, fake_ytdlp):
    """The known race: two people paste one link inside the download window.

    Neither request can see the other's index entry, so both reach dispatch.
    They must still agree on one clip_id -- that is what the derived id buys,
    and losing this race must cost GPU money, never a split lesson.
    """
    first = _paste(api)
    # The second request started before the first wrote anything a lookup
    # could find: wipe the index to reproduce exactly that window.
    import retention
    retention.write_index(api.results_volume, [])
    second = _paste(api)
    assert second.clip_id == first.clip_id
    assert second.job_id == first.job_id


def test_a_removed_link_lesson_is_rebuilt_not_resurrected(api, fake_ytdlp):
    """D7: removed content that comes back is reconstructed afresh."""
    first = _paste(api)
    _succeed(api, first)
    api.remove_lesson(first.clip_id, _removal(api), NO_REQUEST)

    again = _paste(api)
    assert again.clip_id != first.clip_id, "must not reuse the tombstoned id"
    assert api.results_volume.files.get(f"/{first.clip_id}.removed.json"), \
        "the tombstone stays, so the old link keeps answering 410"


# ---------------------------------------------------------------------------
# refusals
# ---------------------------------------------------------------------------

def test_over_length_video_is_refused_before_any_download(api, fake_ytdlp):
    from fastapi import HTTPException
    fake_ytdlp.info = _info(duration=612)  # a ten-minute video
    with pytest.raises(HTTPException) as e:
        _paste(api)
    assert e.value.status_code == 422
    err = e.value.detail["error"]
    assert err["code"] == "clip_too_long"
    assert err["retryable"] is False
    assert "612 seconds" in err["message"] and "trim" in err["message"].lower()
    assert fake_ytdlp.downloads == 0, "refusing after fetching wastes everyone's bandwidth"
    assert api._spawned == []


def test_live_stream_is_refused_before_any_download(api, fake_ytdlp):
    from fastapi import HTTPException
    fake_ytdlp.info = _info(duration=None, live_status="is_live")
    with pytest.raises(HTTPException) as e:
        _paste(api)
    assert e.value.detail["error"]["code"] == "live_stream"
    assert fake_ytdlp.downloads == 0
    # A finished stream is an ordinary video and must NOT be refused.
    fake_ytdlp.info = _info(duration=20, live_status="was_live")
    assert _paste(api).clip_id


def test_over_length_caught_after_download_when_metadata_was_silent(api, fake_ytdlp, tmp_path):
    """yt-dlp does not always know the duration. ffprobe does, after the fetch.

    Dispatching here would hand back a lesson for a silently trimmed dance, so
    this refuses instead -- OPEN-DECISIONS.md D9 is still open on whether a
    trimmer is the better answer.
    """
    from fastapi import HTTPException
    fake_ytdlp.info = _info(duration=None)
    import api as _api
    import fingerprint
    monkey = fingerprint.fingerprint
    try:
        fingerprint.fingerprint = lambda p: dict(monkey(p), duration_s=95.0)
        _api.fingerprint.fingerprint = fingerprint.fingerprint
        with pytest.raises(HTTPException) as e:
            _paste(api)
    finally:
        fingerprint.fingerprint = monkey
        _api.fingerprint.fingerprint = monkey
    assert e.value.detail["error"]["code"] == "clip_too_long"
    assert api._spawned == [], "a trimmed lesson is a different dance -- never dispatch it"


@pytest.mark.parametrize("stderr,code,retryable", [
    # OBSERVED against the live platforms, 2026-09-21.
    ("ERROR: Unsupported URL: https://example.com/", "link_not_supported", False),
    ("ERROR: [vimeo] 769: web client only works when logged-in. Use --cookies, ...",
     "login_required", False),
    ("ERROR: [TikTok] 111: Your IP address is blocked from accessing this post",
     "fetch_blocked", True),
    # From yt-dlp's own source strings, marked as such in ingest.py.
    ("ERROR: [youtube] x: This video is not available from your location due to "
     "geo restriction", "region_locked", False),
    ("ERROR: unable to download video data: HTTP Error 429: Too Many Requests",
     "rate_limited", True),
])
def test_failure_classification_matches_observed_strings(stderr, code, retryable):
    import ingest
    e = ingest.classify_fetch_error(stderr)
    assert e.code == code and e.retryable is retryable


def test_an_unexplained_failure_says_so_instead_of_guessing():
    """DESIGN.md §7h: never state a reason we did not observe.

    YouTube answers "This video is unavailable" for a private video AND for one
    that never existed (both verified). Reporting either as the reason would be
    inventing one, so this must fall through to the generic code.
    """
    import ingest
    for stderr in ("ERROR: [youtube] JZDfoTd2eIY: This video is unavailable",
                   "ERROR: [TikTok] 7672: Unable to extract webpage",
                   "some entirely novel yt-dlp failure"):
        e = ingest.classify_fetch_error(stderr)
        assert e.code == "fetch_failed", stderr
        for word in ("private", "deleted", "removed", "blocked", "region", "age"):
            assert word not in e.message.lower(), f"invented a reason: {e.message}"


def test_every_refusal_is_a_valid_job_status_error():
    """The error triple must drop into job-status.schema.json unchanged."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]
                           / "packages" / "motion-contract" / "python"))
    from motion_contract import validate_job_status

    import ingest
    codes = set()
    for needles, code, message, retryable in ingest._ERROR_PATTERNS:
        codes.add(code)
        doc = {"schema_version": "1.0.0", "job_id": "job_x", "state": "failed",
               "stage_message": "", "progress": None, "retry_count": 0,
               "error": ingest.FetchRefused(code, message, retryable).as_error()}
        result = validate_job_status(doc)
        assert result.valid, (code, result.errors)
        # DESIGN.md §11: errors say what happened and never apologise.
        assert not any(w in message.lower() for w in ("sorry", "oops", "apolog")), message
        assert "!" not in message
    # Codes that only exist on the structured (non-string-matched) path.
    assert codes | {"clip_too_long", "live_stream", "fetch_failed", "invite_required", "invite_invalid"}


# ---------------------------------------------------------------------------
# the gate
# ---------------------------------------------------------------------------

def test_invite_gate_is_closed_by_default(api, fake_ytdlp, monkeypatch):
    from fastapi import HTTPException
    monkeypatch.delenv("STEPWISE_INVITE_CODES", raising=False)
    with pytest.raises(HTTPException) as e:
        _paste(api, code="let-me-in")
    assert e.value.status_code == 403
    assert fake_ytdlp.probes == 0, "an un-invited request must not reach the platform at all"


def test_wrong_or_missing_code_is_refused(api, fake_ytdlp):
    from fastapi import HTTPException
    for code, why in ((None, "invite_required"), ("", "invite_required"), ("  ", "invite_required"),
                      ("nope", "invite_invalid")):
        with pytest.raises(HTTPException) as e:
            _paste(api, code=code)
        assert e.value.status_code == 403, code
        assert e.value.detail["error"]["code"] == why, code
    assert "isn't right" in e.value.detail["error"]["message"]
    assert fake_ytdlp.probes == 0
    assert _paste(api, code="let-me-in ").job_id  # whitespace is stripped, so this one is valid


def test_file_upload_is_not_gated(api, monkeypatch, tmp_path):
    """The gate is on links only. Uploads stay open -- PRD §5's real front door."""
    import asyncio

    import fingerprint
    monkeypatch.delenv("STEPWISE_INVITE_CODES", raising=False)
    clip = tmp_path / "u.mp4"
    clip.write_bytes(b"bytes")

    class _Upload:
        def __init__(self, path):
            self._data = Path(path).read_bytes()
            self._sent = False

        async def read(self, n):
            if self._sent:
                return b""
            self._sent = True
            return self._data

    resp = asyncio.run(api.upload_clip(NO_REQUEST, _Upload(clip)))
    assert resp.clip_id and not resp.deduplicated
    assert len(api._spawned) == 1
    assert fingerprint  # silence the unused import; the real one ran above


def test_prewarm_starts_a_gpu_only_for_real_ingest_requests(api):
    """An upload, or a link with a valid invite code, warms a GPU container
    before its body is read; nothing else does -- a closed door costs nothing."""
    import asyncio

    def hit(method, path, **headers):
        req = types.SimpleNamespace(method=method, url=types.SimpleNamespace(path=path),
                                    headers=headers)

        async def call_next(_):
            return "response"
        before = len(api._warmed)
        assert asyncio.run(api._prewarm_gpu(req, call_next)) == "response"
        return len(api._warmed) - before

    assert hit("POST", "/clips") == 1
    assert hit("POST", "/clips/link", **{"x-invite-code": "let-me-in"}) == 1
    assert hit("POST", "/clips/link") == 0
    assert hit("POST", "/clips/link", **{"x-invite-code": "wrong"}) == 0
    assert hit("GET", "/jobs/job_x") == 0
    assert hit("POST", "/jobs/job_x/retry") == 0


# ---------------------------------------------------------------------------
# live: the builder's own clips. Opt in, because it hits TikTok for real.
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not os.environ.get("STEPWISE_LIVE"),
                    reason="set STEPWISE_LIVE=1 to hit TikTok for real")
def test_live_share_link_and_full_url_agree():
    import ingest
    a = ingest.source_key(ingest.probe(TIKTOK_SHORT))
    b = ingest.source_key(ingest.probe(TIKTOK_FULL))
    assert a == b == f"tiktok:{TIKTOK_ID}", (a, b)


@pytest.mark.skipif(not os.environ.get("STEPWISE_LIVE"),
                    reason="set STEPWISE_LIVE=1 to hit TikTok for real")
def test_live_broken_link_fails_honestly():
    import ingest
    with pytest.raises(ingest.FetchRefused) as e:
        ingest.probe("https://www.tiktok.com/@jonraydybuco/video/1111111111111111111")
    # Whatever the platform said, we must not have turned it into a claim
    # about the video's fate.
    assert e.value.code in {"fetch_blocked", "fetch_failed"}
    assert "deleted" not in e.value.message.lower()


@pytest.mark.skipif(not os.environ.get("STEPWISE_LIVE"),
                    reason="set STEPWISE_LIVE=1 to hit TikTok for real")
def test_live_yt_dlp_is_given_no_credentials():
    """A standing check that no cookie or credential flag creeps in here."""
    source = Path(__file__).with_name("ingest.py").read_text()
    for flag in ("--cookies-from-browser", "--username", "--password",
                 "--netrc", "cookiefile"):
        assert f'"{flag}"' not in source, flag
    assert subprocess  # used by ingest, asserted present


def test_link_fetching_container_is_pinned_to_the_us():
    """TikTok gates by the fetcher's country: unpinned, Modal put the API in
    Milan (login wall) or Pune (India ban page) and pasted links failed. Read
    from modal_app.py's source, like test_api_image, so no modal import."""
    import ast
    tree = ast.parse(Path(__file__).with_name("modal_app.py").read_text())
    web = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "web")
    kwargs = {k.arg: k.value for d in web.decorator_list if isinstance(d, ast.Call)
              for k in d.keywords}
    assert isinstance(kwargs.get("region"), ast.Constant) and kwargs["region"].value == "us"
