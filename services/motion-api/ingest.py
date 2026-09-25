"""Paste a link, get a lesson: server-side fetch of a TikTok or YouTube URL.

This is the MVP's front door -- "someone comes to the website, pastes a TikTok
or YouTube link, and gets a lesson". `POST /clips` already takes a file; this
module is everything that has to happen before a pasted URL can become that
same file.

**Read `docs/research/link-ingestion.md` before changing this.** The platform
terms question for *ingestion* is genuinely different from the one
`docs/legal/rights-and-privacy.md` answered for *uploads*, it is not
settled, and the answer this code implements ("invite-only pilot, not public
launch") is a scope choice with a named expiry, not a legal conclusion.

Three things live here and nothing else does:

* **Normalisation.** yt-dlp is asked for metadata only, and its answer carries
  the canonical `(extractor, id)` pair. That pair IS the normalisation: a
  TikTok share link (`/t/ZP83Enx4b/`), the full `@user/video/76721...` URL and
  the same link with tracking query parameters all resolve to
  `tiktok:7672198121417444628`. No URL regexes are written here, because the
  extractor that will do the download is the only thing that can say
  authoritatively what a URL points at. Measured: 1.5 s for a TikTok probe.

* **Refusal before download.** The same metadata call carries `duration` and
  `live_status`, so a ten-minute video or a live stream is refused without
  fetching a byte. Refusing without fetching is strictly better than refusing
  after: less of someone else's bandwidth, less of ours, faster for the person
  who pasted it.

* **Honest failure.** yt-dlp fails in ways a file upload cannot, and the
  failure reasons are *not* reliably recoverable from its output. See
  `classify_fetch_error` -- the rule there is DESIGN.md section 7h's: never
  state a reason we did not observe. When yt-dlp fails opaquely we say the
  fetch failed, not why.

The errors this module raises carry exactly the `(code, message, retryable)`
triple that `job-status.schema.json`'s `error` object requires, so api.py can
hand one straight to a client without reinterpreting it.

**No credentials, ever.** yt-dlp is invoked with no cookies, no `--username`,
no `--netrc`, no browser cookie import. If a platform demands a login, the
answer is that we could not fetch it -- not that we logged in as someone.
`login_required` is a refusal, never a prompt to add secrets here.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# PRD section 5: one clip, <=60 s. This constant and
# `tools/process_clip.extract_frames`'s `max_seconds` are one fact written
# twice -- if the cap moves, both move, plus the copy in apps/web/lib/copy.ts
# (DESIGN.md section 7h: a number in copy and a constant in code change in the
# same commit).
MAX_CLIP_SECONDS = 60.0

# Only two platforms, deliberately, and checked on the HOSTNAME before yt-dlp
# is invoked at all. yt-dlp supports well over a thousand sites; being a
# general-purpose downloader for anything a stranger pastes is a different
# product with a different rights posture. The allowlist is the control that
# keeps this one honest, and it is cheaper to audit than a blocklist.
ALLOWED_HOSTS = frozenset({
    "tiktok.com", "www.tiktok.com", "m.tiktok.com", "vm.tiktok.com", "vt.tiktok.com",
    "youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be",
})

# Checked again after extraction, against yt-dlp's own extractor name, because
# a hostname is a claim about a URL and the extractor is a fact about what was
# actually found. Lowercased: yt-dlp reports "TikTok" but "youtube".
ALLOWED_EXTRACTORS = frozenset({"tiktok", "youtube"})

_PROBE_TIMEOUT_S = 60
_DOWNLOAD_TIMEOUT_S = 300


class FetchRefused(Exception):
    """A link we will not or cannot turn into a lesson.

    Carries the job-status error triple so the caller never has to invent one.
    `retryable` follows job-status.schema.json's definition exactly -- "could
    re-submitting the same thing plausibly succeed" -- which for this path is
    cheap to be generous about: a retried fetch costs one HTTP request and no
    GPU time, so an unclassifiable failure is marked retryable rather than
    closing a door we cannot see through.
    """

    def __init__(self, code: str, message: str, retryable: bool):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable

    def as_error(self) -> dict:
        return {"code": self.code, "message": self.message, "retryable": self.retryable}


def ytdlp_available() -> bool:
    return shutil.which("yt-dlp") is not None


# ---------------------------------------------------------------------------
# Failure classification.
#
# The honesty rule (DESIGN.md section 7h, and this task's brief) is that we may
# not state a reason we did not observe. That cuts harder here than it looks,
# because the platforms themselves lie:
#
#   $ yt-dlp https://www.tiktok.com/@jonraydybuco/video/1111111111111111111
#   ERROR: [TikTok] 1111111111111111111: Your IP address is blocked from
#          accessing this post
#
# That video id does not exist. TikTok returns the same "your IP is blocked"
# string for a deleted post, a private post and an actually-blocked IP, so
# relaying it as "your link was blocked" would be stating a reason we did not
# observe -- we observed a refusal, not its cause. Likewise YouTube answers
# "This video is unavailable" for both a private video and one that never
# existed (both verified, 2026-09-21).
#
# So: only patterns whose *meaning* is unambiguous get a specific code. The
# rest fall through to `fetch_failed`, which says what happened and stops.
# Provenance is marked per row -- OBSERVED means reproduced against the live
# platform on 2026-09-21; SOURCE means taken from the yt-dlp version pinned in
# requirements-api.txt, not reproduced here.
# ---------------------------------------------------------------------------

_ERROR_PATTERNS: tuple[tuple[tuple[str, ...], str, str, bool], ...] = (
    # OBSERVED: `yt-dlp https://example.com/` -> "ERROR: Unsupported URL: ..."
    (("unsupported url",), "link_not_supported",
     "That link does not point at a video we can open. Paste a TikTok or YouTube link.",
     False),
    # OBSERVED (from Modal): YouTube answers datacenter IPs with "Sign in to
    # confirm you're not a bot. Use --cookies-from-browser ...". That is
    # YouTube refusing our servers, not the video being behind a login, so it
    # is matched BEFORE the login row (it carries the same "--cookies" hint).
    # Only "not a bot": "Sign in to confirm your age" is a genuine login wall
    # and stays login_required.
    # ponytail: no proxy yet. A paid residential proxy would plug in as
    # `--proxy <url>` (from an env var) on both yt-dlp calls, probe and
    # download; this row then only fires when the proxy is blocked too.
    (("not a bot",), "host_blocked",
     "YouTube is blocking our servers right now. "
     "Download the video and upload the file here instead.",
     False),
    # OBSERVED: `yt-dlp https://vimeo.com/76979871` -> "web client only works
    # when logged-in. Use --cookies, ...". The "--cookies" hint is yt-dlp's
    # standard `_login_hint()` suffix and is an unambiguous marker that the
    # platform demanded credentials. We have none and will not get any.
    (("--cookies", "sign in to confirm", "login required", "requires authentication"),
     "login_required",
     "That video is behind a login, so we cannot open it.",
     False),
    # SOURCE: yt-dlp/extractor/common.py `raise_geo_restricted` default message
    # and youtube/_video.py's "The uploader has not made this video available
    # in your country" branch. Not reproduced -- no geo-locked clip to hand.
    (("geo restriction", "not available from your location",
      "not made this video available in your country"),
     "region_locked",
     "That video is not available where our server is, so we cannot open it.",
     False),
    # SOURCE: yt-dlp surfaces the platform's HTTP status verbatim. Retryable:
    # this is the one failure that genuinely clears on its own.
    (("http error 429", "too many requests", "rate-limit", "rate limit"),
     "rate_limited",
     "The platform is asking us to slow down. Try that link again in a few minutes.",
     True),
    # OBSERVED (TikTok, for a video id that does not exist). Deliberately NOT
    # reported as "deleted", "private" or "blocked" -- see the note above.
    (("ip address is blocked",), "fetch_blocked",
     "TikTok would not give us that video.",
     True),
)

# Everything else. The message names what we did and what failed, and stops
# there. It does not guess between private, deleted, region-locked, moved or
# broken, because from here those are indistinguishable.
_UNCLASSIFIED = ("fetch_failed",
                 "We could not get that video from the link.",
                 True)


def classify_fetch_error(stderr: str) -> FetchRefused:
    """Map yt-dlp's stderr to a job-status error, or refuse to guess."""
    low = (stderr or "").lower()
    for needles, code, message, retryable in _ERROR_PATTERNS:
        if any(n in low for n in needles):
            return FetchRefused(code, message, retryable)
    return FetchRefused(*_UNCLASSIFIED)


# ---------------------------------------------------------------------------
# Normalisation + the pre-download gate.
# ---------------------------------------------------------------------------

def _host_allowed(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in ALLOWED_HOSTS


def probe(url: str) -> dict:
    """Metadata only, no download. Raises FetchRefused.

    Returns yt-dlp's info dict. The fields this module relies on -- `id`,
    `extractor`, `duration`, `live_status`, `webpage_url` -- are yt-dlp's
    documented output fields, so this reads structured data rather than
    scraping its own tool's log lines. String matching is only used on the
    failure path, where there is nothing structured to read.
    """
    if not url or not url.strip():
        raise FetchRefused("link_not_supported", "Paste a TikTok or YouTube link.", False)
    if not _host_allowed(url):
        raise FetchRefused(
            "link_not_supported",
            "We can only open TikTok and YouTube links right now.",
            False)
    if not ytdlp_available():
        # Not the visitor's fault and not their problem to solve, so this is
        # retryable and says nothing about their link.
        raise FetchRefused("fetch_failed",
                           "Links are not working right now. A file upload still works.",
                           True)

    try:
        proc = subprocess.run(
            ["yt-dlp", "--skip-download", "--dump-single-json", "--no-warnings",
             "--no-playlist", "--", url],
            capture_output=True, text=True, timeout=_PROBE_TIMEOUT_S,
        )
    except subprocess.SubprocessError:
        raise FetchRefused("fetch_failed",
                           "We could not reach that link. Try again.", True) from None
    if proc.returncode != 0:
        raise classify_fetch_error(proc.stderr)
    try:
        info = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise FetchRefused(*_UNCLASSIFIED) from None
    check_info(info)
    return info


def check_info(info: dict) -> None:
    """The refusals we can make from metadata, before spending a download.

    Ordered cheapest-to-explain first. Each one is a fact read off the
    metadata, never an inference.
    """
    if (info.get("extractor") or "").lower() not in ALLOWED_EXTRACTORS:
        raise FetchRefused("link_not_supported",
                           "We can only open TikTok and YouTube links right now.", False)

    # yt-dlp's documented values: is_live, is_upcoming, post_live, was_live,
    # not_live. A finished stream (`was_live`) is an ordinary video; the other
    # three are not something with a fixed length to make a lesson from.
    if info.get("live_status") in {"is_live", "is_upcoming", "post_live"}:
        raise FetchRefused("live_stream",
                           "That is a live stream, so there is no finished clip to build from.",
                           False)

    duration = info.get("duration")
    if isinstance(duration, (int, float)) and duration > MAX_CLIP_SECONDS:
        # OPEN-DECISIONS.md D9 is still open -- refuse, offer a trimmer, or
        # trim silently. This refuses, and says what to do next rather than
        # what we will not do (DESIGN.md section 11). It does NOT trim: a
        # silent trim would hand back a lesson for a different dance than the
        # one that was pasted.
        #
        # yt-dlp reports duration as whole seconds, so a 60.4 s clip reports 60
        # and passes here. The pipeline's own cap catches it; the gate is a
        # cheap refusal for the 10-minute case, not a precise boundary.
        raise FetchRefused(
            "clip_too_long",
            f"That video is {int(duration)} seconds. Up to 60 works -- "
            "trim it to the part you want to learn and upload that.",
            False)


def source_key(info: dict) -> str:
    """The canonical identity of a pasted link: `<extractor>:<id>`.

    Every way of writing the same TikTok -- share link, full URL, tracking
    parameters, mobile host -- resolves to one string here, which is what makes
    "paste the same link twice, get the same lesson" true. Verified against
    the builder's own clips: `https://www.tiktok.com/t/ZP83Enx4b/` and
    `https://www.tiktok.com/@jonraydybuco/video/7672198121417444628` both
    normalise to `tiktok:7672198121417444628`.
    """
    return f"{(info.get('extractor') or '').lower()}:{info.get('id') or ''}"


_HOST_NAMES = {"tiktok": "TikTok", "youtube": "YouTube"}


def credit(info: dict, pasted_url: str) -> dict:
    """Who made the original, for the "Original by @creator on TikTok" line.

    docs/legal/legal-public-learning.md §6(a)2. Read off yt-dlp's metadata
    (checked 2026-09-23): TikTok's `uploader` is the @handle without the @ and
    its `uploader_id` is a number; YouTube's `uploader_id` is the "@handle" and
    `uploader` the channel name. `creator` is None when neither is there -- the
    line then names only the host rather than guessing a person.

    Plus, only when found: `choreo` (who the caption credits, choreo_credit),
    `track` and `artist` (music_credit). The caption itself is never stored,
    only what was extracted from it.
    """
    extractor = (info.get("extractor") or "").lower()
    uploader_id = info.get("uploader_id") or ""
    uploader = info.get("uploader") or ""
    if uploader_id.startswith("@"):
        creator = uploader_id
    elif extractor == "tiktok" and uploader:
        creator = f"@{uploader}"
    else:
        creator = uploader or None
    url = info.get("webpage_url") or ""
    # The link goes on the page, so it has to be one of the two hosts we fetch
    # from; the pasted URL already passed that check.
    out = {"url": clean_url(url if _host_allowed(url) else pasted_url),
           "host": _HOST_NAMES.get(extractor, extractor), "creator": creator}
    choreo = choreo_credit(info.get("description") or info.get("title") or "")
    if choreo:
        out["choreo"] = choreo
    out.update(music_credit(info))
    return out


def clean_url(url: str) -> str:
    """The canonical video URL: tracking query (TikTok's `?_r=1&_t=...`,
    YouTube's `si=`) and fragment dropped. YouTube's `v` is the one query
    parameter that IS the video, so it stays."""
    p = urlparse(url)
    keep = [(k, v) for k, v in parse_qsl(p.query) if k == "v"]
    return urlunparse(p._replace(query=urlencode(keep), fragment=""))


# C0/C1 controls, zero-width and bidi-override characters: never on the page.
_CONTROL = re.compile("[\x00-\x1f\x7f-\x9f​-‏‪-‮⁦-⁩]")


def _tidy(s, cap: int = 80) -> str | None:
    """Controls out, whitespace squeezed, capped at `cap` characters."""
    if not isinstance(s, str):
        return None
    s = " ".join(_CONTROL.sub(" ", s).split())
    return (s[:cap - 1] + "…" if len(s) > cap else s) or None


def music_credit(info: dict) -> dict:
    """{track, artist}, whichever yt-dlp has. TikTok's "original sound - x" is
    kept: it names whose sound it is. The artist is dropped when the track
    already names them ("original sound - x" by "x")."""
    track = _tidy(info.get("track"))
    artists = info.get("artists")
    if isinstance(artists, list) and artists:
        artist = _tidy(", ".join(a for a in artists if isinstance(a, str)))
    else:
        artist = _tidy(info.get("artist"))
    if track and artist and artist.lower() in track.lower():
        artist = None
    return {k: v for k, v in (("track", track), ("artist", artist)) if v}


# Choreography credit from the caption: only the forms dancers write before a
# handle, and only @handles after them -- plus a capitalised name right after
# "choreo by". No match, no credit: never a guess. `(?<![#\w])` keeps hashtags
# (#choreo, #dc) out. TikTok handles: letters, digits, "_" and ".".
_LEAD = re.compile(
    r"(?<![#\w])(?:choreographed\s+by|choreo(?:graphy|grapher)?(?:\s+by)?"
    r"|dc|dance\s+credits?|cr(?:edits?)?)\s*[:\-–—]?\s*(?=@)",
    re.IGNORECASE)
_HANDLE = re.compile(r"\s*(?:,|&|\+|/|\band\b|\bx\b)?\s*@([A-Za-z0-9_.]{2,30})", re.IGNORECASE)
_NAMED = re.compile(r"(?<![#\w])(?i:choreo(?:graphy)?|choreographed)\s+(?i:by)\s*[:\-–—]?\s*"
                    r"([A-Z][\w'’-]+(?:\s+[A-Z][\w'’-]+){0,2})")
# "cr"/"credit" also credits filming and sound: skip it after one of these
# ("🎥 cr @x", "song cr: @x"). The camera emoji alone never leads a match.
_NOT_CHOREO = re.compile(r"(🎥|📹|📸|\bvid(eo)?|\bfilm(ed)?|\bsong|\bmusic|\baudio|\bsound)\W*$",
                         re.IGNORECASE)


def choreo_credit(caption: str) -> str | None:
    """"@a, @b" for whoever the caption credits with the choreography (up to
    three, in caption order), a plain name after "choreo by", or None."""
    caption = (caption or "")[:4000]
    handles: list[str] = []
    for m in _LEAD.finditer(caption):
        if m.group(0)[:2].lower() == "cr" and _NOT_CHOREO.search(caption[max(0, m.start() - 12):m.start()]):
            continue
        pos = m.end()
        while h := _HANDLE.match(caption, pos):
            name = "@" + h.group(1).rstrip(".")
            if name.lower() not in {x.lower() for x in handles}:
                handles.append(name)
            pos = h.end()
    if handles:
        return _tidy(", ".join(handles[:3]), 100)
    m = _NAMED.search(caption)
    if m and m.group(1).split()[0].lower() not in {"me", "myself", "us", "the", "my"}:
        return _tidy(m.group(1), 40)
    return None


# ---------------------------------------------------------------------------
# The download.
# ---------------------------------------------------------------------------

def download(url: str, dest_path: str) -> None:
    """Fetch the video to `dest_path`. Raises FetchRefused.

    Format selection matches `evaluation/fetch.py`: the largest H.264 stream
    whose SHORT side is <= 1080. The old `[height<=1080]` filter read "1080p"
    as a landscape height, so every vertical clip lost its 1920-tall stream:
    checked with `yt-dlp --print` on 2026-09-23, YouTube Shorts came down at
    480x854 under the old filter and 1080x1920 under this one (landscape
    1920x1080 unchanged). Hands are ~30 px wide at 576 px across, which is
    what caps every hand-shape model we measured (see hand_crops.py), so
    those pixels matter. H.264 first because the file is served to browsers
    as-is: TikTok also offers 720x1280 without a login, but only as HEVC,
    which Firefox will not play -- so TikTok stays at 576x1024 H.264.
    """
    if not ytdlp_available():
        raise FetchRefused("fetch_failed",
                           "Links are not working right now. A file upload still works.",
                           True)
    out_dir = tempfile.mkdtemp(prefix="stepwise-ingest-")
    # yt-dlp picks the container, so let it write a templated name and take
    # whatever single file appears -- guessing ".mp4" up front is how you get
    # a silent "downloaded nothing" when the merge produces .mkv.
    try:
        proc = subprocess.run(
            ["yt-dlp",
             "-f", "bv*+ba/b", "-S", "vcodec:h264,res:1080",
             "--merge-output-format", "mp4",
             "--no-playlist", "--no-warnings",
             "-o", os.path.join(out_dir, "clip.%(ext)s"),
             "--", url],
            capture_output=True, text=True, timeout=_DOWNLOAD_TIMEOUT_S,
        )
        if proc.returncode != 0:
            raise classify_fetch_error(proc.stderr)
        files = [os.path.join(out_dir, f) for f in os.listdir(out_dir)]
        files = [f for f in files if os.path.isfile(f) and os.path.getsize(f) > 0]
        if len(files) != 1:
            # yt-dlp said it succeeded and did not leave exactly one file. We
            # do not know why, so we do not say why.
            raise FetchRefused(*_UNCLASSIFIED)
        shutil.move(files[0], dest_path)
    except subprocess.SubprocessError:
        raise FetchRefused("fetch_failed",
                           "That video took too long to fetch. Try again.", True) from None
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# The invite gate.
# ---------------------------------------------------------------------------

def invite_codes() -> frozenset[str]:
    """Codes read from the environment on every call, never from a file.

    Read per-call so a code can be added or revoked by restarting the service
    with a different value, with no deploy and nothing written to disk.
    """
    raw = os.environ.get("STEPWISE_INVITE_CODES", "")
    # Lower-cased, and compared lower-cased: a phone keyboard capitalises the
    # first letter ("Andaaz"), and a tester should not be turned away for it.
    return frozenset(c.strip().lower() for c in raw.split(",") if c.strip())


def invite_code_ok(code: str | None) -> bool:
    """Closed by default: no codes configured means the link path is shut.

    **What this does not protect against, stated plainly.** A shared secret is
    not identity. Everyone in the pilot holds the same string, so the gate
    cannot tell them apart, cannot revoke one person, cannot rate-limit one
    person, and cannot survive one of them pasting it into a group chat. It
    also does not protect the *platforms* from anything -- it limits who can
    ask us to fetch, not what we fetch.

    What it does do is make "link ingestion is reachable only by invited
    testers" a property of the code rather than of a promise, without
    inventing the account system OPEN-DECISIONS.md D5 leaves open. When D5 is
    decided, this is one function to delete.
    """
    codes = invite_codes()
    if not codes:
        return False
    return code is not None and code.strip().lower() in codes
