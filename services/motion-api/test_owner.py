"""The owner's count-1 tool (owner.py + api.py /owner/*), against the same
in-memory Volume and R2 stand-ins as test_retention.py.

    python -m pytest test_owner.py -q
"""
from __future__ import annotations

import copy
import gzip
import json
import os
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_retention import FakeR2, api  # noqa: E402,F401 -- `api` is the fixture
from test_schema import db, store  # noqa: E402,F401 -- fixtures

_CONTRACT = Path(__file__).resolve().parents[2] / "packages" / "motion-contract"
KEY = "test-owner-key"
JOB, CLIP = "job_abc", "abc"
ALTS = [{"count_one_s": 0.9, "shift_counts": 1, "confidence": 0.3},
        {"count_one_s": 1.4, "shift_counts": 2, "confidence": 0.2},
        {"count_one_s": 1.9, "shift_counts": 3, "confidence": 0.1}]


def _http(key=KEY):
    return types.SimpleNamespace(headers={"x-stepwise-owner-key": key} if key is not None else {},
                                 client=None)


class R2(FakeR2):
    def put_object(self, Bucket, Key, Body, Metadata=None, **extra):
        self.objects[Key] = dict(Metadata or {}, _body=Body, _cache=extra.get("CacheControl"))

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise FileNotFoundError(Key)
        return {"Body": types.SimpleNamespace(read=lambda: self.objects[Key]["_body"])}


@pytest.fixture()
def lesson(api, monkeypatch):
    import owner
    monkeypatch.setenv("STEPWISE_OWNER_KEY", KEY)
    owner._FAILS.clear()
    doc = json.loads((_CONTRACT / "fixtures" / "good-lesson.json").read_text())
    doc["job_id"] = JOB
    doc["proposed_counts"]["count_one_alternates"] = copy.deepcopy(ALTS)
    r = api.results_volume.files
    r[f"/{CLIP}.motion-result.json.gz"] = gzip.compress(json.dumps(doc).encode())
    r[f"/{CLIP}.beats.json"] = json.dumps({"count_one_s": 0.4, "seconds_per_count": 0.5, "bpm": 120,
                                           "count_one_alternates": ALTS}).encode()
    r[f"/{JOB}.job-meta.json"] = json.dumps({"clip_id": CLIP, "credit": {"creator": "@x"}}).encode()
    r[f"/{JOB}.job-status.json"] = json.dumps({
        "schema_version": "1.0.0", "job_id": JOB, "state": "succeeded",
        "stage_message": "", "progress": 1.0, "error": None, "retry_count": 0}).encode()
    return api


def _stored(api):
    return json.loads(gzip.decompress(api.results_volume.files[f"/{CLIP}.motion-result.json.gz"]))


def _set(api, t, **kw):
    return api.owner_set_count_one(JOB, api.CountOneRequest(count_one_s=t, **kw), _http())


# --- auth ---------------------------------------------------------------------

def test_closed_when_no_key_is_configured(lesson, monkeypatch):
    monkeypatch.delenv("STEPWISE_OWNER_KEY")
    for call in (lambda: lesson.owner_queue(_http()), lambda: _set(lesson, 0.9)):
        with pytest.raises(lesson.HTTPException) as e:
            call()
        assert e.value.status_code == 404


@pytest.mark.parametrize("key", [None, "", "wrong", "tést"])
def test_missing_or_wrong_key_is_403_and_writes_nothing(lesson, key):
    before = dict(lesson.results_volume.files)
    with pytest.raises(lesson.HTTPException) as e:
        lesson.owner_set_count_one(JOB, lesson.CountOneRequest(count_one_s=0.9), _http(key))
    assert e.value.status_code == 403
    assert lesson.results_volume.files == before


def test_repeated_bad_keys_are_rate_limited(lesson):
    import owner
    for _ in range(owner.MAX_FAILS):
        with pytest.raises(lesson.HTTPException):
            lesson.owner_queue(_http("wrong"))
    with pytest.raises(lesson.HTTPException) as e:
        lesson.owner_queue(_http())  # even the right key, until the window passes
    assert e.value.status_code == 429


# --- the rewrite --------------------------------------------------------------

def test_snaps_to_the_nearest_grid_beat_and_keeps_the_grid(lesson):
    out = _set(lesson, 0.97, method="tap")  # grid is 0.4 + 0.5k; nearest is 0.9
    pc = _stored(lesson)["proposed_counts"]
    assert pc["count_one_s"] == 0.9 == out["proposed_counts"]["count_one_s"]
    assert (pc["seconds_per_count"], pc["bpm"], pc["count_one_source"]) == (0.5, 120, "owner")
    assert pc["count_one_confidence"] == 1.0  # a person decided it: not a guess any more
    assert pc["count_total"] == int((13.933333 - 0.9) // 0.5) + 1


def test_snap_before_the_detector_pick_and_never_below_zero():
    import owner
    assert owner.snap(0.4, 0.5, 0.0, 14.0) == (0.4, 0)    # -0.1 would be before the clip
    assert owner.snap(2.4, 0.5, 0.45, 14.0) == (0.4, -4)  # a whole bar earlier
    with pytest.raises(owner.OffGrid):
        owner.snap(0.4, 0.5, 20.0, 14.0)


def test_old_pick_becomes_the_first_alternate(lesson):
    _set(lesson, 0.9, option="B")
    alts = _stored(lesson)["proposed_counts"]["count_one_alternates"]
    assert alts[0] == {"count_one_s": 0.4, "shift_counts": -1, "confidence": 0.4}
    # 0.9 is the pick now, so it is no longer an alternate; the rest re-measured.
    assert [(a["count_one_s"], a["shift_counts"]) for a in alts[1:]] == [(1.4, 1), (1.9, 2)]


def test_a_whole_bar_move_adds_no_alternate(lesson):
    _set(lesson, 2.4)
    alts = _stored(lesson)["proposed_counts"]["count_one_alternates"]
    assert [(a["count_one_s"], a["shift_counts"]) for a in alts] == [(0.9, -3), (1.4, -2), (1.9, -1)]


def test_rewritten_document_passes_the_contract(lesson):
    sys.path.insert(0, str(_CONTRACT / "python"))
    from motion_contract import validate_motion_result
    _set(lesson, 1.4)
    assert validate_motion_result(_stored(lesson)).errors == []


def test_off_the_end_of_the_clip_is_422(lesson):
    with pytest.raises(lesson.HTTPException) as e:
        _set(lesson, 30.0)
    assert e.value.status_code == 422


def test_removed_lesson_is_410_and_untouched(lesson):
    import retention
    retention.write_tombstone(lesson.results_volume, CLIP, "gone")
    before = lesson.results_volume.files[f"/{CLIP}.motion-result.json.gz"]
    with pytest.raises(lesson.HTTPException) as e:
        _set(lesson, 0.9)
    assert e.value.status_code == 410
    assert lesson.results_volume.files[f"/{CLIP}.motion-result.json.gz"] == before
    assert f"/{CLIP}.count-one-labels.json" not in lesson.results_volume.files


def test_publishes_like_export_and_this_replica_serves_it(lesson, monkeypatch):
    import storage
    fake = R2()
    monkeypatch.setattr(storage, "enabled", lambda: True)
    monkeypatch.setattr(storage, "client", lambda: fake)
    monkeypatch.setattr(storage, "bucket", lambda: "b")
    monkeypatch.setattr(storage, "url_for", lambda key: f"https://r2.example/{key}")
    lesson._R2_VALIDATED[(JOB, CLIP)] = ("motion-result/abc.old.json.gz", 1e18)

    _set(lesson, 0.9)
    gz = lesson.results_volume.files[f"/{CLIP}.motion-result.json.gz"]
    version = storage.content_version(gz)
    latest = fake.objects["motion-result/abc.json.gz"]
    assert latest["_body"] == gz and latest["validated"] == JOB and latest["version"] == version
    assert latest["_cache"] == storage.MUTABLE_CACHE_CONTROL
    assert fake.objects[f"motion-result/abc.{version}.json.gz"]["_body"] == gz
    assert lesson._validated_r2_url(JOB, CLIP) == f"https://r2.example/motion-result/abc.{version}.json.gz"


# --- labels + queue -----------------------------------------------------------

def test_every_set_appends_a_label(lesson):
    _set(lesson, 0.9, option="B")
    _set(lesson, 1.4, method="tap")
    doc = json.loads(lesson.results_volume.files[f"/{CLIP}.count-one-labels.json"])
    first, second = doc["labels"]
    assert (first["count_one_s"], first["previous_count_one_s"], first["option"]) == (0.9, 0.4, "B")
    assert (second["count_one_s"], second["previous_count_one_s"], second["method"]) == (1.4, 0.9, "tap")
    assert first["detector_count_one_s"] == second["detector_count_one_s"] == 0.4
    assert {"job_id", "clip_id", "seconds_per_count", "bpm", "at"} <= set(first)


def test_labels_go_with_a_removal(lesson):
    import retention
    _set(lesson, 0.9)
    paths = retention.clip_artifact_paths(
        [p.lstrip("/") for p in lesson.results_volume.files], CLIP, JOB)["results"]
    assert f"/{CLIP}.count-one-labels.json" in paths


def test_queue_from_the_volume_shows_confirmed_after_a_set(lesson):
    (row,) = lesson.owner_queue(_http())["jobs"]
    assert (row["clip_id"], row["count_one_s"], row["confirmed"], row["bpm"]) == (CLIP, 0.4, False, 120)
    assert row["video_url"] == f"/api/jobs/{JOB}/video" and row["credit"] == {"creator": "@x"}
    _set(lesson, 0.9)
    (row,) = lesson.owner_queue(_http())["jobs"]
    assert (row["count_one_s"], row["confirmed"], row["duration_s"]) == (0.9, True, 14)
    assert row["count_one_alternates"][0]["count_one_s"] == 0.4


@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="no DATABASE_URL -- see test_schema.py")
def test_queue_from_postgres_is_newest_succeeded_first(lesson, store, db):  # noqa: F811
    for job, clip, state, age in [(JOB, CLIP, "succeeded", "2 hours"), ("job_new", "new", "succeeded", "1 hour"),
                                  ("job_run", "run", "processing", "0 hours")]:
        db.execute("INSERT INTO jobs (job_id, clip_id, state, created_at) "
                   "VALUES (%s, %s, %s, now() - %s::interval)", (job, clip, state, age))
    rows = lesson.owner_queue(_http())["jobs"]
    assert [r["job_id"] for r in rows] == ["job_new", JOB]
    assert rows[0]["bpm"] is None and rows[1]["bpm"] == 120  # no beats.json: listed, nothing to set
    assert isinstance(rows[1]["created_at"], float)


# --- recount ------------------------------------------------------------------

FRESH = {"count_one_s": 0.4, "seconds_per_count": 0.5, "confidence": 0.9, "bpm": 120.0,
         "alternates": [], "warnings": [], "count_one_alternates": ALTS, "count_one_confidence": 0.3}


def _recount(api, monkeypatch, beats=FRESH):
    calls = []
    monkeypatch.setattr(api, "_propose_counts_now",
                        lambda clip_id: calls.append(clip_id) or copy.deepcopy(beats))
    out = api.owner_recount(JOB, _http())
    assert calls == [CLIP]
    return out


def test_recount_republishes_the_fresh_proposal(lesson, monkeypatch):
    out = _recount(lesson, monkeypatch, dict(FRESH, confidence=0.5))
    pc = _stored(lesson)["proposed_counts"]
    assert out["kept_owner_count_one"] is False and pc == out["proposed_counts"]
    assert pc["confidence"] == 0.5 and "count_one_source" not in pc
    assert pc["count_one_confidence"] == 0.3  # the backfill this endpoint exists for


def test_recount_keeps_an_owner_count_one(lesson, monkeypatch):
    _set(lesson, 0.9)
    out = _recount(lesson, monkeypatch, dict(FRESH, confidence=0.5))
    pc = _stored(lesson)["proposed_counts"]
    assert out["kept_owner_count_one"] is True
    assert (pc["count_one_s"], pc["count_one_source"], pc["confidence"]) == (0.9, "owner", 0.5)
    assert pc["count_one_confidence"] == 1.0
    assert pc["count_one_alternates"][0]["count_one_s"] == 0.4  # the fresh detector pick


def test_recount_with_no_proposal_leaves_the_lesson_alone(lesson, monkeypatch):
    before = lesson.results_volume.files[f"/{CLIP}.motion-result.json.gz"]
    with pytest.raises(lesson.HTTPException) as e:
        _recount(lesson, monkeypatch, None)
    assert e.value.status_code == 409
    assert lesson.results_volume.files[f"/{CLIP}.motion-result.json.gz"] == before


def test_recount_needs_the_key(lesson, monkeypatch):
    monkeypatch.setattr(lesson, "_propose_counts_now", lambda clip_id: pytest.fail("ran the beat stage"))
    with pytest.raises(lesson.HTTPException) as e:
        lesson.owner_recount(JOB, _http("wrong"))
    assert e.value.status_code == 403


# --- owner removal (POST /owner/jobs/{job_id}/remove) ------------------------

def _remove(api, mode, key=KEY, note=""):
    return api.owner_remove(JOB, api.OwnerRemovalRequest(mode=mode, note=note), _http(key))


@pytest.mark.parametrize("key", [None, "wrong"])
def test_owner_removal_needs_the_key_and_touches_nothing(lesson, key):
    before = dict(lesson.results_volume.files)
    for mode in ("delete", "quarantine"):
        with pytest.raises(lesson.HTTPException) as e:
            _remove(lesson, mode, key)
        assert e.value.status_code == 403
    assert lesson.results_volume.files == before and lesson.quarantine.files == {}


def test_owner_removal_is_closed_without_a_configured_key(lesson, monkeypatch):
    monkeypatch.delenv("STEPWISE_OWNER_KEY")
    with pytest.raises(lesson.HTTPException) as e:
        _remove(lesson, "delete")
    assert e.value.status_code == 404


def test_owner_delete_is_the_normal_takedown(lesson):
    out = _remove(lesson, "delete", note="not a dance")
    assert out["quarantined"] is False and out["removed"]
    assert [p for p in lesson.results_volume.files if CLIP in p] == [f"/{CLIP}.removed.json"]
    tomb = json.loads(lesson.results_volume.files[f"/{CLIP}.removed.json"])
    assert (tomb["relationship"], tomb["reason"]) == ("owner", "not a dance")
    assert lesson.quarantine.files == {}
    with pytest.raises(lesson.HTTPException) as e:
        lesson.get_job_status(JOB)
    assert e.value.status_code == 410


def test_owner_quarantine_preserves_and_alerts(lesson, monkeypatch):
    sent = []
    monkeypatch.setattr(lesson.observability, "message", lambda text, c, **kw: sent.append(kw["level"]))
    out = _remove(lesson, "quarantine", note="looks like a minor")
    assert out["quarantined"] is True and sent == ["fatal"]
    assert [p for p in lesson.results_volume.files if CLIP in p] == [f"/{CLIP}.removed.json"]
    m = json.loads(lesson.quarantine.files[f"/{CLIP}/manifest.json"])
    assert (m["relationship"], m["reason"]) == ("owner", "looks like a minor")
    assert any(f["source"] == f"results:/{CLIP}.motion-result.json.gz" for f in m["files"])
    # Idempotent, and a later "delete" cannot destroy what was preserved.
    snapshot = dict(lesson.quarantine.files)
    assert _remove(lesson, "delete")["quarantined"] is True
    assert lesson.quarantine.files == snapshot and sent == ["fatal"]
