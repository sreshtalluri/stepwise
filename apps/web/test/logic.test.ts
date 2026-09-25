import { test } from "node:test";
import assert from "node:assert/strict";

import { REVEAL_DURATION_MS, easeInOutCubic, revealAzimuth } from "../lib/reveal";
import { isJobStatus, timeRemaining } from "../lib/jobStatus";
import { lessonIdFromLink, lessonSource, parseCredit } from "../lib/lessons";
import { lesson as lessonCopy } from "../lib/copy";
import type { MotionResult } from "../lib/motion";

test("the reveal is one full orbit that settles back at the front", () => {
  assert.equal(revealAzimuth(0), 0);
  assert.ok(Math.abs(revealAzimuth(REVEAL_DURATION_MS / 2) - 180) < 0.001);
  // Settled: at and past the end the camera is back at the camera view.
  assert.equal(revealAzimuth(REVEAL_DURATION_MS), 0);
  assert.equal(revealAzimuth(REVEAL_DURATION_MS + 5000), 0);
});

test("the orbit is eased, not linear — DESIGN.md §7f", () => {
  assert.equal(easeInOutCubic(0), 0);
  assert.equal(easeInOutCubic(1), 1);
  assert.equal(easeInOutCubic(0.5), 0.5);
  // Slow out of the front: a quarter of the time covers well under a quarter
  // of the turn.
  assert.ok(easeInOutCubic(0.25) < 0.15);
  // Monotonic — the camera never reverses mid-orbit.
  let prev = -1;
  for (let t = 0; t <= 1.0001; t += 0.01) {
    const v = easeInOutCubic(t);
    assert.ok(v >= prev, `eased value went backwards at t=${t}`);
    prev = v;
  }
});

test("time remaining stays loose and says nothing when it cannot know", () => {
  assert.equal(timeRemaining({ state: "queued", progress: null }, 0), "Still in the queue.");
  // Too early to extrapolate honestly.
  assert.equal(timeRemaining({ state: "processing", progress: null }, 30000), null);
  assert.equal(timeRemaining({ state: "processing", progress: 0.02 }, 30000), null);
  assert.equal(timeRemaining({ state: "processing", progress: 0.5 }, 1000), null);
  // 25% done after 60s → about 3 minutes left.
  assert.equal(
    timeRemaining({ state: "processing", progress: 0.25 }, 60000),
    "About 3 minutes left.",
  );
  assert.equal(
    timeRemaining({ state: "processing", progress: 0.5 }, 60000),
    "About a minute left.",
  );
  assert.equal(
    timeRemaining({ state: "processing", progress: 0.98 }, 60000),
    "Nearly there.",
  );
  // Nothing to say once it is over — the reveal takes it from here.
  assert.equal(timeRemaining({ state: "succeeded", progress: 1 }, 99999), null);
});

test("job status guard rejects a malformed payload", () => {
  const ok = {
    schema_version: "1.0.0",
    job_id: "job_1",
    state: "processing",
    stage_message: "Building the body — count 9 of 32",
    progress: 0.3,
    error: null,
    retry_count: 0,
  };
  assert.ok(isJobStatus(ok));
  assert.ok(!isJobStatus({ ...ok, state: "detection_complete" }));
  assert.ok(!isJobStatus({ ...ok, stage_message: 42 }));
  assert.ok(!isJobStatus(null));
  assert.ok(!isJobStatus("queued"));
});

test("a lesson id resolves to fixture files or to the job API", () => {
  const persons = [
    { person_id: "p0", animation: { glb_asset_id: "clip1_track0.glb" } },
    { person_id: "p1", animation: { glb_asset_id: "clip1_track1.glb" } },
  ];
  const doc = { persons } as unknown as MotionResult;

  const fixture = lessonSource("good-lesson");
  assert.equal(fixture.docUrl, "/fixtures/good-lesson.json");
  assert.equal(fixture.videoUrl, "/fixtures/good-lesson.mp4");
  assert.deepEqual(fixture.glbUrls(doc), ["/fixtures/good-lesson.p0.glb", "/fixtures/good-lesson.p1.glb"]);
  assert.ok(fixture.title);

  const job = lessonSource("job 1/x");
  assert.equal(job.title, null);
  assert.equal(job.docUrl, "/api/jobs/job%201%2Fx/result");
  assert.equal(job.videoUrl, "/api/jobs/job%201%2Fx/video");
  assert.deepEqual(job.glbUrls(doc), ["/api/assets/clip1_track0.glb", "/api/assets/clip1_track1.glb"]);

  // A prototype key is a job id, not a fixture.
  assert.equal(lessonSource("constructor").docUrl, "/api/jobs/constructor/result");
});

test("lessonIdFromLink takes a lesson or processing link, never a fixture", () => {
  assert.equal(lessonIdFromLink("https://stepwise.example/lesson/job_abc123"), "job_abc123");
  assert.equal(lessonIdFromLink("  /job/job_abc?x=1#y "), "job_abc");
  assert.equal(lessonIdFromLink("https://www.tiktok.com/@someone/video/123"), null);
  assert.equal(lessonIdFromLink("/lesson/good-lesson"), null);
  assert.equal(lessonIdFromLink(""), null);
});

test("parseCredit keeps an https credit and drops anything else", () => {
  const tiktok = { url: "https://www.tiktok.com/@jonraydybuco/video/7672198121417444628", host: "TikTok", creator: "@jonraydybuco",
    choreo: null, track: null, artist: null };
  assert.deepEqual(parseCredit(tiktok), tiktok);
  // An older credit without the caption fields reads them as null; non-strings are dropped.
  const { choreo: _c, track: _t, artist: _a, ...old } = tiktok;
  assert.deepEqual(parseCredit(old), tiktok);
  assert.deepEqual(parseCredit({ ...tiktok, choreo: "@kyle", track: 3 }), { ...tiktok, choreo: "@kyle" });
  // The line under the credit shows only what was found.
  assert.equal(lessonCopy.postCredit(tiktok), null);
  assert.equal(lessonCopy.postCredit({ ...tiktok, choreo: "@kyle" }), "Choreo @kyle");
  assert.equal(lessonCopy.postCredit({ ...tiktok, track: "APT." }), "♪ APT.");
  assert.equal(lessonCopy.postCredit({ choreo: "@a, @b", track: "APT.", artist: "ROSÉ" }), "Choreo @a, @b · ♪ APT. · ROSÉ");
  assert.deepEqual(parseCredit({ ...tiktok, creator: null }), { ...tiktok, creator: null });
  assert.equal(parseCredit({ ...tiktok, url: "javascript:alert(1)" }), null);
  assert.equal(parseCredit({ detail: "No source link for this lesson." }), null);
  assert.equal(parseCredit(null), null);
});

test("a link lesson is named for its post, with the choreographer when known", () => {
  const c = { host: "TikTok", creator: "@kinjazofficial", choreo: null };
  assert.equal(lessonCopy.creditTitle(c), "@kinjazofficial on TikTok");
  assert.equal(lessonCopy.creditTitle({ ...c, choreo: "@carlodarang" }), "@kinjazofficial on TikTok · Choreo @carlodarang");
  assert.equal(lessonCopy.creditTitle({ ...c, creator: null }), "From TikTok");
});
