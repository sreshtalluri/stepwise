import { test } from "node:test";
import assert from "node:assert/strict";
import { clicksAhead, loadClickVolume, saveClickVolume, DEFAULT_CLICK_VOLUME } from "./metronome";
import { loopTimesS } from "../../../packages/navigation/src/core";

// count 1 at 0.2 s, 0.5 s a count, 40 counts (dance ends at 20.2 s)
const grid = { countOneS: 0.2, secondsPerCount: 0.5, countTotal: 40 };
const near = (a: number, b: number) => Math.abs(a - b) < 1e-9;
const at = (cs: { at: number }[]) => cs.map((c) => Math.round(c.at * 1000) / 1000);

test("counts: the next beats in the lookahead, 1 accented by its label", () => {
  const cs = clicksAhead({ grid, loop: null, t: 0.1, rate: 1, lookahead: 1.2, mode: "counts" });
  assert.deepEqual(at(cs), [0.2, 0.7, 1.2]);
  assert.deepEqual(cs.map((c) => c.label), [1, 2, 3]);
  assert.ok(near(cs[0].in, 0.1));
  const eight = clicksAhead({ grid, loop: null, t: 3.6, rate: 1, lookahead: 1, mode: "counts" });
  assert.deepEqual(eight.map((c) => c.label), [8, 1], "count 9 is the next 1");
});

test("counts + and: an 'and' halfway, label 0", () => {
  const cs = clicksAhead({ grid, loop: null, t: 0.2, rate: 1, lookahead: 1, mode: "ands" });
  assert.deepEqual(at(cs), [0.2, 0.45, 0.7, 0.95]);
  assert.deepEqual(cs.map((c) => c.label), [1, 0, 2, 0]);
});

test("the playback rate stretches wall time, not the grid", () => {
  const cs = clicksAhead({ grid, loop: null, t: 0.2, rate: 0.5, lookahead: 1, mode: "counts" });
  assert.deepEqual(at(cs), [0.2], "half speed: half as much music in the same lookahead");
  const two = clicksAhead({ grid, loop: null, t: 0.1, rate: 0.5, lookahead: 1.3, mode: "ands" });
  assert.deepEqual(at(two), [0.2, 0.45, 0.7]);
  assert.ok(near(two[1].in, 0.7), "(0.45 - 0.1) / 0.5");
});

test("any speed on the 0.05 grid: the click interval is the count's length over the rate", () => {
  for (const rate of [0.25, 0.65, 1, 1.25]) {
    const cs = clicksAhead({ grid, loop: null, t: 0.2, rate, lookahead: 10, mode: "counts" });
    const gaps = cs.slice(1).map((c, i) => c.in - cs[i].in);
    assert.ok(gaps.length > 2 && gaps.every((g) => near(g, grid.secondsPerCount / rate)), `${rate}×: ${gaps}`);
    const ands = clicksAhead({ grid, loop: null, t: 0.2, rate, lookahead: 10, mode: "ands" });
    assert.ok(near(ands[1].in - ands[0].in, grid.secondsPerCount / 2 / rate), `${rate}× and`);
  }
});

test("a loop cuts the lookahead at its end; after the wrap the loop's start clicks first", () => {
  const loop = loopTimesS(grid, { startCount: 3.5, endCount: 6 }); // 3& – 6: [1.45, 3.2)
  const before = clicksAhead({ grid, loop, t: 2.9, rate: 1, lookahead: 1, mode: "ands" });
  assert.deepEqual(at(before), [2.95], "nothing at or past 3.2 (count 7) until the video is there");
  const after = clicksAhead({ grid, loop, t: 1.45, rate: 1, lookahead: 0.3, mode: "ands" });
  assert.deepEqual(at(after), [1.45, 1.7]);
  assert.deepEqual(after.map((c) => c.label), [0, 4], "the loop starts on an and");
});

test("a seek re-reads from where the video is; nothing before count 1 or after the dance", () => {
  const cs = clicksAhead({ grid, loop: null, t: 10.3, rate: 1, lookahead: 0.5, mode: "counts" });
  assert.deepEqual(at(cs), [10.7]);
  assert.deepEqual(clicksAhead({ grid, loop: null, t: 0, rate: 1, lookahead: 0.15, mode: "ands" }), []);
  assert.deepEqual(clicksAhead({ grid, loop: null, t: 20.1, rate: 1, lookahead: 1, mode: "counts" }), []);
  assert.deepEqual(clicksAhead({ grid, loop: null, t: 1, rate: 0, lookahead: 1, mode: "counts" }), [], "paused");
});

test("no drift: clicks are read off the grid, never summed, so an hour in is still exact", () => {
  const long = { countOneS: 0.2, secondsPerCount: 0.4838, countTotal: 100000 };
  const cs = clicksAhead({ grid: long, loop: null, t: 3600, rate: 0.75, lookahead: 0.5, mode: "ands" });
  for (const c of cs) {
    const k = (c.at - long.countOneS) / (long.secondsPerCount / 2);
    assert.ok(Math.abs(k - Math.round(k)) < 1e-6, `${c.at} is on the half-count grid`);
  }
});

test("click volume: quiet by default, remembered, private mode never throws", () => {
  const store = new Map<string, string>();
  (globalThis as any).window = {
    localStorage: { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v) },
  };
  assert.equal(loadClickVolume(), DEFAULT_CLICK_VOLUME);
  saveClickVolume(0.6);
  assert.equal(loadClickVolume(), 0.6);
  store.set("stepwise.click-volume.v1", "7");
  assert.equal(loadClickVolume(), DEFAULT_CLICK_VOLUME);
  (globalThis as any).window = { localStorage: { getItem: () => { throw new Error("x"); }, setItem: () => { throw new Error("x"); } } };
  assert.equal(loadClickVolume(), DEFAULT_CLICK_VOLUME);
  saveClickVolume(0.1);
  delete (globalThis as any).window;
});
