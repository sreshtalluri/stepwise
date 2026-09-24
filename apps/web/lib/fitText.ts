/**
 * The longest of `options` (longest first) that fits `width`, by `measure`.
 * Falls back to the last, shortest one. Used for the paste field's placeholder,
 * which a browser clips rather than wraps (components/front/LinkDoor.tsx).
 */
export function fitText(options: readonly string[], width: number, measure: (s: string) => number): string {
  return options.find((s) => measure(s) <= width) ?? options[options.length - 1];
}
