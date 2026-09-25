/**
 * The grid maths behind /owner's "where is count 1?" choices. The detector's
 * beat grid (`count_one_s + k * spc`) is trusted; only which beat of the bar
 * is 1 is in question, so the choices are the four beats of one bar.
 */

export const OPTION_LETTERS = ["A", "B", "C", "D"] as const;

/** The first four grid beats at or after 0 s: options A-D, one bar. */
export function barOptions(countOneS: number, spc: number): number[] {
  // The epsilon keeps a beat sitting exactly on 0 s (after float noise) as A.
  const first = countOneS - Math.floor(countOneS / spc + 1e-6) * spc;
  return OPTION_LETTERS.map((_, i) => +(first + i * spc).toFixed(3));
}

/** Which option (0-3) is the same beat of the bar as `t`. */
export function optionOf(t: number, countOneS: number, spc: number): number {
  const k = Math.round((t - barOptions(countOneS, spc)[0]) / spc);
  return ((k % 4) + 4) % 4;
}

/**
 * The count (1-8) showing at time `t` when 1 is at `origin`, and the beat index
 * (negative during the lead-in before it), so a caller can tell a new beat.
 */
export function countAt(t: number, origin: number, spc: number): { beat: number; count: number } {
  const beat = Math.floor((t - origin) / spc + 1e-3);
  return { beat, count: (((beat % 8) + 8) % 8) + 1 };
}

/** Where Play starts: a few counts before the 1 ("5 6 7 8"), never before 0. */
export function leadInStart(origin: number, spc: number, counts = 4): number {
  return Math.max(0, origin - counts * spc);
}
