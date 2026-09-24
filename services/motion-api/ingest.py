"""Paste-a-link ingestion: turn a TikTok or YouTube URL into a local file.

This is the MVP's front door ("someone comes to the website, pastes a TikTok or
YouTube link, gets a lesson"), and it is a **deliberate change to PRD §5**,
which lists paste-a-link as out of v1 scope. The scope note in docs/PRD.md §5
has been updated rather than contradicted silently.

**Read docs/research/link-ingestion.md before widening this.** Short version:
TikTok's and YouTube's terms of service both prohibit automated downloading.
`evaluation/fetch.py` already runs yt-dlp, but only to pull clips into a private
Volume for pipeline testing, which `evaluation/README.md` tiers explicitly as a
different situation from anything public. Fetching on behalf of strangers is a
third situation that neither document covered. The posture this module
implements is the near-term one: **invite-only**, gated below, with the file
upload path left open to everybody. The builder decides before that gate comes
off; it is not a decision this code makes.

Three cost tiers, cheapest first, so the common case spends nothing:

  1. **Syntactic normalisation** (`normalize`) -- zero network. A canonical key
     per video, so the same link pasted twice by two learners is one lookup.
  2. **Probe** (`probe`) -- one JSON request, no media bytes. Resolves TikTok
     short links to their canonical id, and reads `duration` so a ten-minute
     video is refused before a single frame is fetched.
  3. **Download** (`download`) -- the only step that costs bandwidth.

The perceptual fingerprint (fingerprint.py) is the fourth gate and runs after
the download, catching the same dance arriving via a different URL or as a
re-upload. All four converge on one `clip_id` -- see api.py.

**No credentials, ever.** Every yt-dlp invocation below passes `--no-cookies`,
`--no-cookies-from-browser` and `--ignore-config`. A login-walled video is a
failure state (see `classify`), not a reason to hold an account. `--ignore-config`
matters specifically: without it a `yt-dlp.conf` on the host could inject a
`--cookies` line into a process that runs on behalf of strangers.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass

# PRD §5's cap. D9 ("refuse, or offer a trimmer?") is STILL OPEN -- this
# implements refuse, which is the honest floor, and records the decision as
# unresolved in docs/OPEN-DECISIONS.md rather than pretending a trimmer exists.
MAX_DURATION_S = 60.0

# Backstop only. The duration gate above is the real limit; this stops a
# mislabelled or streaming-manifest fetch from filling the disk.
MAX_FETCH_BYTES = 200 * 1024 * 1024

_YTDLP = shutil.which("yt-dlp")

# Never negotiable, and prepended to every invocation. See the module docstring.
_BASE_ARGS = ["--ignore-config", "--no-cookies", "--no-cookies-from-browser",
              "--no-playlist", "--socket-timeout", "30"]


def ytdlp_available() -> bool:
    return bool(_YTDLP)


# --- 1. normalisation -------------------------------------------------------
#
# The key is what the dedupe index is scanned for. Two learners pasting the
# same dance must produce the same key with no network access at all, which
# means stripping everything a share sheet bolts on: `?is_from_webapp=1`,
# `&si=`, `&t=42`, `#`, trailing slashes, `m.`/`music.`/`www.` hosts.

_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com",
                  "music.youtube.com", "youtu.be", "www.youtu.be"}
_TIKTOK_HOSTS = {"tiktok.com", "www.tiktok.com", "m.tiktok.com",
                 "vm.tiktok.com", "vt.tiktok.com"}

_YT_ID = r"(?P<id>[0-9A-Za-z_-]{11})"
_YOUTUBE_PATTERNS = [
    re.compile(r"^/watch$"),                     # id comes from ?v=
    re.compile(rf"^/(?:shorts|embed|v|live|e)/{_YT_ID}"),
]
_TIKTOK_LONG = re.compile(r"^/@[^/]+/(?:video|photo)/(?P<id>\d{6,})")
_TIKTOK_LONG_ALT = re.compile(r"^/(?:v|embed)/(?P<id>\d{6,})")
# The share-sheet form. `/t/ZP83Enx4b/` and `vm.tiktok.com/ZP83Enx4b` are the
# two shapes TikTok's own "copy link" produces; neither carries the video id,
# so they only resolve at probe time.
_TIKTOK_SHORT = re.compile(r"^/(?:t/)?(?P<code>[A-Za-z0-9]{5,})/?$")


@dataclass(frozen=True)
class Link:
    platform: str          # "tiktok" | "youtube"
    key: str               # dedupe key, e.g. "youtube:M7FIvfx5J10"
    fetch_url: str         # what yt-dlp is actually given
    resolved: bool         # False when `key` is a short code, not a video id


def normalize(raw: str) -> Link | None:
    """Canonical dedupe key for a supported link, or None if it is not one.

    None means "not a TikTok or YouTube video link" and is answered
    immediately, with no network and no job -- there is nothing to observe and
    nothing to retry. Everything that needs the network to decide becomes a job
    failure instead (see `classify`).
    """
    from urllib.parse import parse_qs, urlsplit

    raw = (raw or "").strip()
    if not raw:
        return None
    if not re.match(r"^https?://", raw, re.I):
        raw = "https://" + raw  # people paste "tiktok.com/@x/video/1" without a scheme
    try:
        parts = urlsplit(raw)
    except ValueError:
        return None
    host = parts.netloc.lower().split("@")[-1].split(":")[0]
    path = parts.path.rstrip("/") or "/"

    if host in _YOUTUBE_HOSTS:
        vid = None
        if host.endswith("youtu.be"):
            m = re.match(rf"^/{_YT_ID}", path)
            vid = m.group("id") if m else None
        elif path == "/watch":
            vid = (parse_qs(parts.query).get("v") or [None])[0]
            vid = vid if vid and re.fullmatch(r"[0-9A-Za-z_-]{11}", vid) else None
        else:
            for pat in _YOUTUBE_PATTERNS:
                m = pat.match(path)
                if m and m.groupdict().get("id"):
                    vid = m.group("id")
                    break
        if not vid:
            return None
        return Link("youtube", f"youtube:{vid}",
                    f"https://www.youtube.com/watch?v={vid}", resolved=True)

    if host in _TIKTOK_HOSTS or host.endswith(".tiktok.com"):
        for pat in (_TIKTOK_LONG, _TIKTOK_LONG_ALT):
            m = pat.match(path)
            if m:
                vid = m.group("id")
                return Link("tiktok", f"tiktok:{vid}",
                            f"https://www.tiktok.com/@i/video/{vid}", resolved=True)
        m = _TIKTOK_SHORT.match(path)
        if m and host in ("vm.tiktok.com", "vt.tiktok.com", "www.tiktok.com",
                          "tiktok.com", "m.tiktok.com"):
            code = m.group("code")
            # Keep the scheme+host+code and drop the query: the same share link
            # pasted by two people differs only in its `?_t=` tracking blob, so
            # dropping it is what makes the free gate actually hit.
            return Link("tiktok", f"tiktok:short:{code}",
                        f"https://{host}{path}", resolved=False)
    return None


def canonical_key(platform_hint: str, probed: dict) -> str | None:
    """The resolved key, from probe metadata. Pairs with `normalize`.

    `extractor_key` is yt-dlp's own name for the site, which is the only
    trustworthy signal that a short link landed where it claimed -- a
    `vm.tiktok.com` code that redirects off-platform must not be keyed as
    TikTok.
    """
    vid = probed.get("id")
    extractor = (probed.get("extractor_key") or probed.get("extractor") or "").lower()
    if not vid:
        return None
    if extractor.startswith("tiktok"):
        return f"tiktok:{vid}"
    if extractor.startswith("youtube"):
        return f"youtube:{vid}"
    return None


# --- 2. failure classification ---------------------------------------------
#
# DESIGN.md §7h, pointed at plumbing: **never state a reason you did not
# observe.** Every pattern below was matched against a message yt-dlp actually
# printed, or against a metadata field it actually set. Anything unmatched
# falls through to `fetch_failed`, whose message says the fetch did not go
# through and does NOT guess why.
#
# One finding worth stating because it is a trap: TikTok answers a link to a
# video that does not exist with "Your IP address is blocked from accessing
# this post" (observed 2026-09-20 against
# tiktok.com/@nonexistentuser999/video/1111111111111111111). Mapping that to
# "this video was deleted" would be inventing a reason; mapping it to "the
# platform would not serve it" is what was actually observed. Hence
# `fetch_refused`, which says exactly that and offers the upload path instead.
#
# `retryable` follows the schema's own definition -- "could re-submitting the
# same clip plausibly succeed?" -- not "is this our fault":
#   * region lock, private, deleted, over-length -> False. Nothing changes by
#     asking again.
#   * rate limit, transient network, an IP block, an unknown failure -> True.
#
# Codes reuse the existing vocabulary where it fits (`clip_too_long` is already
# named in job-status.schema.json; `pipeline_error`/`too_many_dancers`/
# `export_error` come from modal_app.py) and extend it only for situations that
# cannot happen on the upload path.

_UNAVAILABLE = "That video is not there any more. Check the link, or upload the file instead."
_PRIVATE = "That video is private, so it cannot be fetched. Upload the file instead."
_REGION = "The platform will not serve that video to where this runs. Upload the file instead."
_LOGIN = "That video needs someone signed in to watch it, so it cannot be fetched. Upload the file instead."
_LIVE = "That is a live stream, not a finished video. Try again once it has finished and been posted."
_RATE = "The platform is rate-limiting us right now. Try again in a few minutes."
_REFUSED = "The platform would not serve that video. Check the link, or upload the file instead."
_FAILED = "The fetch did not go through. Try again, or upload the file instead."

# Ordered: the first match wins, so the specific patterns precede the generic
# ones. Region and age checks must beat the bare "unavailable" match, because
# YouTube says "Video unavailable" as a prefix to both.
_RULES: list[tuple[str, tuple[str, str, bool]]] = [
    # Deliberately loose on "available in your country": YouTube's real wording
    # is "The uploader has not made this video available in your country",
    # where the negation sits ten words away from the phrase.
    (r"available in your country|blocked it in your country|"
     r"available (in|from) your (location|region)|geo[- ]?restrict|"
     r"not available in the country",
     ("video_region_locked", _REGION, False)),
    (r"confirm your age|age[- ]?restricted|inappropriate for some users",
     ("video_login_required", _LOGIN, False)),
    (r"sign in to confirm|confirm you'?re not a bot|login required|"
     r"requires authentication|use --cookies|only available to (members|subscribers)",
     ("video_login_required", _LOGIN, False)),
    (r"private video|this video is private|is a private",
     ("video_private", _PRIVATE, False)),
    (r"video unavailable|this video is unavailable|has been removed|"
     r"video has been deleted|content isn'?t available|no longer available|"
     r"account.{0,20}(terminated|closed)",
     ("video_unavailable", _UNAVAILABLE, False)),
    (r"live event will begin|is live|live stream",
     ("video_is_live", _LIVE, True)),
    (r"http error 429|too many requests|rate[- ]?limit|temporarily blocked|"
     r"slow ?down",
     ("fetch_rate_limited", _RATE, True)),
    (r"ip address is blocked|forbidden|http error 40[13]",
     ("fetch_refused", _REFUSED, True)),
]


# Every code this module can produce. api.py's retry endpoint branches on
# membership: a job that failed at one of these never got a clip into the
# uploads Volume, so retrying it means re-running the fetch, not re-spawning a
# GPU container to look for a file that was never written.
FETCH_STAGE_CODES = frozenset(
    [outcome[0] for _, outcome in _RULES] + ["fetch_failed", "clip_too_long"]
)


def classify(stderr: str) -> tuple[str, str, bool]:
    """(code, message, retryable) for a failed yt-dlp run.

    The fallthrough is the point of this function, not an afterthought: an
    opaque yt-dlp failure produces `fetch_failed` and a message that says the
    fetch did not go through, never a manufactured cause.
    """
    text = (stderr or "").lower()
    for pattern, outcome in _RULES:
        if re.search(pattern, text):
            return outcome
    return ("fetch_failed", _FAILED, True)


def too_long_error(duration_s: float) -> tuple[str, str, bool]:
    """The over-length refusal, decided from probe metadata, pre-download.

    D9 is open (refuse vs. offer a trimmer). This refuses, and says the one
    thing the learner can do about it today.
    """
    return ("clip_too_long",
            f"That video is {duration_s:.0f} seconds long and the limit is 60. "
            "Trim it to the part you want to learn and upload that.",
            False)


class FetchError(Exception):
    """Carries an already-classified job-status error."""

    def __init__(self, code: str, message: str, retryable: bool):
        super().__init__(message)
        self.code, self.message, self.retryable = code, message, retryable

    def as_job_error(self) -> dict:
        return {"code": self.code, "message": self.message, "retryable": self.retryable}


# --- 3. probe and download --------------------------------------------------

def _run(args: list[str], timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run([_YTDLP, *_BASE_ARGS, *args],
                          capture_output=True, text=True, timeout=timeout)


def probe(link: Link) -> dict:
    """Metadata only -- resolves short links and reads duration. No media bytes.

    Measured 2026-09-20: 1.8s and zero files written for a TikTok share link.
    That is what makes the over-length refusal in `check_duration` genuinely
    free, rather than a check that runs after the damage.
    """
    if not _YTDLP:
        raise FetchError("fetch_failed", _FAILED, True)
    try:
        proc = _run(["--dump-single-json", "--skip-download", "--no-warnings",
                     link.fetch_url], timeout=120)
    except subprocess.TimeoutExpired as e:
        raise FetchError("fetch_failed", _FAILED, True) from e
    if proc.returncode != 0 or not proc.stdout.strip():
        raise FetchError(*classify(proc.stderr))
    try:
        doc = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise FetchError("fetch_failed", _FAILED, True) from e
    # A playlist/channel URL that slipped past `normalize` has entries and no
    # duration of its own. Treated as unsupported rather than guessed at.
    if doc.get("_type") == "playlist" and not doc.get("duration"):
        raise FetchError("fetch_failed", _FAILED, False)
    return doc


def check_duration(probed: dict) -> None:
    """Refuse before downloading. Raises FetchError, or returns.

    A missing duration is NOT a refusal: some extractors do not report one, and
    refusing on an absent number would reject working clips for a fact we did
    not observe. MAX_FETCH_BYTES is the backstop for that case.
    """
    if probed.get("is_live") or probed.get("live_status") in ("is_live", "is_upcoming"):
        raise FetchError("video_is_live", _LIVE, True)
    duration = probed.get("duration")
    if isinstance(duration, (int, float)) and duration > MAX_DURATION_S:
        raise FetchError(*too_long_error(float(duration)))


def download(link: Link, dest_path: str) -> None:
    """Fetch the media to `dest_path`. The only step that costs bandwidth.

    Format capped at 1080p, matching evaluation/fetch.py: the pipeline
    normalises to that anyway, and TikTok serves 576x1024 regardless
    (evaluation/clips.yaml's 2026-09-18 resolution finding).
    """
    if not _YTDLP:
        raise FetchError("fetch_failed", _FAILED, True)
    try:
        proc = _run([
            "-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
            "--merge-output-format", "mp4",
            "--max-filesize", str(MAX_FETCH_BYTES),
            "--no-warnings", "-o", dest_path, link.fetch_url,
        ], timeout=900)
    except subprocess.TimeoutExpired as e:
        raise FetchError("fetch_failed", _FAILED, True) from e
    if proc.returncode != 0:
        raise FetchError(*classify(proc.stderr))
    if not os.path.exists(dest_path) or os.path.getsize(dest_path) == 0:
        # yt-dlp exits 0 when --max-filesize aborts the download, so an
        # apparent success with no file is the size backstop firing.
        raise FetchError("clip_too_long",
                         "That video is too large to fetch. Upload the file instead.",
                         False)


# --- 4. the invite gate -----------------------------------------------------
#
# The simplest thing that is credible without D5 (accounts), which is open.
#
# `STEPWISE_INVITE_CODES` is a comma-separated allowlist read from the
# environment. **Unset means link ingestion is off**, not open -- failing
# closed is the only safe default for the one path that fetches other people's
# content, and it means a fresh deploy cannot accidentally be a public
# downloader. File upload is not gated by any of this and stays open.
#
# What it protects against: a stranger finding the site and pasting links into
# it. That is the entire scenario docs/research/link-ingestion.md §5 is about,
# and for the invite-only pilot it is enough.
#
# What it does NOT protect against, stated plainly because a gate that is
# oversold is worse than none:
#   * A code is a shared secret. One tester forwarding it to a group chat
#     re-opens the door, and nothing here would show that it happened.
#   * There is no identity behind a code, so there is no per-person rate limit,
#     no audit of who ingested what, and no way to terminate one user without
#     rotating a code everyone shares. That is D5, and it is open.
#   * Rotation is an env change plus a restart. There is no revocation list.
#   * It is not a legal exemption of any kind. See link-ingestion.md §4.


def invite_codes() -> set[str]:
    raw = os.environ.get("STEPWISE_INVITE_CODES", "")
    return {c.strip() for c in raw.split(",") if c.strip()}


def invite_ok(code: str | None) -> bool:
    codes = invite_codes()
    return bool(codes) and (code or "").strip() in codes
