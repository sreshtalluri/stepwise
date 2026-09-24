"""Sentry for the backend: the GPU worker, the sweeper and the ASGI app.

Why this exists at all: Modal Starter keeps logs for ONE day. Without an error
tracker, the reason a job failed is gone before anyone reports it
(docs/DEPLOYMENT.md §5.3).

Three rules, all enforced here rather than trusted to each call site:

1. **Off unless configured.** No DSN in the environment (a laptop, CI, a Modal
   deploy before `stepwise-sentry` exists) means every function below is a
   no-op. `sentry_sdk` missing from an image is the same no-op, not an
   ImportError that takes the job down with it.

2. **No source links leave this process.** A pasted TikTok/YouTube URL
   identifies the person who pasted it, and a presigned R2 URL carries a live
   signature. Both turn up in exception messages (yt-dlp, boto3, httpx) and in
   request data. `scrub()` runs over the WHOLE event just before it is sent --
   messages, exception values, breadcrumbs, request, extra, contexts -- because
   an allowlist of fields to clean is exactly the kind of list that misses the
   one field that leaks. Local variables are not captured at all: a frame's
   locals in ingest.py are the URL.

3. **Every event names the deployed commit.** `release` is `STEPWISE_GIT_SHA`,
   injected by modal_app.py at `modal deploy` time. That is also what exposes
   the warm-container trap (DEPLOYMENT.md §7.1): an error tagged with the
   PREVIOUS sha after a deploy means a container outlived the deploy.
"""

from __future__ import annotations

import os
import re

_initialised = False

# Order matters: whole URLs first, so the bare-domain pattern never sees half
# of one.
_PATTERNS = [
    # Anything with a scheme. Covers presigned R2 URLs and every pasted link.
    (re.compile(r"\b[a-zA-Z][a-zA-Z0-9+.-]*://[^\s'\"<>]+"), "[url]"),
    # Schemeless links as people paste them: tiktok.com/@name/video/123,
    # youtu.be/abc, www.instagram.com/reel/...
    (re.compile(r"\b(?:www\.)?[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*\.(?:com|be|net|org|io|tv|app|ly|co)/[^\s'\"<>]*"),
     "[url]"),
    # yt-dlp's own error shape: "ERROR: [youtube] dQw4w9WgXcQ: Video unavailable"
    # -- the video id alone is the link.
    (re.compile(r"\[([a-z0-9_:]+)\] [A-Za-z0-9_-]{4,}:"), r"[\1] [id]:"),
    # ingest.py's canonical source key, "<extractor>:<id>" (e.g. tiktok:7301..).
    (re.compile(r"\b(youtube|tiktok|instagram|vimeo|twitter|x|facebook)(?::[a-z]+)?:[A-Za-z0-9_-]+"),
     r"\1:[id]"),
    # Email addresses, then @handles (TikTok/Instagram usernames).
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[email]"),
    (re.compile(r"(?<![\w/])@[\w.]{2,}"), "[handle]"),
]


def scrub_text(s: str) -> str:
    for pattern, repl in _PATTERNS:
        s = pattern.sub(repl, s)
    return s


# Stack-frame fields that are this repo's own source, never user data. Left
# alone so a traceback still reads as code (`@app.function` is a decorator,
# not a TikTok handle).
_CODE_KEYS = frozenset({"context_line", "pre_context", "post_context",
                        "filename", "abs_path", "module", "function"})


def scrub(value):
    """Return `value` with every string in it scrubbed, at any depth."""
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, dict):
        return {k: v if k in _CODE_KEYS else scrub(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(scrub(v) for v in value)
    return value


def _before_send(event, _hint):
    return scrub(event)


def _before_breadcrumb(crumb, _hint):
    return scrub(crumb)


def _before_send_log(log, _hint):
    return scrub(log)


def _dsn() -> str | None:
    # sentry.env holds one DSN per project; the backend reads its own and falls
    # back to the generic name so a single-key Secret also works.
    return os.environ.get("SENTRY_DSN_BACKEND") or os.environ.get("SENTRY_DSN") or None


def init(component: str) -> bool:
    """Initialise once per process. Returns whether Sentry is actually on.

    Must run BEFORE the FastAPI app is imported for the ASGI integration to
    attach -- sentry_sdk auto-enables its Starlette/FastAPI integrations at
    init and patches the app class, not an existing instance.
    """
    global _initialised
    if _initialised:
        return True
    dsn = _dsn()
    if not dsn:
        return False
    try:
        import sentry_sdk
    except ImportError:
        print(f"[sentry] {component}: SENTRY_DSN set but sentry_sdk not installed -- errors stay local")
        return False

    sentry_sdk.init(
        dsn=dsn,
        release=os.environ.get("STEPWISE_GIT_SHA") or None,
        environment=os.environ.get("MODAL_ENVIRONMENT") or os.environ.get("STEPWISE_ENV") or "local",
        send_default_pii=False,
        include_local_variables=False,
        max_request_body_size="never",
        # Tracing only where there are requests to trace. The GPU worker is one
        # long span per job and the sweeper is one per day; neither teaches
        # anything a free-tier span budget is worth spending on.
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1")) if component == "web" else 0.0,
        enable_logs=True,
        before_send=_before_send,
        before_send_transaction=_before_send,
        before_breadcrumb=_before_breadcrumb,
        before_send_log=_before_send_log,
    )
    sentry_sdk.set_tag("component", component)
    _initialised = True
    return True


def capture(exc: BaseException, component: str, level: str = "error", **tags) -> None:
    """Report `exc` and flush before returning.

    The flush is the point: this is called from `except` branches that
    re-raise, and a Modal container can be torn down the moment the function
    exits. An unflushed event on a dead container is an event that never
    happened.
    """
    if not init(component):
        return
    import sentry_sdk

    with sentry_sdk.new_scope() as scope:
        scope.set_level(level)
        for k, v in tags.items():
            if v is not None:
                scope.set_tag(k, str(v))
        sentry_sdk.capture_exception(exc)
    sentry_sdk.flush(timeout=5)
