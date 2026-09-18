/**
 * The placeholder body on its floor — docs/DESIGN.md §10.
 *
 * This is NOT the viewer. The real R3F/GLB viewer is W5's surface. This is the
 * stand-in the marketing hero and the processing screen draw while there is no
 * cleared demo clip and no finished lesson, and it exists so the *interaction*
 * (drag to spin, shadow swings with the camera) is real and reviewable now.
 *
 * Three things from DESIGN.md are load-bearing here and must survive any
 * redraw:
 *   §10 two-tone shading — a flat single fill reads as a bathroom pictogram.
 *   §10 a real floor surface with an unmistakable horizon — a 1px line is not
 *       a floor.
 *   §9  the contact shadow swings as you orbit. This is the signature motion
 *       and the only self-explaining "you can rotate this" affordance. It
 *       keeps moving under prefers-reduced-motion, because it is information.
 */

type Props = {
  /** Degrees. 0 = front (camera view). */
  azimuth: number;
  /** Lesson accent, from MotionResult.accent_color.hex. Falls back to --accent. */
  accent?: string;
  height?: number;
};

const deg2rad = (d: number) => (d * Math.PI) / 180;

export default function StageFigure({ azimuth, accent, height = 200 }: Props) {
  const a = deg2rad(azimuth);
  const facing = Math.cos(a); // 1 = front, -1 = back
  const side = Math.sin(a);

  // Foreshortening: the body narrows as it turns toward profile. Floored at
  // 0.52 — below that it collapses into a sliver and stops reading as a body.
  const squash = 0.52 + 0.48 * Math.abs(facing);

  // Two-tone break follows the light (DESIGN.md §10: accent mid-tone, shadow
  // side is the accent at 70% lightness). The split slides across the body as
  // it rotates instead of being a fixed 55% stripe.
  const split = Math.round((0.5 + 0.28 * side) * 100);

  // The contact shadow swings opposite the camera and shortens as the body
  // turns edge-on.
  const shadowShift = side * 26;
  const shadowWidth = 96 + 34 * Math.abs(facing);

  const color = accent ?? "var(--accent)";
  const gradientId = `two-tone-${Math.round(azimuth)}`;

  return (
    <div
      aria-hidden="true"
      style={{ position: "absolute", inset: 0, pointerEvents: "none" }}
    >
      {/* floor — a surface, not a grid */}
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          bottom: 0,
          height: "30%",
          background: "linear-gradient(#252118, #2e2920)",
        }}
      />
      {/* horizon, with real weight */}
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          bottom: "30%",
          height: 2,
          background: "rgba(216, 208, 195, 0.3)",
        }}
      />
      {/* the signature: contact shadow, swinging with the camera */}
      <div
        style={{
          position: "absolute",
          bottom: "25%",
          left: `calc(50% + ${shadowShift}px)`,
          transform: "translateX(-50%)",
          width: shadowWidth,
          height: 18,
          borderRadius: "50%",
          // Dark-on-dark: the shadow needs real weight or it disappears
          // against the floor, and it is the only "you can rotate this"
          // affordance on the page.
          background:
            "radial-gradient(ellipse, rgba(0,0,0,0.9) 20%, rgba(0,0,0,0.45) 55%, transparent 75%)",
        }}
      />
      {/* viewBox is trimmed to the figure's own bounds (feet end at y=142), so
          bottom-aligning the svg puts the feet on the floor rather than
          floating the body above the horizon. */}
      <svg
        viewBox="0 0 132 146"
        width={height * 0.8}
        height={height}
        style={{
          position: "absolute",
          bottom: "26%",
          left: "50%",
          transform: `translateX(-50%) scaleX(${squash})`,
        }}
      >
        <defs>
          <linearGradient id={gradientId} x1="0" x2="1">
            <stop offset="0" stopColor={color} />
            <stop offset={`${split}%`} stopColor={color} />
            <stop offset={`${split}%`} stopColor={color} stopOpacity="0.55" />
            <stop offset="1" stopColor={color} stopOpacity="0.55" />
          </linearGradient>
        </defs>
        <g fill={`url(#${gradientId})`}>
          <circle cx="66" cy="18" r="14" />
          <path d="M53 36h26l7 52H46z" />
          <rect x="50" y="88" width="14" height="54" rx="7" />
          <rect x="68" y="88" width="14" height="54" rx="7" />
          <rect
            x="30"
            y="40"
            width="13"
            height="45"
            rx="6"
            transform="rotate(16 36 40)"
          />
          <rect
            x="89"
            y="40"
            width="13"
            height="45"
            rx="6"
            transform="rotate(-16 95 40)"
          />
        </g>
      </svg>
    </div>
  );
}
