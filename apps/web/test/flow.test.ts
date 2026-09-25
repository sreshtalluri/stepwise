import { test } from "node:test";
import assert from "node:assert/strict";

import { detectionIndex, failedBody, flowSteps, handoffHref, parseHandoff, type Detections } from "../lib/flow";
import type { JobStatus } from "../lib/jobStatus";
import { processing, upload } from "../lib/copy";
import { failureFrom } from "../lib/submit";

const COUNTS = { bpm: 120, count_one_s: 0.5, seconds_per_count: 0.5, confidence: 0.9 };

function status(over: Partial<JobStatus>): JobStatus {
  return {
    schema_version: "1.0.0",
    job_id: "job_x",
    state: "processing",
    stage_message: "",
    progress: 0.3,
    error: null,
    retry_count: 0,
    ...over,
  };
}

test("every done step is backed by a milestone, not by the progress fraction", () => {
  const [, dancers, body] = flowSteps(status({ progress: 0.9 }));
  assert.equal(dancers.state, "now");
  assert.equal(body.state, "wait");

  const s = flowSteps(
    status({ milestones: { counts: COUNTS, dancers: 2, frames_done: 150, frames_total: 300 } }),
  );
  assert.deepEqual(s.map((x) => x.state), ["done", "done", "now"]);
  assert.equal(s[1].note, "2 dancers");
  assert.equal(s[2].note, "Frame 150 of 300");

  const q = flowSteps(status({ state: "queued", progress: null, milestones: { counts: COUNTS } }));
  assert.equal(q[1].state, "wait");

  const done = flowSteps(status({ state: "succeeded", progress: 1 }));
  assert.ok(done.every((x) => x.state === "done"));
});

test("no step reports counts: the early counts are not shown on this page", () => {
  const s = flowSteps(status({ milestones: { counts: COUNTS, dancers: 1 } }));
  assert.deepEqual(s.map((x) => x.key), ["clip", "dancers", "body"]);
  assert.ok(s.every((x) => !/count|a minute/i.test(x.note)), JSON.stringify(s));
});

test("the handoff round-trips speed and loop, and drops anything it does not know", () => {
  const href = handoffHref("job_a b", 0.5, { startCount: 9, endCount: 16 });
  assert.equal(href, "/lesson/job_a%20b?speed=0.5&loop=9-16");
  assert.equal(handoffHref("j", 1, null), "/lesson/j");

  const speeds = [0.25, 0.5, 0.75, 1];
  assert.deepEqual(parseHandoff("?speed=0.5&loop=9-16", speeds, 40), {
    speed: 0.5,
    loop: { startCount: 9, endCount: 16 },
  });
  assert.deepEqual(parseHandoff("?loop=41-48", speeds, 42), { speed: null, loop: { startCount: 41, endCount: 42 } });
  assert.deepEqual(parseHandoff("?speed=3&loop=9-2", speeds, 40), { speed: null, loop: null });
  assert.deepEqual(parseHandoff("?loop=50-56", speeds, 42), { speed: null, loop: null });
  assert.deepEqual(parseHandoff("?loop=3.5-6", speeds, 40).loop, { startCount: 3.5, endCount: 6 }, "an and");
  assert.equal(handoffHref("j", 1, { startCount: 3.5, endCount: 6 }), "/lesson/j?loop=3.5-6");
  assert.equal(parseHandoff("?loop=3.25-6", speeds, 40).loop, null, "only counts and ands");
});

test("detections are looked up by time and end where the sampling ended", () => {
  const d: Detections = { fps: 5, width: 10, height: 10, times: [0, 0.2, 0.4], dancers: [] };
  assert.equal(detectionIndex(d, 0), 0);
  assert.equal(detectionIndex(d, 0.29), 1);
  assert.equal(detectionIndex(d, 0.45), 2);
  assert.equal(detectionIndex(d, 5), -1);
});

test("a retryable failure never shows the raw exception text; a refusal shows the service's sentence", () => {
  const raw = "RuntimeError: CUDA out of memory. Tried to allocate 2.00 GiB";
  assert.equal(failedBody({ message: raw, retryable: true }), processing.failedRetryable);
  const refusal = "This clip has 7 dancers tracked confidently enough to reconstruct, more than the 6 we can currently handle in one clip.";
  assert.equal(failedBody({ message: refusal, retryable: false }), refusal);
});

test("a 413 names the size problem, not the connection; service sentences pass through verbatim", async () => {
  const json = (status: number, body: unknown) =>
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  // services/motion-api api.py: HTTPException(413, "Clip is too large.") -- a bare-string detail.
  assert.deepEqual(await failureFrom(json(413, { detail: "Clip is too large." }), upload.errors.uploadFailed),
    { error: upload.errors.tooLarge, kind: "file" });
  // The host in front of the service can answer 413 with an HTML page.
  assert.deepEqual(await failureFrom(new Response("<html>413</html>", { status: 413 }), upload.errors.uploadFailed),
    { error: upload.errors.tooLarge, kind: "file" });
  const limit = "You have started 5 lessons this hour, which is the limit. Try again in about an hour.";
  assert.deepEqual(await failureFrom(json(429, { detail: { error: { message: limit } } }), upload.errors.uploadFailed),
    { error: limit, kind: "limit" });
  // services/motion-api api.py: a wrong code (invite_invalid) is told apart from a missing one (invite_required).
  const invite = "That invite code isn't right. Check it and try again.";
  assert.deepEqual(await failureFrom(json(403, { detail: { error: { message: invite } } }), upload.linkErrors.unreachable),
    { error: invite, kind: "invite" });
  assert.deepEqual(await failureFrom(json(422, { detail: { error: { message: "That video is behind a login, so we cannot open it." } } }), ""),
    { error: "That video is behind a login, so we cannot open it.", kind: "refused" });
  // No sentence from the service: ours.
  assert.deepEqual(await failureFrom(new Response("bad gateway", { status: 502 }), upload.errors.uploadFailed),
    { error: upload.errors.uploadFailed, kind: "unreachable" });
});
