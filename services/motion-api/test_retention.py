"""One runnable check for the deletion path. `python test_retention.py`.

No framework, no fixtures, no Modal account: the Volume and Dict surfaces this
code uses are four methods each, so they are faked here. What this is actually
guarding is the two things that would be silent and bad if they broke --
a takedown that misses an artifact, and a removed lesson that still answers as
if it were alive.
"""
from __future__ import annotations

import io
import sys
import time

import retention


class FakeVolume:
    def __init__(self, files: dict[str, bytes] | None = None):
        self.files = dict(files or {})

    def read_file_into_fileobj(self, path, buf):
        if path not in self.files:
            raise FileNotFoundError(path)
        buf.write(self.files[path])

    def remove_file(self, path, recursive=False):
        if path not in self.files:
            raise FileNotFoundError(path)
        del self.files[path]

    def listdir(self, path, recursive=False):
        class _E:
            def __init__(self, p): self.path = p.lstrip("/")
        return [_E(p) for p in self.files]

    def batch_upload(self, force=False):
        vol = self

        class _Batch:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def put_file(self, local, remote):
                with open(local, "rb") as f:
                    vol.files[remote] = f.read()
        return _Batch()


class FakeDict(dict):
    def put(self, k, v): self[k] = v
    def get(self, k, default=None): return dict.get(self, k, default)
    def items(self): return list(dict.items(self))


def _lesson(uploads, results, idx, clip_id, job_ids, glb_tracks=(1,)):
    uploads.files[f"/{clip_id}.mp4"] = b"video-bytes"
    results.files[f"/{clip_id}.npz"] = b"npz"
    results.files[f"/{clip_id}.performance.json"] = b"{}"
    results.files[f"/{clip_id}.export-manifest.json"] = (
        '{"clip_id":"%s","fps":15.0,"glb_paths":{%s}}'
        % (clip_id, ",".join(f'"{t}":"{clip_id}_track{t}.glb"' for t in glb_tracks))
    ).encode()
    for t in glb_tracks:
        results.files[f"/{clip_id}_track{t}.glb"] = b"glb"
    for j in job_ids:
        results.files[f"/{j}.job-status.json"] = b'{"state":"succeeded"}'
        results.files[f"/{j}.job-meta.json"] = ('{"clip_id":"%s"}' % clip_id).encode()
    rec = retention.new_record(clip_id, {"sha256": clip_id, "self_spread": 0.3}, job_ids[0])
    rec["job_ids"] = list(job_ids)
    idx.put(clip_id, rec)


def test_takedown_removes_every_artifact_and_every_link():
    uploads, results, idx = FakeVolume(), FakeVolume(), FakeDict()
    # Two people uploaded the same dance; dedupe collapsed them onto one clip.
    _lesson(uploads, results, idx, "clipA", ["job_1", "job_2"], glb_tracks=(1, 3))
    _lesson(uploads, results, idx, "clipB", ["job_9"])

    out = retention.purge_clip("clipA", "takedown", uploads_volume=uploads,
                               results_volume=results, idx=idx)

    assert "/clipA.mp4" not in uploads.files, "source video survived a takedown"
    for leftover in results.files:
        assert "clipA" not in leftover or leftover.endswith(".removed.json"), \
            f"artifact survived a takedown: {leftover}"
    # Both share links die, not just the one that asked.
    assert sorted(out["job_ids"]) == ["job_1", "job_2"]
    for j in ("job_1", "job_2"):
        assert retention.removal_marker(results, j) is not None, f"{j} has no tombstone"
        assert f"/{j}.job-status.json" not in results.files

    # The unrelated lesson is untouched.
    assert "/clipB.mp4" in uploads.files and "/clipB_track1.glb" in results.files
    assert retention.removal_marker(results, "job_9") is None

    # The fingerprint stays, tombstoned, so a re-upload cannot resurrect it.
    rec = idx.get("clipA")
    assert rec["removed_reason"] == "takedown" and rec["removed_at"]
    assert rec["fingerprint"]["sha256"] == "clipA", "stay-down record lost its fingerprint"
    assert "video" not in str(rec), "tombstone must not hold video bytes"


def test_takedown_is_idempotent_and_survives_a_missing_manifest():
    uploads, results, idx = FakeVolume(), FakeVolume(), FakeDict()
    _lesson(uploads, results, idx, "clipA", ["job_1"])
    del results.files["/clipA.export-manifest.json"]   # a refused/crashed export
    retention.purge_clip("clipA", "takedown", uploads_volume=uploads,
                         results_volume=results, idx=idx)
    assert "/clipA_track1.glb" not in results.files, "listdir fallback missed an orphaned GLB"
    # Running it again must not raise.
    retention.purge_clip("clipA", "takedown", uploads_volume=uploads,
                         results_volume=results, idx=idx)


def test_sweep_expires_on_last_access_not_on_upload_date():
    uploads, results, idx = FakeVolume(), FakeVolume(), FakeDict()
    _lesson(uploads, results, idx, "viral", ["job_v"])
    _lesson(uploads, results, idx, "oneoff", ["job_o"])
    long_ago = time.time() - (retention.TTL_DAYS + 30) * 86400

    # Both uploaded long ago; only one is still being opened.
    for cid, last in (("viral", time.time()), ("oneoff", long_ago)):
        rec = idx.get(cid)
        rec["created_at"] = long_ago
        rec["last_accessed"] = last
        idx.put(cid, rec)

    retention.index = lambda: idx  # noqa: E731 -- the one seam worth faking
    out = retention.sweep(uploads, results)

    assert out["expired"] == ["oneoff"], out
    assert "/viral.mp4" in uploads.files, "a lesson opened today was deleted"
    assert "/oneoff.mp4" not in uploads.files, "a lesson untouched for 180 days survived"
    assert retention.removal_marker(results, "job_o") is not None
    assert idx.get("oneoff")["removed_reason"] == "expired"


def test_touch_is_debounced_but_does_not_revive_a_removed_lesson():
    idx = FakeDict()
    rec = retention.new_record("c", {"sha256": "c"}, "job_1")
    rec["last_accessed"] = 0.0
    idx.put("c", rec)
    retention.touch(idx, "c")
    assert idx.get("c")["last_accessed"] > 0, "a stale lesson was not refreshed"

    before = idx.get("c")["last_accessed"]
    retention.touch(idx, "c")
    assert idx.get("c")["last_accessed"] == before, "touch wrote twice inside the debounce window"

    rec = idx.get("c"); rec["removed_at"] = time.time(); rec["last_accessed"] = 0.0
    idx.put("c", rec)
    retention.touch(idx, "c")
    assert idx.get("c")["last_accessed"] == 0.0, "touch revived a removed lesson"

    retention.touch(idx, "never-seen")  # must not raise


if __name__ == "__main__":
    real_index = retention.index
    failures = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_"):
            continue
        retention.index = real_index
        try:
            fn()
            print(f"ok   {name}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL {name}: {e}")
    print("all retention checks passed" if not failures else f"{failures} failed")
    sys.exit(1 if failures else 0)
