"""observability.py: nothing identifying leaves the process, and the release is set.

The end-to-end test drives a real FastAPI app through sentry_sdk's real
integrations into an in-memory transport, and asserts on the serialised
envelope -- the bytes that would have gone to Sentry -- not on what
`scrub()` returns. A scrubber that works but is never called is the failure
this file exists to catch.
"""

import json

import pytest

import observability

TIKTOK = "https://www.tiktok.com/@some.dancer/video/7301234567890123456?lang=en"
PRESIGNED = ("https://acct.r2.cloudflarestorage.com/stepwise/clips/abc.glb"
             "?X-Amz-Signature=deadbeef&X-Amz-Credential=AKIA123")


@pytest.mark.parametrize("raw, leaked", [
    (f"yt-dlp failed for {TIKTOK}", ["tiktok.com", "some.dancer", "7301234567890123456"]),
    (f"GET {PRESIGNED} -> 403", ["X-Amz-Signature", "deadbeef", "AKIA123"]),
    ("could not fetch youtu.be/dQw4w9WgXcQ", ["dQw4w9WgXcQ"]),
    ("ERROR: [youtube] dQw4w9WgXcQ: Video unavailable", ["dQw4w9WgXcQ"]),
    ("[dedupe] url hit: tiktok:7301234567890123456", ["7301234567890123456"]),
    ("reported by someone@example.com", ["someone@example.com"]),
    ("reposted from @some.dancer", ["some.dancer"]),
])
def test_scrub_text_removes_identifiers(raw, leaked):
    out = observability.scrub_text(raw)
    for s in leaked:
        assert s not in out, out


def test_scrub_keeps_code_locations_and_plain_messages():
    frame = {"context_line": "@app.function(image=cv_image)", "filename": "modal_app.py",
             "vars": {"u": TIKTOK}}
    out = observability.scrub(frame)
    assert out["context_line"] == frame["context_line"]
    assert "tiktok" not in json.dumps(out)
    assert observability.scrub_text("CUDA out of memory (clip 3f2a)") == "CUDA out of memory (clip 3f2a)"


def test_init_is_a_noop_without_a_dsn(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    monkeypatch.delenv("SENTRY_DSN_BACKEND", raising=False)
    monkeypatch.setattr(observability, "_initialised", False)
    assert observability.init("web") is False
    observability.capture(RuntimeError("x"), "run_clip")  # must not raise


@pytest.fixture
def sent(monkeypatch):
    """Initialise for real, with the network swapped for a list."""
    sentry_sdk = pytest.importorskip("sentry_sdk")
    from sentry_sdk.transport import Transport

    envelopes = []

    class Capture(Transport):
        def capture_envelope(self, envelope):
            envelopes.append(envelope.serialize().decode())

    real_init = sentry_sdk.init
    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: real_init(transport=Capture(kw), **kw))
    monkeypatch.setenv("SENTRY_DSN_BACKEND", "https://public@o0.ingest.sentry.invalid/1")
    monkeypatch.setenv("STEPWISE_GIT_SHA", "92d508fabc")
    monkeypatch.setattr(observability, "_initialised", False)
    yield envelopes
    sentry_sdk.get_client().close()
    monkeypatch.setattr(observability, "_initialised", False)


def test_capture_sends_scrubbed_event_with_release_and_tags(sent):
    link = TIKTOK

    try:
        raise RuntimeError(f"pipeline died on {link}")
    except RuntimeError as e:
        observability.capture(e, "run_clip", stage="reconstruct", clip_id="c0ffee", job_id="job_1")

    body = "\n".join(sent)
    assert "RuntimeError" in body and "pipeline died on [url]" in body
    assert '"release":"92d508fabc"' in body.replace(" ", "")
    assert "c0ffee" in body and "reconstruct" in body
    for leak in ("tiktok.com", "some.dancer", "7301234567890123456"):
        assert leak not in body


def _asgi_post(app, path, query, payload):
    """One raw ASGI request. Starlette's TestClient needs httpx, which CI does
    not install for this suite, and a 500 needs nothing that TestClient adds."""
    import asyncio

    body = json.dumps(payload).encode()
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
             "method": "POST", "scheme": "http", "path": path, "raw_path": path.encode(),
             "query_string": query.encode(), "root_path": "",
             "headers": [(b"content-type", b"application/json"),
                         (b"content-length", str(len(body)).encode())],
             "client": ("127.0.0.1", 1), "server": ("testserver", 80)}
    messages = [{"type": "http.request", "body": body, "more_body": False}]
    status = {}

    async def receive():
        return messages.pop(0) if messages else {"type": "http.disconnect"}

    async def send(msg):
        if msg["type"] == "http.response.start":
            status["code"] = msg["status"]

    async def run():
        try:
            await app(scope, receive, send)
        except ValueError:
            pass  # ServerErrorMiddleware re-raises after sending the 500

    asyncio.run(run())
    return status.get("code")


def test_fastapi_errors_reach_sentry_scrubbed(sent):
    fastapi = pytest.importorskip("fastapi")

    assert observability.init("web")
    app = fastapi.FastAPI()

    @app.post("/clips/link")
    def ingest(payload: dict):
        raise ValueError(f"extractor failed for {payload['url']}")

    assert _asgi_post(app, "/clips/link", f"src={PRESIGNED}", {"url": TIKTOK}) == 500

    import sentry_sdk
    sentry_sdk.flush()
    body = "\n".join(sent)
    assert "ValueError" in body, "the ASGI integration never reported the 500"
    for leak in ("tiktok.com", "some.dancer", "X-Amz-Signature", "AKIA123"):
        assert leak not in body, leak
