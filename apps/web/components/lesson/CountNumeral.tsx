import { countLabel } from "../../../../packages/navigation/src/core";

/**
 * One count on the strip: its numeral and, unless the learner hid them, the "&" after
 * it — there to SEE, it lights on the off-beat (`half` is the playhead in half counts).
 * Hidden, the eight numerals keep their even columns. Its own file so a test can
 * render it without the 3D.
 */
export function CountNumeral({ c, total, half, ands }: { c: number; total: number; half: number; ands: boolean }) {
  if (c > total) return null;
  return (
    <>
      {countLabel(c)}
      {ands && (
        <span className={`ls-and${half === c + 0.5 ? " ls-on" : ""}`} aria-hidden="true">
          &amp;
        </span>
      )}
    </>
  );
}
