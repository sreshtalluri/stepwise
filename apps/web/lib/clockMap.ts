/**
 * The audio clock's arithmetic, pure (components/lesson/audioClock.ts runs it; tested
 * in clockMap.test.ts).
 *
 * The music is one straight line from context time to media time, with the loop
 * folded in exactly the way the stretcher folds it: on reaching the loop's end it
 * carries on from the loop's start, with no gap. Because the line is known ahead of
 * time, so is every wrap: the click is booked across it and the picture is sent to
 * the loop's start early enough to land on it.
 */

/** [start, end) in media seconds. */
export type Loop = readonly [number, number];

export interface TimeMap {
  /** Context seconds at which `input` plays. */
  output: number;
  /** Media seconds, unlooped: it may lie before the loop, never at or past its end. */
  input: number;
  rate: number;
  loop: Loop | null;
}

const raw = (map: TimeMap, at: number) => map.input + (at - map.output) * map.rate;

/** How many times the loop has wrapped by context time `at`. */
export function wrapsAt(map: TimeMap, at: number): number {
  const lp = map.loop;
  const m = raw(map, at);
  return lp && m >= lp[1] ? Math.floor((m - lp[1]) / (lp[1] - lp[0])) + 1 : 0;
}

/** Media seconds the music plays at context time `at`. */
export function mediaAt(map: TimeMap, at: number): number {
  const lp = map.loop;
  const m = raw(map, at);
  return lp && m >= lp[1] ? lp[0] + ((m - lp[1]) % (lp[1] - lp[0])) : m;
}

/** Context seconds from `at` to the next wrap; Infinity with no loop. */
export function untilWrap(map: TimeMap, at: number): number {
  const lp = map.loop;
  if (!lp || !(map.rate > 0)) return Infinity;
  const next = lp[1] + wrapsAt(map, at) * (lp[1] - lp[0]);
  return (next - raw(map, at)) / map.rate;
}

/**
 * A picture-minus-music difference, read the short way round the loop: just before
 * a wrap the picture is already at the loop's start while the music is still at its
 * end, which is a few ms apart, not a whole loop.
 */
export function aroundLoop(d: number, loop: Loop | null): number {
  if (!loop) return d;
  const len = loop[1] - loop[0];
  return d - len * Math.round(d / len);
}

/** The loop a map starting at `input` runs: null when there is none, or it is already behind. */
export function loopFor(loop: Loop | null, input: number): Loop | null {
  return loop && loop[1] - loop[0] > 0.05 && input < loop[1] ? [loop[0], loop[1]] : null;
}

/**
 * How long a seek takes on this device, learned from the ones just made: the picture
 * is sent to the loop's start this long before the music gets there. Held between a
 * frame and a quarter second, so one stalled seek cannot throw the next ones.
 */
export const SEEK_LATENCY_START_S = 0.08;
export function nextSeekLatency(prev: number, measuredS: number): number {
  if (!Number.isFinite(measuredS) || measuredS <= 0) return prev;
  return Math.min(0.25, Math.max(0.02, 0.7 * prev + 0.3 * measuredS));
}

/**
 * `ctx.currentTime` as the page sees it only moves once per audio callback (up to
 * ~20 ms on a phone), so reading it every frame makes a moving mesh judder. It is
 * never ahead of the real audio clock, only behind, so the largest recent
 * (context − wall) difference is the real one. `window` holds those differences.
 * A drop of more than 0.1 s is the context having been suspended: start again.
 */
export function steadyOffset(window: number[], sample: number, size = 30): number {
  if (window.length && sample < Math.max(...window) - 0.1) window.length = 0;
  window.push(sample);
  if (window.length > size) window.shift();
  return Math.max(...window);
}
