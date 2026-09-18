"use client";

import { useCallback, useRef, useState } from "react";
import StageFigure from "./StageFigure";
import { legend, marketing, reveal as revealCopy } from "../lib/copy";
import { useRevealOrbit } from "../lib/reveal";

/**
 * The live demo lesson in the marketing hero — docs/DESIGN.md §7d, §7e.
 * A stranger can drag and spin this before signing up for anything.
 *
 * ── On the clip ──────────────────────────────────────────────────────────
 * There is no cleared demo video yet. `evaluation/clips.yaml`'s `demo-public`
 * slot is marked `needs-permission` and is empty, and no clip may appear on a
 * public page without the dancer's explicit permission. The private testing
 * clips are `rights: untested` and must NOT be wired in here.
 *
 * So this component takes the clip as a prop and renders the placeholder body
 * when it is null. When a cleared clip lands, pass it — and pass W5's viewer
 * as `renderBody` — without editing this file.
 */

export type DemoClip = {
  /** MotionResult document for the lesson (packages/motion-contract). */
  motionResultUrl: string;
  videoUrl: string;
  glbUrl: string;
  /** MotionResult.accent_color.hex. */
  accentHex: string;
  /** Shown with the clip. Required: a cleared clip has a named dancer. */
  credit: string;
};

type Props = {
  clip: DemoClip | null;
  /** W5's viewer, injected. Gets the current azimuth in degrees. */
  renderBody?: (azimuth: number) => React.ReactNode;
  /** Stable id for the once-per-lesson reveal orbit (DESIGN.md §7f). */
  lessonId?: string;
  /** Arm the reveal orbit — set true the moment the lesson becomes ready. */
  revealArmed?: boolean;
  height?: number;
  showChips?: boolean;
};

const VIEW_AZIMUTH: Record<string, number> = {
  front: 0,
  side: 90,
  back: 180,
  top: 0,
};

const normalise = (deg: number) => ((deg % 360) + 360) % 360;

export default function DemoStage({
  clip,
  renderBody,
  lessonId = "demo",
  revealArmed = false,
  height = 340,
  showChips = true,
}: Props) {
  const [azimuth, setAzimuth] = useState(0);
  const [view, setView] = useState("front");
  const [dragged, setDragged] = useState(false);
  const drag = useRef<{ x: number; from: number } | null>(null);

  const revealAzimuth = useRevealOrbit(lessonId, revealArmed);
  const shown = revealAzimuth ?? azimuth;

  const onPointerDown = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    (e.target as Element).setPointerCapture?.(e.pointerId);
    drag.current = { x: e.clientX, from: azimuth };
  }, [azimuth]);

  const onPointerMove = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    if (!drag.current) return;
    // 0.6°/px: a full turn is roughly a 600px drag, which is one comfortable
    // swipe on a phone and one deliberate sweep on a trackpad.
    const next = normalise(drag.current.from + (e.clientX - drag.current.x) * 0.6);
    setAzimuth(next);
    setDragged(true);
    setView(nearestView(next, view));
  }, [view]);

  const endDrag = useCallback(() => {
    drag.current = null;
  }, []);

  const onKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    e.preventDefault();
    const next = normalise(azimuth + (e.key === "ArrowRight" ? 15 : -15));
    setAzimuth(next);
    setDragged(true);
    setView(nearestView(next, view));
  }, [azimuth, view]);

  const current = marketing.views.find((v) => v.id === view) ?? marketing.views[0];
  const tilted = view === "top";

  return (
    <div>
      <div
        className="stage"
        role="application"
        tabIndex={0}
        aria-label={`Demo lesson. ${revealCopy.hint}`}
        style={{ height, cursor: drag.current ? "grabbing" : "grab" }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onKeyDown={onKeyDown}
      >
        {/* Honesty label, always on, never a badge or an icon — DESIGN.md §4. */}
        <span className="stage-label">{current.note}</span>
        {!dragged && !revealArmed && (
          <span
            className="stage-label"
            style={{ left: "auto", right: 14, transition: "opacity 160ms" }}
          >
            {marketing.hero.dragHint}
          </span>
        )}

        <div
          style={{
            position: "absolute",
            inset: 0,
            transform: tilted ? "perspective(700px) rotateX(52deg)" : undefined,
            transformOrigin: "50% 80%",
            transition: "transform 160ms cubic-bezier(0.16,1,0.3,1)",
          }}
        >
          {renderBody ? (
            renderBody(shown)
          ) : (
            <StageFigure
              azimuth={shown}
              accent={clip?.accentHex}
              height={height * 0.55}
            />
          )}
        </div>

        {showChips && (
          <div
            style={{
              position: "absolute",
              left: 12,
              right: 12,
              bottom: 12,
              display: "flex",
              gap: 6,
            }}
          >
            {marketing.views.map((v) => (
              <button
                key={v.id}
                type="button"
                onClick={() => {
                  setView(v.id);
                  setAzimuth(VIEW_AZIMUTH[v.id] ?? 0);
                  setDragged(true);
                }}
                aria-pressed={view === v.id}
                className={`chip${view === v.id ? " chip-on" : ""}`}
              >
                {v.label}
              </button>
            ))}
          </div>
        )}
      </div>

      <p className="meta" style={{ marginTop: 10 }}>
        {legend}
        {clip ? ` · ${clip.credit}` : ""}
      </p>
    </div>
  );
}

function nearestView(azimuth: number, currentView: string): string {
  if (currentView === "top") return "top";
  const a = normalise(azimuth);
  if (a < 45 || a >= 315) return "front";
  if (a < 135) return "side";
  if (a < 225) return "back";
  return "side";
}
