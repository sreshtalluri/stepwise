import Link from "next/link";
import { ACCENT, markBox, markShapes } from "../../lib/brand";
import { PRODUCT_NAME } from "../../lib/copy";

const [x0, y0, x1, y1] = markBox();
// Static, built from lib/brand.ts constants only.
const SHAPES = markShapes({ ink: "currentColor", head: ACCENT });

/**
 * The brand mark for the header lockup. Drawn from lib/brand.ts, the same
 * source as every icon file. Strokes take currentColor; the head is the
 * accent, the one lit count.
 */
export default function Mark({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox={`${x0} ${y0} ${x1 - x0} ${y1 - y0}`}
      aria-hidden="true"
      focusable="false"
      dangerouslySetInnerHTML={{ __html: SHAPES }}
    />
  );
}

/** The header lockup: the mark and the wordmark, linking home. The same on every page. */
export function Lockup() {
  return (
    <Link href="/" className="fd-logo fd-lockup">
      <Mark />
      {PRODUCT_NAME}
    </Link>
  );
}
