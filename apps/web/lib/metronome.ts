/**
 * The lesson's click, as data: which clicks fall in the next moment of playback.
 * Pure — the Web Audio side (components/lesson/hooks.ts `useMetronome`) asks this
 * every tick with the video's own time and rate, so the click follows the video
 * clock (speed, pauses, seeks, loop wraps) and never runs on a timer of its own.
 *
 * It is a click on OUR count grid — a guess from the music until the learner sets
 * count 1 — not on the song's real beat.
 */
import { countLabel, timeOfCount, type CountGrid } from "../../../packages/navigation/src/core";

export type ClickMode = "counts" | "ands";

export interface Click {
  /** Timeline (media) seconds the click belongs to. */
  at: number;
  /** Wall seconds from now until it sounds, at the current playback rate. */
  in: number;
  /** 1–8, or 0 for an "and". */
  label: number;
}

/**
 * Clicks with media time in [t, t + lookahead × rate), cut at the loop's end (`loop`
 * is [start, end) in media seconds) and the dance's last count. After a wrap the
 * caller asks again from the loop's start: a click is only ever predicted from where
 * the video actually is, never across a seek.
 */
export function clicksAhead(o: {
  grid: CountGrid;
  loop: readonly [number, number] | null;
  t: number;
  rate: number;
  lookahead: number;
  mode: ClickMode;
}): Click[] {
  const { grid, loop, t, rate, lookahead, mode } = o;
  if (!(rate > 0)) return [];
  const step = mode === "ands" ? 0.5 : 1;
  const danceEnd = timeOfCount(grid, grid.countTotal + 1);
  const end = Math.min(t + lookahead * rate, danceEnd, loop && t < loop[1] ? loop[1] : Infinity);
  const out: Click[] = [];
  // First count position at or after t, on the step grid, never before count 1.
  let c = Math.max(1, Math.ceil(((t - grid.countOneS) / grid.secondsPerCount + 1) / step - 1e-9) * step);
  for (let at = timeOfCount(grid, c); at < end; c += step, at = timeOfCount(grid, c)) {
    out.push({ at, in: (at - t) / rate, label: Number.isInteger(c) ? countLabel(c) : 0 });
  }
  return out;
}

/** The click's loudness, 0–1, remembered per device. Quiet by default: the music leads. */
const VOL_KEY = "stepwise.click-volume.v1";
export const DEFAULT_CLICK_VOLUME = 0.3;
const MUSIC_KEY = "stepwise.music-volume.v1";

const loadVol = (key: string, dflt: number) => {
  try {
    const raw = window.localStorage.getItem(key);
    const v = raw === null ? NaN : Number(raw);
    return v >= 0 && v <= 1 ? v : dflt;
  } catch {
    return dflt;
  }
};
const saveVol = (key: string, v: number) => {
  try {
    window.localStorage.setItem(key, String(v));
  } catch {
    /* private mode: kept for this visit only */
  }
};
export const loadClickVolume = () => loadVol(VOL_KEY, DEFAULT_CLICK_VOLUME);
export const saveClickVolume = (v: number) => saveVol(VOL_KEY, v);
export const loadMusicVolume = () => loadVol(MUSIC_KEY, 1);
export const saveMusicVolume = (v: number) => saveVol(MUSIC_KEY, v);
