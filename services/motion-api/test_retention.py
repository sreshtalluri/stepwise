"""The one runnable check for the dedupe / retention / takedown path.

Runs the real api.py handlers against an in-memory stand-in for a Modal
Volume, because the things worth checking are all about *which bytes survive*,
and that question does not need a GPU, a network or a deployed app:

  * a re-encode of an already-reconstructed clip does not start a second GPU run
  * a removal actually deletes everything, with nothing left individually fetchable
  * an expired lesson deletes exactly what a takedown deletes
  * a removed lesson answers 410, and never dedupes back into existence

    python3 -m pytest test_retention.py -q
"""
from __future__ import annotations

import io
import json
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

# The starlette Request the dispatch handlers read the client IP from. These
# tests run the Volume backend, where the rate limiter allows without looking.
NO_REQUEST = types.SimpleNamespace(headers={}, client=None)


class FakeDict(dict):
    """modal.Dict's first-write-wins put, over a plain dict."""

    def put(self, key, value, skip_if_exists=False):
        if skip_if_exists and key in self:
            return False
        self[key] = value
        return True


def _removal(api, relationship="i_am_in_it", reason=""):
    return api.RemovalRequest(relationship=relationship, reason=reason)


class InvalidError(Exception):
    """Stands in for modal.exception.InvalidError."""


class FakeVolume:
    """Enough of modal.Volume for these handlers: the parts that move bytes."""

    def __init__(self, name):
        self.name = name
        self.files: dict[str, bytes] = {}
        self.committed = 0

    # -- reads
    def read_file_into_fileobj(self, path, buf):
        data = self.files.get(path if path.startswith("/") else "/" + path)
        if data is None:
            raise FileNotFoundError(path)
        buf.write(data)

    def listdir(self, path, *, recursive=False):
        return [types.SimpleNamespace(path=p.lstrip("/"), mtime=0, size=len(v))
                for p, v in self.files.items()]

    # -- writes
    def batch_upload(self, force=False):
        vol = self

        class _Batch:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *a):
                return False

            def put_file(self_inner, local, remote):
                vol.files[remote] = Path(local).read_bytes()

        return _Batch()

    def remove_file(self, path, recursive=False):
        if path not in self.files:
            # What the real client raises for a missing file -- NOT
            # FileNotFoundError (measured, modal 1.5.5). Faking the friendlier
            # one hid a removal that aborted at the first absent artifact.
            raise InvalidError("No such file or directory.")
        del self.files[path]

    def commit(self):
        # Matches the real client: modal.Volume.commit() raises unless the
        # volume is MOUNTED inside a container. Faking it as a no-op hid a
        # real bug once -- the removal endpoint called commit() and would have
        # returned a 500 after successfully deleting the lesson.
        raise RuntimeError("commit() can only be called on a mounted volume inside a container")


@pytest.fixture()
def api(monkeypatch):
    """Import api.py with modal stubbed out, then point it at fresh volumes."""
    fake_modal = types.ModuleType("modal")
    fake_modal.Volume = types.SimpleNamespace(from_name=lambda *a, **k: FakeVolume(a[0]))
    spawned: list[dict] = []
    # `spawned` records GPU runs only; the CPU beat proposal spawned beside
    # each one hands back a call id for run_clip to collect.
    fake_modal.Function = types.SimpleNamespace(
        from_name=lambda app, name, **k: types.SimpleNamespace(
            spawn=lambda **kw: types.SimpleNamespace(object_id=f"fc-{name}")))
    # run_clip runs as Reconstructor.run; run_when_handed is the ingest-time
    # pre-warm, which takes its job through the `stepwise-gpu-handoff` Dict.
    prewarmed: list[str] = []
    handoff = FakeDict()
    fake_modal.Dict = types.SimpleNamespace(from_name=lambda *a, **k: handoff)
    fake_modal.Cls = types.SimpleNamespace(
        from_name=lambda app, name, **k: lambda: types.SimpleNamespace(
            run=types.SimpleNamespace(spawn=lambda **kw: spawned.append(kw) or types.SimpleNamespace(
                object_id=f"fc-run-{len(spawned)}")),
            run_when_handed=types.SimpleNamespace(spawn=prewarmed.append)))
    cancelled: list[str] = []
    fake_modal.FunctionCall = types.SimpleNamespace(
        from_id=lambda call_id: types.SimpleNamespace(cancel=lambda: cancelled.append(call_id)))
    monkeypatch.setitem(sys.modules, "modal", fake_modal)
    for mod in ("api", "retention", "motion_result", "fingerprint"):
        sys.modules.pop(mod, None)
    import api as api_mod
    api_mod.uploads_volume = FakeVolume("uploads")
    api_mod.results_volume = FakeVolume("results")
    api_mod.eval_volume = FakeVolume("eval")
    api_mod._TOUCHED.clear()
    api_mod._spawned = spawned
    api_mod._prewarmed, api_mod._handoff_dict = prewarmed, handoff
    api_mod._cancelled = cancelled
    return api_mod


def _seed_lesson(api, clip_id, job_id, fp=None):
    """A finished lesson, exactly as run_clip + export_clip_gltf leave one."""
    import retention
    api.uploads_volume.files[f"/{clip_id}.mp4"] = b"video-bytes"
    r = api.results_volume.files
    r[f"/{clip_id}_track1.glb"] = b"glb-bytes-1"
    r[f"/{clip_id}_track2.glb"] = b"glb-bytes-2"
    r[f"/{clip_id}.motion-result.json.gz"] = b"gz"
    r[f"/{clip_id}.export-manifest.json"] = b"{}"
    r[f"/{clip_id}.performance.json"] = b"{}"
    # Derived from the audio of the person's video, so it must go with the rest.
    r[f"/{clip_id}.beats.json"] = b"{}"
    r[f"/{job_id}.job-meta.json"] = json.dumps({"clip_id": clip_id}).encode()
    r[f"/{job_id}.job-status.json"] = json.dumps({
        "schema_version": "1.0.0", "job_id": job_id, "state": "succeeded",
        "stage_message": "", "progress": 1.0, "error": None, "retry_count": 0,
    }).encode()
    if fp:
        retention.write_index(api.results_volume,
                              [dict(fp, clip_id=clip_id, job_id=job_id, created_at=0)])


# --------------------------------------------------------------------------
# takedown
# --------------------------------------------------------------------------

def test_removal_deletes_every_artifact(api):
    _seed_lesson(api, "abc", "job_abc")
    api.results_volume.files["/abc.npz"] = b"npz-bytes"
    api.results_volume.files["/abc.last-access.json"] = b'{"at": 0}'

    out = api.remove_lesson("abc", _removal(api, reason="i am in this video"), NO_REQUEST)

    survivors = [p for p in api.results_volume.files if "abc" in p]
    assert survivors == ["/abc.removed.json"], survivors
    assert api.uploads_volume.files == {}, "the source video must not survive a removal"
    assert len(out.removed) >= 8

    tomb = json.loads(api.results_volume.files["/abc.removed.json"])
    assert set(tomb) == {"clip_id", "removed_at", "reason", "relationship"}, \
        "the tombstone must hold nothing derived from the video"
    assert tomb["relationship"] == "i_am_in_it" and tomb["reason"] == "i am in this video"


def test_removal_by_job_id_resolves_the_canonical_clip(api):
    # The web only knows the job_id in its /lesson/{job_id} link.
    _seed_lesson(api, "abc", "job_abc")
    api.results_volume.files["/job_legacy.job-meta.json"] = json.dumps({"clip_id": "abc"}).encode()
    out = api.remove_lesson_by_job("job_legacy", _removal(api), NO_REQUEST)
    assert out.clip_id == "abc"
    assert "/abc.removed.json" in api.results_volume.files
    assert api.uploads_volume.files == {}


def test_removal_request_requires_a_relationship_and_caps_the_reason(api):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        api.RemovalRequest(reason="no box ticked")
    with pytest.raises(ValidationError):
        api.RemovalRequest(relationship="lawyer")
    with pytest.raises(ValidationError):
        api.RemovalRequest(relationship="other", reason="x" * 501)


def test_removal_boxes_match_the_dialog(api):
    """Every box RemoveLessonDialog offers (lib/copy.ts removal.relationships)
    is one the API accepts, and the reverse -- "under 18" included."""
    import re
    import typing
    copy = (Path(__file__).resolve().parents[2] / "apps/web/lib/copy.ts").read_text()
    block = re.search(r"relationships: \{(.*?)\}", copy, re.S).group(1)
    offered = set(re.findall(r"^\s*(\w+):", block, re.M))
    accepted = set(typing.get_args(api.RemovalRequest.model_fields["relationship"].annotation))
    assert offered == accepted and "under_18" in accepted


def test_removal_alerts_the_owner_without_the_reason(api, monkeypatch):
    sent = []
    monkeypatch.setattr(api.observability, "message",
                        lambda text, component, **kw: sent.append((text, component, kw)))
    _seed_lesson(api, "abc", "job_abc")
    api.remove_lesson("abc", _removal(api, "i_own_the_rights", "my name is Jo, @jo.dances"), NO_REQUEST)
    assert sent == [("lesson removed", "web",
                     {"level": "warning", "relationship": "i_own_the_rights", "clip_id": "abc"})]
    api.remove_lesson("abc", _removal(api), NO_REQUEST)
    assert len(sent) == 1, "an already-removed lesson is not a second alert"


def test_removed_lesson_is_410_not_404_and_assets_are_gone(api):
    from fastapi import HTTPException
    _seed_lesson(api, "abc", "job_abc")
    api.remove_lesson("abc", _removal(api), NO_REQUEST)

    for call in (lambda: api.get_job_status("job_abc"),
                 lambda: api.get_job_result("job_abc"),
                 lambda: api.get_asset("video:abc"),
                 lambda: api.get_asset("abc_track1.glb")):
        with pytest.raises(HTTPException) as e:
            call()
        assert e.value.status_code == 410, f"expected 410 Gone, got {e.value.status_code}"


def test_removal_is_idempotent(api):
    _seed_lesson(api, "abc", "job_abc")
    api.remove_lesson("abc", _removal(api), NO_REQUEST)
    again = api.remove_lesson("abc", _removal(api), NO_REQUEST)
    assert again.removed == []


# --------------------------------------------------------------------------
# dedupe
# --------------------------------------------------------------------------

def test_dedupe_reuses_the_canonical_lesson(api):
    fp = {"sha256": "f" * 64, "duration_s": 20.0, "frames": 4,
          "ahash": "0" * 64, "dhash": "0" * 64}
    _seed_lesson(api, "abc", "job_abc", fp)
    hit = api._find_existing(dict(fp))
    assert hit and hit["clip_id"] == "abc"


def test_dedupe_never_resurrects_a_removed_lesson(api):
    fp = {"sha256": "f" * 64, "duration_s": 20.0, "frames": 4,
          "ahash": "0" * 64, "dhash": "0" * 64}
    _seed_lesson(api, "abc", "job_abc", fp)
    api.remove_lesson("abc", _removal(api), NO_REQUEST)
    assert api._find_existing(dict(fp)) is None, \
        "a re-upload must never be pointed at a lesson that was taken down"


def test_dedupe_skips_a_job_that_did_not_succeed(api):
    fp = {"sha256": "f" * 64, "duration_s": 20.0, "frames": 4,
          "ahash": "0" * 64, "dhash": "0" * 64}
    _seed_lesson(api, "abc", "job_abc", fp)
    api.results_volume.files["/job_abc.job-status.json"] = json.dumps({
        "schema_version": "1.0.0", "job_id": "job_abc", "state": "failed",
        "stage_message": "", "progress": None,
        "error": {"code": "pipeline_error", "message": "x", "retryable": True},
        "retry_count": 0}).encode()
    assert api._find_existing(dict(fp)) is None


def test_removal_drops_the_fingerprint_entry(api):
    import retention
    fp = {"sha256": "f" * 64, "duration_s": 20.0, "frames": 4,
          "ahash": "0" * 64, "dhash": "0" * 64}
    _seed_lesson(api, "abc", "job_abc", fp)
    api.remove_lesson("abc", _removal(api), NO_REQUEST)
    assert retention.read_index(api.results_volume) == [], \
        "the content fingerprint is derived from the video and must go with it"


# --------------------------------------------------------------------------
# the two deletion paths must agree
# --------------------------------------------------------------------------

def test_expiry_and_takedown_delete_the_same_set(api):
    import retention
    listing = ["abc.npz", "abc_track1.glb", "abc_track2.glb",
               "abc.motion-result.json.gz", "abc.export-manifest.json",
               "abc.performance.json", "abc.beats.json", "abc.last-access.json",
               "job_abc.job-status.json", "job_abc.job-meta.json",
               "other_track1.glb"]
    paths = retention.clip_artifact_paths(listing, "abc", "job_abc")
    flat = set(paths["uploads"]) | set(paths["results"])
    assert "/other_track1.glb" not in flat, "must not delete another lesson's dancer"
    for expected in ("/abc.mp4", "/abc.npz", "/abc_track1.glb", "/abc_track2.glb",
                     "/abc.motion-result.json.gz", "/abc.export-manifest.json",
                     "/abc.performance.json", "/abc.beats.json", "/abc.detections.json",
                     "/abc.last-access.json", "/job_abc.job-status.json", "/job_abc.job-meta.json"):
        assert expected in flat, f"{expected} would survive deletion"


def test_ttl_boundary():
    import retention
    now = 1_000_000_000.0
    day = 86400
    assert not retention.is_expired(now - (retention.TTL_DAYS - 1) * day, now)
    assert retention.is_expired(now - (retention.TTL_DAYS + 1) * day, now)


# --------------------------------------------------------------------------
# the whole upload path, with a real video
# --------------------------------------------------------------------------

def test_reuploading_a_reencode_starts_no_gpu_job(api, tmp_path):
    """The point of the whole exercise: a re-encode costs no GPU.

    Runs the real `upload_clip` handler twice -- once with a clip, once with a
    genuine ffmpeg re-encode of it -- and checks that the second upload spawns
    nothing, stores no second video, and hands back the first lesson.
    """
    import asyncio
    import os
    import subprocess

    import fingerprint

    if not fingerprint.ffmpeg_available():
        pytest.skip("needs ffmpeg")
    src_dir = os.environ.get("STEPWISE_FP_CLIPS")
    clips = (sorted(Path(src_dir).glob("*.mp4")) if src_dir and os.path.isdir(src_dir) else [])
    if not clips:
        original = tmp_path / "synth.mp4"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                        "testsrc2=size=320x568:rate=30:duration=8,rotate=t/3",
                        "-c:v", "libx264", "-crf", "20", str(original)], check=True)
    else:
        original = clips[0]

    reencoded = tmp_path / "reencoded.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(original),
                    "-c:v", "libx264", "-crf", "31", "-preset", "veryfast",
                    "-an", str(reencoded)], check=True)

    class _Upload:
        def __init__(self, path):
            self._f = open(path, "rb")

        async def read(self, n):
            return self._f.read(n)

    first = asyncio.run(api.upload_clip(NO_REQUEST, _Upload(original)))
    assert first.deduplicated is False
    assert len(api._spawned) == 1, "the first upload must actually run the pipeline"

    # Mark it finished, the way run_clip would.
    api.results_volume.files[f"/{first.job_id}.job-status.json"] = json.dumps({
        "schema_version": "1.0.0", "job_id": first.job_id, "state": "succeeded",
        "stage_message": "", "progress": 1.0, "error": None, "retry_count": 0,
    }).encode()

    second = asyncio.run(api.upload_clip(NO_REQUEST, _Upload(reencoded)))
    assert second.deduplicated is True, "a re-encode must not be reconstructed again"
    assert second.clip_id == first.clip_id and second.job_id == first.job_id
    assert len(api._spawned) == 1, "no second GPU job may be dispatched"
    assert len(api.uploads_volume.files) == 1, "no second copy of the video may be stored"

    # And the removal is therefore complete for BOTH uploaders at once.
    api.remove_lesson(second.clip_id, _removal(api), NO_REQUEST)
    assert api.uploads_volume.files == {}


def test_unknown_job_is_404_but_a_just_dispatched_one_is_queued(api):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        api.get_job_status("job_never_existed")
    assert e.value.status_code == 404
    # Dispatched (job-meta written) but the worker has not written status yet.
    api.results_volume.files["/job_fresh.job-meta.json"] = b'{"clip_id": "fresh"}'
    assert api.get_job_status("job_fresh")["state"] == "queued"


def test_stored_result_is_served_as_is_and_validated_once(api, monkeypatch):
    from fastapi import HTTPException
    import gzip
    from pathlib import Path
    fixture = Path(__file__).resolve().parents[2] / "packages/motion-contract/fixtures/good-lesson.json"
    doc = json.loads(fixture.read_text())
    job_id = doc["job_id"]
    _seed_lesson(api, "good", job_id)
    stored = gzip.compress(json.dumps(doc).encode())
    api.results_volume.files["/good.motion-result.json.gz"] = stored
    api.results_volume.files[f"/{job_id}.job-status.json"] = json.dumps({
        "schema_version": "1.0.0", "job_id": job_id, "state": "succeeded", "stage_message": "",
        "progress": 1.0, "error": None, "retry_count": 0}).encode()
    api._PRIMED.add(job_id)  # no background thread in a test
    calls = []
    real = api.validate_motion_result
    monkeypatch.setattr(api, "validate_motion_result", lambda d: calls.append(1) or real(d))

    for _ in range(2):
        resp = api.get_job_result(job_id)
        assert resp.body == stored and resp.headers["content-encoding"] == "gzip"
    assert len(calls) == 1, "validated on every open again"

    # A contract-invalid stored document is still refused, never served.
    api.results_volume.files["/good.motion-result.json.gz"] = gzip.compress(b'{"persons": 3}')
    with pytest.raises(HTTPException) as e:
        api.get_job_result(job_id)
    assert e.value.status_code == 500


def test_result_validated_at_export_is_a_redirect_with_no_revalidation(api, monkeypatch):
    """A cold replica must not re-validate what export already validated (the
    20-30 s "second wait" after Start learning): R2 metadata `validated: <job_id>`
    is trusted, anything else takes the validating byte path."""
    job_id = "job_marked"
    _seed_lesson(api, "marked", job_id)
    api.results_volume.files[f"/{job_id}.job-status.json"] = json.dumps({
        "schema_version": "1.0.0", "job_id": job_id, "state": "succeeded", "stage_message": "",
        "progress": 1.0, "error": None, "retry_count": 0}).encode()
    api._PRIMED.add(job_id)
    metadata = {"validated": job_id}
    monkeypatch.setattr(api.storage, "enabled", lambda: True)
    monkeypatch.setattr(api.storage, "client", lambda: types.SimpleNamespace(
        head_object=lambda **kw: {"Metadata": metadata}))
    monkeypatch.setattr(api.storage, "bucket", lambda: "b")
    monkeypatch.setattr(api.storage, "url_for", lambda key: f"https://r2.example/{key}?sig")
    monkeypatch.setattr(api, "validate_motion_result", lambda d: pytest.fail("re-validated"))

    resp = api.get_job_result(job_id)
    assert resp.status_code == 302
    assert resp.headers["location"] == "https://r2.example/motion-result/marked.json.gz?sig"

    # Marked for a different job (a deduplicated upload): not trusted. Fresh
    # replica, since this one already remembers the verdict for job_marked.
    metadata["validated"] = "job_someone_else"
    api._R2_VALIDATED.clear()
    assert api._validated_r2_url(job_id, "marked") is None


def _marked_in_r2(api, monkeypatch, clip_id, job_id):
    """A finished lesson whose R2 MotionResult export marked validated; returns
    the list head_object appends to, so a test can count R2 round trips."""
    _seed_lesson(api, clip_id, job_id)
    api._PRIMED.add(job_id)
    heads = []
    monkeypatch.setattr(api.storage, "enabled", lambda: True)
    monkeypatch.setattr(api.storage, "client", lambda: types.SimpleNamespace(
        head_object=lambda **kw: heads.append(kw) or {"Metadata": {"validated": job_id}}))
    monkeypatch.setattr(api.storage, "bucket", lambda: "b")
    monkeypatch.setattr(api.storage, "url_for", lambda key: f"https://r2.example/{key}?sig")
    return heads


def test_cached_success_is_still_410_after_a_removal_on_another_replica(api, monkeypatch):
    """/result caches "succeeded" and the R2 verdict per replica. A removal
    handled by a DIFFERENT replica clears none of that, so the tombstone must
    still be read on every request."""
    import retention
    from fastapi import HTTPException
    heads = _marked_in_r2(api, monkeypatch, "abc", "job_abc")
    assert api.get_job_result("job_abc").status_code == 302
    assert api.get_job_result("job_abc").status_code == 302
    assert len(heads) == 1, "the R2 verdict is cached per replica"

    retention.delete_clip(api.uploads_volume, api.results_volume, "abc", "job_abc", "", "i_am_in_it")
    with pytest.raises(HTTPException) as e:
        api.get_job_result("job_abc")
    assert e.value.status_code == 410


def test_result_redirect_records_the_access_after_responding(api, monkeypatch):
    """The last-access write is a BackgroundTask: still recorded (it is the
    retention clock), but no longer between the learner and the 302."""
    import asyncio
    _marked_in_r2(api, monkeypatch, "abc", "job_abc")
    touch = "/abc.last-access.json"
    seen = {}

    async def send(msg):
        if msg["type"] == "http.response.start":
            seen["status"] = msg["status"]
            seen["touched_before_response"] = touch in api.results_volume.files

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    path = "/jobs/job_abc/result"
    asyncio.run(api.app({"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                         "method": "GET", "scheme": "http", "path": path, "raw_path": path.encode(),
                         "query_string": b"", "root_path": "", "headers": [],
                         "client": ("127.0.0.1", 1), "server": ("testserver", 80)}, receive, send))
    assert seen == {"status": 302, "touched_before_response": False}
    assert touch in api.results_volume.files


def test_removed_mid_run_status_written_after_removal_is_410_and_not_retryable(api):
    """job_6037...: the lesson was removed while its job ran, and the worker then
    wrote a final `failed` status after delete_clip. Status and retry must both
    answer removed -- retry must never re-run the GPU on a taken-down lesson."""
    from fastapi import HTTPException
    _seed_lesson(api, "abc", "job_abc")
    api.remove_lesson("abc", _removal(api), NO_REQUEST)
    api.results_volume.files["/job_abc.job-meta.json"] = json.dumps({"clip_id": "abc"}).encode()
    api.results_volume.files["/job_abc.job-status.json"] = json.dumps({
        "schema_version": "1.0.0", "job_id": "job_abc", "state": "failed",
        "stage_message": "", "progress": 0.5, "retry_count": 0,
        "error": {"code": "export_error", "message": "x", "retryable": True}}).encode()
    for call in (lambda: api.get_job_status("job_abc"),
                 lambda: api.retry_job("job_abc", NO_REQUEST)):
        with pytest.raises(HTTPException) as e:
            call()
        assert e.value.status_code == 410


def test_finished_status_rechecks_removal_after_the_cache_window(api, monkeypatch):
    """The not-removed verdict is cached per replica, so a finished job's polls
    stay cheap; a removal on ANOTHER replica is seen once the window passes."""
    import retention
    from fastapi import HTTPException
    _seed_lesson(api, "abc", "job_abc")
    assert api.get_job_status("job_abc")["state"] == "succeeded"
    retention.delete_clip(api.uploads_volume, api.results_volume, "abc", "job_abc", "", "i_am_in_it")
    api.results_volume.files["/job_abc.job-status.json"] = json.dumps({
        "schema_version": "1.0.0", "job_id": "job_abc", "state": "succeeded",
        "stage_message": "", "progress": 1.0, "error": None, "retry_count": 0}).encode()
    monkeypatch.setattr(api, "_REMOVAL_CHECK_S", 0.0)
    with pytest.raises(HTTPException) as e:
        api.get_job_status("job_abc")
    assert e.value.status_code == 410


# --------------------------------------------------------------------------
# job_6037: nothing may write a lesson after its removal
# --------------------------------------------------------------------------

class FakeR2:
    """Enough of the S3 client for storage.list_keys / delete / head."""

    def __init__(self, keys=()):
        self.objects = {k: {} for k in keys}

    def get_paginator(self, _name):
        r2 = self
        return types.SimpleNamespace(paginate=lambda Bucket, Prefix: [
            {"Contents": [{"Key": k} for k in sorted(r2.objects) if k.startswith(Prefix)]}])

    def delete_object(self, Bucket, Key):
        self.objects.pop(Key, None)

    def head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise FileNotFoundError(Key)
        return {"Metadata": self.objects[Key]}


@pytest.fixture()
def r2(monkeypatch):
    import storage
    fake = FakeR2()
    monkeypatch.setattr(storage, "enabled", lambda: True)
    monkeypatch.setattr(storage, "client", lambda: fake)
    monkeypatch.setattr(storage, "bucket", lambda: "b")
    return fake


def _late_writes(api, clip_id, job_id):
    """What the worker (and the racing dispatch) wrote AFTER job_6037's removal."""
    api.uploads_volume.files[f"/{clip_id}.mp4"] = b"video-bytes"
    r = api.results_volume.files
    r[f"/{clip_id}.npz"] = b"npz"
    r[f"/{clip_id}.performance.json"] = b"{}"
    r[f"/{clip_id}_track1.0123456789ab.glb"] = b"glb"
    r[f"/{job_id}.job-meta.json"] = json.dumps({"clip_id": clip_id}).encode()
    r[f"/{job_id}.job-status.json"] = b"{}"


def test_delete_clip_is_idempotent_and_takes_back_a_late_write(api):
    import retention
    _seed_lesson(api, "abc", "job_abc")
    first = retention.delete_clip(api.uploads_volume, api.results_volume, "abc", "job_abc",
                                  "mine", "i_am_in_it")
    tomb = api.results_volume.files["/abc.removed.json"]
    assert first["deleted"]

    _late_writes(api, "abc", "job_abc")
    again = retention.delete_clip(api.uploads_volume, api.results_volume, "abc", "job_abc", "")
    assert [p for p in api.results_volume.files if "abc" in p] == ["/abc.removed.json"]
    assert api.uploads_volume.files == {}
    assert "/abc.npz" in again["deleted"] and "/abc.mp4" in again["deleted"]
    assert api.results_volume.files["/abc.removed.json"] == tomb, \
        "a re-sweep must keep the original tombstone (its time and reason are the record)"

    assert retention.delete_clip(api.uploads_volume, api.results_volume, "abc", "job_abc", "")["deleted"] == []


def test_a_second_removal_request_sweeps_what_came_back(api):
    _seed_lesson(api, "abc", "job_abc")
    api.remove_lesson("abc", _removal(api), NO_REQUEST)
    _late_writes(api, "abc", "job_abc")
    again = api.remove_lesson("abc", _removal(api), NO_REQUEST)
    assert "/abc.mp4" in again.removed
    assert [p for p in api.results_volume.files if "abc" in p] == ["/abc.removed.json"]


def test_removal_writes_the_tombstone_before_deleting(api, monkeypatch):
    """So a writer checking between two deletions already sees it."""
    import retention
    _seed_lesson(api, "abc", "job_abc")
    seen = []
    real = api.uploads_volume.remove_file
    monkeypatch.setattr(api.uploads_volume, "remove_file",
                        lambda p, **k: seen.append("/abc.removed.json" in api.results_volume.files) or real(p))
    retention.delete_clip(api.uploads_volume, api.results_volume, "abc", "job_abc", "", "other")
    assert seen == [True]


def test_removal_deletes_every_version_in_r2_and_on_the_volume(api, r2):
    _seed_lesson(api, "abc", "job_abc")
    api.results_volume.files["/abc_track1.0123456789ab.glb"] = b"v1"
    api.results_volume.files["/abc_track1.ba9876543210.glb"] = b"v2"
    r2.objects.update({k: {} for k in (
        "video/abc.mp4", "glb/abc_track1.glb", "glb/abc_track1.0123456789ab.glb",
        "glb/abc_track1.ba9876543210.glb", "motion-result/abc.json.gz",
        "motion-result/abc.0123456789ab.json.gz", "glb/other_track1.glb", "video/abcd.mp4")})
    out = api.remove_lesson("abc", _removal(api), NO_REQUEST)
    assert sorted(r2.objects) == ["glb/other_track1.glb", "video/abcd.mp4"], "another lesson was touched"
    assert "r2:motion-result/abc.0123456789ab.json.gz" in out.removed
    assert not [p for p in api.results_volume.files if p.startswith("/abc_track")]


def test_removal_forgets_the_job_rows(api, monkeypatch):
    import jobstore
    forgot = []
    monkeypatch.setattr(jobstore, "forget", lambda job_id, clip_id=None: forgot.append((job_id, clip_id)))
    _seed_lesson(api, "abc", "job_abc")
    api.remove_lesson("abc", _removal(api), NO_REQUEST)
    assert forgot == [("job_abc", "abc")]


def test_removal_cancels_the_running_calls(api):
    """The GPU run and the beat proposal are cancelled and an unclaimed
    hand-off is dropped, instead of paying for work every write of which the
    tombstone would refuse."""
    api._dispatch_run(types.SimpleNamespace(state=types.SimpleNamespace()),
                      clip_id="abc", job_id="job_abc", beats_call_id="fc-beats")
    _seed_lesson(api, "abc", "job_abc")
    api.remove_lesson("abc", _removal(api), NO_REQUEST)
    assert api._cancelled == ["fc-run-1", "fc-beats"]
    assert "calls:job_abc" not in api._handoff_dict


def test_removal_drops_a_handoff_the_container_has_not_picked_up(api):
    state = types.SimpleNamespace(gpu_token="tok", gpu_call_id="fc-warm")
    api._dispatch_run(types.SimpleNamespace(state=state), clip_id="abc", job_id="job_abc",
                      beats_call_id=None)
    assert "tok" in api._handoff_dict
    _seed_lesson(api, "abc", "job_abc")
    api.remove_lesson("abc", _removal(api), NO_REQUEST)
    assert "tok" not in api._handoff_dict and api._cancelled == ["fc-warm"]


def test_link_dispatch_that_lost_a_race_with_removal_leaves_nothing(api, tmp_path):
    """A link's clip_id is derived, so it can be removed while the request is
    still downloading. The dispatch must not leave the bytes it just stored
    (the job_6037 shape) and must not spend a GPU."""
    from fastapi import HTTPException
    import retention
    clip = tmp_path / "c.mp4"
    clip.write_bytes(b"video")
    retention.write_tombstone(api.results_volume, "linked", "", "i_am_in_it")
    with pytest.raises(HTTPException) as e:
        api._store_and_dispatch(str(clip), "linked", {"sha256": "0" * 64, "frames": 0}, NO_REQUEST,
                                source_key="tiktok:1")
    assert e.value.status_code == 410
    assert api._spawned == [] and api.uploads_volume.files == {}
    assert [p for p in api.results_volume.files if "linked" in p] == ["/linked.removed.json"]
    assert retention.read_index(api.results_volume) == []


def test_status_mirror_does_not_resurrect_a_removed_jobs_row(api, monkeypatch):
    import jobstore
    import retention
    writes = []
    monkeypatch.setattr(jobstore, "postgres_enabled", lambda: True)
    monkeypatch.setattr(jobstore, "_pg_read", lambda job_id: None)   # forget deleted it
    monkeypatch.setattr(jobstore, "_pg_write", lambda *a, **k: writes.append(a))
    api.results_volume.files["/job_abc.job-status.json"] = json.dumps({
        "schema_version": "1.0.0", "job_id": "job_abc", "state": "failed", "stage_message": "",
        "progress": None, "retry_count": 0,
        "error": {"code": "export_error", "message": "x", "retryable": True}}).encode()
    retention.write_tombstone(api.results_volume, "abc", "", "other")
    jobstore.read_status(api.results_volume, "job_abc", lambda j: "abc")
    assert writes == [], "a removed job's row was written back"


def test_last_access_is_not_recorded_after_a_removal(api):
    import retention
    retention.write_tombstone(api.results_volume, "abc", "", "other")
    api._touch("abc")
    assert "/abc.last-access.json" not in api.results_volume.files


# --- the workers (modal_app), against a Volume whose mount and client agree --

class DirVolume:
    """A Volume that is both a mount (a real directory the worker writes to
    through open()) and a client (read_file_into_fileobj/remove_file), backed
    by the same bytes -- which is what the tombstone check relies on."""

    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def read_file_into_fileobj(self, path, buf):
        p = self.root / path.lstrip("/")
        if not p.exists():
            raise FileNotFoundError(path)
        buf.write(p.read_bytes())

    def listdir(self, path, **k):
        return [types.SimpleNamespace(path=p.name, mtime=0) for p in self.root.iterdir()]

    def remove_file(self, path, **k):
        p = self.root / path.lstrip("/")
        if not p.exists():
            raise InvalidError("No such file or directory.")  # as FakeVolume
        p.unlink()

    def batch_upload(self, force=False):
        vol = self

        class _Batch:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *a):
                return False

            def put_file(self_inner, local, remote):
                (vol.root / remote.lstrip("/")).write_bytes(Path(local).read_bytes())

        return _Batch()

    def commit(self):
        pass

    def reload(self):
        pass

    def names(self):
        return sorted(p.name for p in self.root.iterdir())


@pytest.fixture()
def worker(monkeypatch, tmp_path):
    import modal_app
    results, uploads = DirVolume(tmp_path / "results"), DirVolume(tmp_path / "uploads")
    monkeypatch.setattr(modal_app, "results", results)
    monkeypatch.setattr(modal_app, "uploads", uploads)
    monkeypatch.setattr(modal_app, "RESULTS_DIR", str(results.root))
    monkeypatch.setattr(modal_app, "UPLOADS_DIR", str(uploads.root))
    modal_app._test_volumes = (results, uploads)
    return modal_app


def test_job_status_is_never_written_for_a_removed_lesson(worker):
    import retention
    results, _ = worker._test_volumes
    worker._write_job_status("job_abc", "processing", "", 0.5, 0, clip_id="abc")
    assert "job_abc.job-status.json" in results.names()
    retention.write_tombstone(results, "abc", "", "other")
    with pytest.raises(retention.Removed):
        worker._write_job_status("job_abc", "failed", "", None, 0, clip_id="abc",
                                 error={"code": "export_error", "message": "x", "retryable": True})
    assert json.loads((results.root / "job_abc.job-status.json").read_text())["state"] == "processing"


def test_beat_proposal_stops_at_the_tombstone(worker):
    """Before starting, and again before its one write."""
    import dataclasses
    import retention
    results, uploads = worker._test_volumes
    (uploads.root / "abc.mp4").write_bytes(b"v")

    @dataclasses.dataclass
    class Grid:
        seconds_per_count: float = 0.5
        bpm: float = 120.0
        count_one_s: float = 0.0
        confidence: float = 1.0
        warnings: tuple = ()

    def removed_while_listening(path):
        retention.write_tombstone(results, "abc", "", "other")  # the takedown lands mid-proposal
        return Grid()

    with pytest.raises(retention.Removed):
        worker._propose_counts("abc", removed_while_listening)
    assert "abc.beats.json" not in results.names()
    with pytest.raises(retention.Removed):
        worker._propose_counts("abc", lambda p: pytest.fail("started work on a removed lesson"))


def test_worker_sweep_takes_back_uncommitted_local_writes(worker):
    """A file written through the mount but not yet committed would be
    committed by Modal at container exit -- after the server-side sweep -- so
    the worker deletes its own local writes first."""
    import retention
    results, uploads = worker._test_volumes
    retention.write_tombstone(results, "abc", "", "other")
    for name in ("abc.npz", "abc.performance.json", "job_abc.job-status.json", "abc_track1.0123456789ab.glb"):
        (results.root / name).write_bytes(b"late")
    (uploads.root / "abc.mp4").write_bytes(b"v")
    out = retention.stop_and_sweep(uploads, results, "abc", "job_abc",
                                   {str(results.root): results, str(uploads.root): uploads})
    assert out["removed"] is True
    assert results.names() == ["abc.removed.json"] and uploads.names() == []


def test_reexport_prunes_superseded_versions_and_keeps_the_new_ones(worker, r2, monkeypatch):
    results, _ = worker._test_volumes
    monkeypatch.setattr(worker, "OLD_VERSION_GRACE_S", 0)
    for name in ("abc_track1.glb", "abc_track1.0123456789ab.glb", "abc_track1.ba9876543210.glb",
                 "other_track1.glb"):
        (results.root / name).write_bytes(b"x")
    r2.objects.update({k: {} for k in (
        "video/abc.mp4", "glb/abc_track1.glb", "glb/abc_track1.0123456789ab.glb",
        "glb/abc_track1.ba9876543210.glb", "motion-result/abc.json.gz",
        "motion-result/abc.0123456789ab.json.gz", "motion-result/abc.ba9876543210.json.gz")})
    new = ["glb/abc_track1.ba9876543210.glb", "motion-result/abc.ba9876543210.json.gz",
           "motion-result/abc.json.gz"]
    worker._prune_old_versions("abc", {"glb_names": ["abc_track1.ba9876543210.glb"],
                                       "motion_result_materialised": True, "r2_published": new})
    assert results.names() == ["abc_track1.ba9876543210.glb", "other_track1.glb"]
    assert sorted(r2.objects) == sorted(new + ["video/abc.mp4"])


def test_no_pruning_while_the_old_document_is_still_the_one_served(worker, r2, monkeypatch):
    """If the new MotionResult did not reach R2, the old one still names the
    old GLBs -- they must stay."""
    results, _ = worker._test_volumes
    monkeypatch.setattr(worker, "OLD_VERSION_GRACE_S", 0)
    (results.root / "abc_track1.glb").write_bytes(b"x")
    r2.objects["glb/abc_track1.glb"] = {}
    worker._prune_old_versions("abc", {"glb_names": ["abc_track1.ba9876543210.glb"],
                                       "motion_result_materialised": True, "r2_published": []})
    assert "abc_track1.glb" in results.names() and "glb/abc_track1.glb" in r2.objects


# --- versioned asset names ----------------------------------------------------

def test_versioned_name_is_stable_for_identical_bytes_and_changes_with_them():
    import storage
    a = storage.versioned_name("abc_track1.glb", b"glb-bytes")
    assert a == storage.versioned_name("abc_track1.glb", b"glb-bytes")
    assert a != storage.versioned_name("abc_track1.glb", b"glb-bytes!")
    assert a.startswith("abc_track1.") and a.endswith(".glb")
    # The versioned name is still an asset id the API resolves to its lesson.
    assert storage.clip_id_for_asset(a) == "abc"
    assert storage.key_for_asset(a) == f"glb/{a}"


def test_result_redirect_follows_the_version_and_old_lessons_fall_back(api, monkeypatch, r2):
    """The browser is sent to the immutable versioned MotionResult; a lesson
    exported before versioning (no `version` metadata) keeps its old key."""
    monkeypatch.setattr(api.storage, "url_for", lambda key: f"https://r2.example/{key}")
    r2.objects["motion-result/new.json.gz"] = {"validated": "job_new", "version": "0123456789ab"}
    r2.objects["motion-result/old.json.gz"] = {"validated": "job_old"}
    assert api._validated_r2_url("job_new", "new") == \
        "https://r2.example/motion-result/new.0123456789ab.json.gz"
    assert api._validated_r2_url("job_old", "old") == "https://r2.example/motion-result/old.json.gz"
