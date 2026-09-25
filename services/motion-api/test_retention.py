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


def _removal(api, relationship="i_am_in_it", reason=""):
    return api.RemovalRequest(relationship=relationship, reason=reason)


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
            raise FileNotFoundError(path)
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
            spawn=lambda **kw: spawned.append(kw) if name == "run_clip"
            else types.SimpleNamespace(object_id=f"fc-{name}")))
    monkeypatch.setitem(sys.modules, "modal", fake_modal)
    for mod in ("api", "retention", "motion_result", "fingerprint"):
        sys.modules.pop(mod, None)
    import api as api_mod
    api_mod.uploads_volume = FakeVolume("uploads")
    api_mod.results_volume = FakeVolume("results")
    api_mod.eval_volume = FakeVolume("eval")
    api_mod._TOUCHED.clear()
    api_mod._spawned = spawned
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

    # Marked for a different job (a deduplicated upload): not trusted.
    metadata["validated"] = "job_someone_else"
    assert api._validated_r2_url(job_id, "marked") is None
