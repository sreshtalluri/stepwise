import { test } from "node:test";
import assert from "node:assert/strict";
import { aroundLoop, loopFor, mediaAt, nextSeekLatency, steadyOffset, untilWrap, wrapsAt, type TimeMap } from "./clockMap";

const near = (a: number, b: number) => assert.ok(Math.abs(a - b) < 1e-9, `${a} vs ${b}`);

// Music at media 4.0 when the context reads 100, half speed, looping [4, 6).
const map: TimeMap = { output: 100, input: 4, rate: 0.5, loop: [4, 6] };

test("no loop: a straight line at the playback rate", () => {
  const plain = { ...map, loop: null };
  near(mediaAt(plain, 110), 9);
  assert.equal(wrapsAt(plain, 1e6), 0);
  assert.equal(untilWrap(plain, 100), Infinity);
});

test("the loop's end carries straight on from its start, every pass", () => {
  near(mediaAt(map, 103), 5.5); // inside the first pass
  near(mediaAt(map, 104), 4); // the end is the start: [start, end)
  near(mediaAt(map, 105), 4.5);
  near(mediaAt(map, 108.5), 4.25); // third pass
  assert.deepEqual([103, 104, 105, 108, 108.5].map((t) => wrapsAt(map, t)), [0, 1, 1, 2, 2]);
});

test("a map that starts before the loop plays into it, then loops", () => {
  const lead = { ...map, input: 3 };
  near(mediaAt(lead, 101), 3.5);
  near(mediaAt(lead, 106), 4); // 3 s of media later: the loop's end, so its start
  assert.equal(wrapsAt(lead, 105.9), 0);
});

test("untilWrap is wall time to the next wrap, at the playback rate", () => {
  near(untilWrap(map, 100), 4); // 2 s of media at 0.5x
  near(untilWrap(map, 103.9), 0.1);
  near(untilWrap(map, 104), 4); // just wrapped: a whole pass to go
  near(untilWrap({ ...map, rate: 1 }, 101.5), 0.5);
});

test("loopFor: no loop once the playhead is past it, or when it is too short to loop", () => {
  assert.deepEqual(loopFor([4, 6], 5), [4, 6]);
  assert.deepEqual(loopFor([4, 6], 1), [4, 6]);
  assert.equal(loopFor([4, 6], 6), null);
  assert.equal(loopFor([4, 4.01], 4), null);
  assert.equal(loopFor(null, 4), null);
});

test("seek latency follows the device, without one stall throwing it", () => {
  near(nextSeekLatency(0.08, 0.18), 0.11);
  assert.equal(nextSeekLatency(0.08, 5), 0.25); // a stalled seek
  assert.equal(nextSeekLatency(0.02, 0.001), 0.02); // never under a frame
  assert.equal(nextSeekLatency(0.08, NaN), 0.08);
});

test("steadyOffset: the stepped context clock read as a steady one", () => {
  const win: number[] = [];
  // The real offset is 50; the page sees it up to 20 ms stale.
  const seen = [49.985, 49.999, 49.982, 49.99].map((s) => steadyOffset(win, s));
  assert.deepEqual(seen, [49.985, 49.999, 49.999, 49.999]);
  // Suspended for 3 s: the context stood still while the wall clock ran.
  assert.equal(steadyOffset(win, 46.99), 46.99);
  for (let i = 0; i < 40; i++) steadyOffset(win, 46.9);
  assert.equal(win.length, 30);
  assert.equal(steadyOffset(win, 46.95), 46.95);
});

test("aroundLoop: picture at the loop's start, music still at its end, is a few ms apart", () => {
  near(aroundLoop(4.0 - 5.98, [4, 6]), 0.02); // the picture landed 20 ms before the wrap
  near(aroundLoop(-0.03, [4, 6]), -0.03);
  near(aroundLoop(-0.03, null), -0.03);
});
