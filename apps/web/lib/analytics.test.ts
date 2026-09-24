import { test } from "node:test";
import assert from "node:assert/strict";
import { createAnalytics, optedOut, referrerHost, type EventName } from "./analytics";

function harness() {
  const sent: unknown[][] = [];
  const a = createAnalytics((body) => sent.push(JSON.parse(body)));
  return { a, sent };
}

test("events wait in memory and go as one batch", () => {
  const { a, sent } = harness();
  a.track("tap_on_one", undefined, "job_1");
  a.track("speed_changed", { speed: 0.5 });
  assert.equal(sent.length, 0);
  a.flush();
  assert.deepEqual(sent, [[{ name: "tap_on_one", lesson: "job_1" }, { name: "speed_changed", props: { speed: 0.5 } }]]);
  a.flush();
  assert.equal(sent.length, 1, "an empty queue sends nothing");
});

test("a full batch goes at 20, and batches never exceed 20", () => {
  const { a, sent } = harness();
  for (let i = 0; i < 45; i++) a.track("tap_on_one");
  assert.deepEqual(sent.map((b) => b.length), [20, 20]);
  a.hide();
  assert.deepEqual(sent.map((b) => b.length), [20, 20, 5]);
});

test("only allowlisted names are queued", () => {
  const { a } = harness();
  a.track("pageview" as EventName);
  a.track("mousemove" as EventName);
  assert.equal(a.pending(), 0);
});

test("play time is sent in 30 s buckets, the remainder on hide", () => {
  const { a, sent } = harness();
  for (let i = 0; i < 70; i++) a.addPlay(1, "job_1");
  assert.equal(a.pending(), 2);
  a.hide();
  assert.deepEqual(sent[0].map((e) => (e as { props: { seconds: number } }).props.seconds), [30, 30, 10]);
  a.hide();
  assert.equal(sent.length, 1, "the remainder is sent once");
});

test("switching lessons closes the previous lesson's bucket", () => {
  const { a, sent } = harness();
  a.addPlay(12, "job_1");
  a.addPlay(5, "job_2");
  a.hide();
  assert.deepEqual(sent[0], [
    { name: "play_seconds", props: { seconds: 12 }, lesson: "job_1" },
    { name: "play_seconds", props: { seconds: 5 }, lesson: "job_2" },
  ]);
});

test("the batch carries no identifier of any kind", () => {
  const { a, sent } = harness();
  a.track("loop_created", { counts: 4, start: 1, snapped: true, via: "drag" }, "job_1");
  a.flush();
  assert.deepEqual(Object.keys(sent[0][0] as object).sort(), ["lesson", "name", "props"]);
});

test("referrer is the host only, and empty for our own site", () => {
  assert.equal(referrerHost("https://www.TikTok.com/@someone/video/1?x=2", "stepwise.app"), "www.tiktok.com");
  assert.equal(referrerHost("https://stepwise.app/lessons", "stepwise.app"), "");
  assert.equal(referrerHost("", "stepwise.app"), "");
});

test("Global Privacy Control and Do Not Track switch it off", () => {
  assert.equal(optedOut({ globalPrivacyControl: true }), true);
  assert.equal(optedOut({ doNotTrack: "1" }), true);
  assert.equal(optedOut({ doNotTrack: null }), false);
});
