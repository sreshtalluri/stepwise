import { test } from "node:test";
import assert from "node:assert/strict";

import { fetchLessonDoc, forgetLessonDoc, loadLessonDoc, retryable } from "./lessonDoc";

const ok = () => new Response(JSON.stringify({ persons: [] }), { status: 200 });
const status = (s: number) => () => new Response("", { status: s });
const reject = () => Promise.reject(new TypeError("Load failed"));
const noSleep = async () => {};

/** A fetch that answers from a script, one entry per call, and counts calls. */
function scripted(...answers: (() => Response | Promise<Response>)[]) {
  const f = async () => answers[Math.min(f.calls++, answers.length - 1)]();
  f.calls = 0;
  return f;
}

test("answers are final, bad moments are not", () => {
  for (const s of [404, 409, 410]) assert.equal(retryable(s), false, String(s));
  for (const s of [0, 429, 500, 502, 503, 504]) assert.equal(retryable(s), true, String(s));
});

test("a network failure, then a 502, then the document: the learner never sees the error", async () => {
  const f = scripted(reject, status(502), ok);
  const load = await fetchLessonDoc("/api/jobs/j/result", f, [1, 1], noSleep);
  assert.equal(load.kind, "ok");
  assert.equal(f.calls, 3);
});

test("a removed lesson (410) is reported at once, not retried", async () => {
  const f = scripted(status(410), ok);
  assert.deepEqual(await fetchLessonDoc("/x", f, [1, 1], noSleep), { kind: "error", status: 410 });
  assert.equal(f.calls, 1);
});

test("retries run out: the last failure is what the page shows", async () => {
  const f = scripted(status(503));
  assert.deepEqual(await fetchLessonDoc("/x", f, [1, 1], noSleep), { kind: "error", status: 503 });
  assert.equal(f.calls, 3);
});

test("a body that is not a MotionResult is a failure, and retried", async () => {
  const f = scripted(() => new Response("{}", { status: 200 }), ok);
  assert.equal((await fetchLessonDoc("/x", f, [1], noSleep)).kind, "ok");
  assert.equal(f.calls, 2);
});

test("the lesson page joins the processing screen's prefetch instead of fetching again", async () => {
  const f = scripted(ok);
  const prefetch = loadLessonDoc("/api/jobs/handoff/result", f);
  const open = loadLessonDoc("/api/jobs/handoff/result", f);
  assert.equal(open, prefetch);
  assert.equal((await open).kind, "ok");
  assert.equal(f.calls, 1);
  // Taken: a later open fetches afresh (a removal must not hide behind a cached copy).
  forgetLessonDoc("/api/jobs/handoff/result");
  await loadLessonDoc("/api/jobs/handoff/result", f);
  assert.equal(f.calls, 2);
  forgetLessonDoc("/api/jobs/handoff/result");
});
