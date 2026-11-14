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
 *
 * `wrap`: the loop wraps on the audio clock, exactly at its end with no gap
 * (lib/clockMap.ts), so the clicks carry on from the loop's start.
 */
export function clicksAhead(o: {
  grid: CountGrid;
  loop: readonly [number, number] | null;
  t: number;
  rate: number;
  lookahead: number;
  mode: ClickMode;
  wrap?: boolean;
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
  if (o.wrap && loop && loop[1] > loop[0] && t < loop[1] && t + lookahead * rate > loop[1]) {
    const spent = (loop[1] - t) / rate;
    for (const c of clicksAhead({ ...o, t: loop[0], lookahead: lookahead - spent })) out.push({ ...c, in: c.in + spent });
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

/**
 * Sound timing, per device: how many ms late the sound reaches the learner (wireless
 * headphones and speakers), so the picture and the mesh wait for it. Negative for a
 * screen that shows late. 0 until they move it.
 */
const SYNC_KEY = "stepwise.sound-timing-ms.v1";
export const SYNC_MIN_MS = -200;
export const SYNC_MAX_MS = 400;
export function loadSyncOffsetMs(): number {
  try {
    const v = Number(window.localStorage.getItem(SYNC_KEY) ?? "0");
    return v >= SYNC_MIN_MS && v <= SYNC_MAX_MS ? v : 0;
  } catch {
    return 0;
  }
}
export const saveSyncOffsetMs = (ms: number) => saveVol(SYNC_KEY, ms);
