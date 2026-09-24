"use client";

/**
 * The parts both lesson layouts are built from. Each reads the shared `Lesson`
 * state (LessonViewer.tsx); none keeps a clock of its own — anything that moves
 * per frame reads `timeRef` on its own rAF and writes the DOM directly.
 */
import Link from "next/link";
import { memo, useEffect, useMemo, useRef, useState } from "react";
import Stage3D from "../Stage3D";
import {
  containFit,
  cropRegions,
  sampleIndexAt,
  sourceAspect,
  steadyCropAt,
  steadyCropTrack,
  viewLabel,
  STEADY_CROP_SIGMA_REDUCED_S,
  STEADY_CROP_SIGMA_S,
  type CropRegion,
  type MotionResult,
  type ViewId,
} from "../../lib/motion";
import {
  accentForPerson,
  countAtTime,
  countLabel,
  eightStartCount,
  loopTimesS,
  timeOfCount,
  type LoopSpan,
} from "../../../../packages/navigation/src/core";
import { footContact, type FootContact } from "../../lib/footContact";
import { tileGrid } from "../../lib/tiles";
import { dancerBox, firstWellObserved, markerPoint, sideWord, stillCrop } from "../../lib/dancers";
import {
  countLoop,
  countName,
  edgeLoop,
  extendAnchor,
  LOOP_ALL,
  LOOP_LENGTHS,
  loopName,
  nudgeEdge,
  presetCounts,
  sameSpan,
  spanDone,
  spanLabel,
} from "../../lib/lessonEngine";
import { lesson as copy } from "../../lib/copy";
import { prefersReducedMotion } from "../../lib/reveal";
import { useCount, useFrameGrabs } from "./hooks";
import type { Lesson, PanelId } from "../LessonViewer";
import { StructureEditor } from "../../../../packages/navigation/src/LessonNavigator";
import "../../../../packages/navigation/src/navigation.css";

export const accentOf = (l: Lesson) => accentForPerson(l.doc, l.selected);

/** The lesson root's class and CSS variables: the accent, and the source frame's aspect for the layout. */
export const rootProps = (l: Lesson, className: string) => ({
  className: `ls ${className}${l.wide ? " ls-wide" : ""}`,
  style: { ["--accent" as string]: accentOf(l), ["--ar" as string]: l.aspect },
});

// ------------------------------------------------------------------ icons

/** Phosphor (regular) paths, inlined: DESIGN.md §11, SVG only, one weight. */
const P = {
  play: "M232.4,114.49,88.32,26.35a16,16,0,0,0-16.2-.3A15.86,15.86,0,0,0,64,39.87V216.13A15.94,15.94,0,0,0,80,232a16.07,16.07,0,0,0,8.36-2.35L232.4,141.51a15.81,15.81,0,0,0,0-27ZM80,215.94V40l143.83,88Z",
  pause: "M200,32H160a16,16,0,0,0-16,16V208a16,16,0,0,0,16,16h40a16,16,0,0,0,16-16V48A16,16,0,0,0,200,32Zm0,176H160V48h40ZM96,32H56A16,16,0,0,0,40,48V208a16,16,0,0,0,16,16H96a16,16,0,0,0,16-16V48A16,16,0,0,0,96,32Zm0,176H56V48H96Z",
  left: "M165.66,202.34a8,8,0,0,1-11.32,11.32l-80-80a8,8,0,0,1,0-11.32l80-80a8,8,0,0,1,11.32,11.32L91.31,128Z",
  right: "M181.66,133.66l-80,80a8,8,0,0,1-11.32-11.32L164.69,128,90.34,53.66a8,8,0,0,1,11.32-11.32l80,80A8,8,0,0,1,181.66,133.66Z",
  check: "M229.66,77.66l-128,128a8,8,0,0,1-11.32,0l-56-56a8,8,0,0,1,11.32-11.32L96,188.69,218.34,66.34a8,8,0,0,1,11.32,11.32Z",
  x: "M205.66,194.34a8,8,0,0,1-11.32,11.32L128,139.31,61.66,205.66a8,8,0,0,1-11.32-11.32L116.69,128,50.34,61.66A8,8,0,0,1,61.66,50.34L128,116.69l66.34-66.35a8,8,0,0,1,11.32,11.32L139.31,128Z",
  mirror: "M224,168a8,8,0,0,1-8,8H59.31l18.35,18.34a8,8,0,0,1-11.32,11.32l-32-32a8,8,0,0,1,0-11.32l32-32a8,8,0,0,1,11.32,11.32L59.31,160H216A8,8,0,0,1,224,168ZM189.66,50.34a8,8,0,0,0-11.32,11.32L196.69,80H40a8,8,0,0,0,0,16H196.69l-18.35,18.34a8,8,0,0,0,11.32,11.32l32-32a8,8,0,0,0,0-11.32Z",
  hand: "M188,48a27.75,27.75,0,0,0-12,2.71V44a28,28,0,0,0-54.65-8.6A28,28,0,0,0,80,60v64l-3.82-6.13a28,28,0,0,0-48.6,27.82c16,33.77,28.93,57.72,43.72,72.69C86.24,233.54,103.2,240,128,240a88.1,88.1,0,0,0,88-88V76A28,28,0,0,0,188,48Zm12,104a72.08,72.08,0,0,1-72,72c-20.38,0-33.51-4.88-45.33-16.85C69.44,193.74,57.26,171,41.9,138.58a6.36,6.36,0,0,1-.3-.58,12,12,0,0,1,20.79-12,1.76,1.76,0,0,0,.14.23l18.67,30A8,8,0,0,0,96,152V60a12,12,0,0,1,24,0v60a8,8,0,0,0,16,0V44a12,12,0,0,1,24,0v76a8,8,0,0,0,16,0V76a12,12,0,0,1,24,0Z",
  video: "M251.77,73a8,8,0,0,0-8.21.39L208,97.05V72a16,16,0,0,0-16-16H32A16,16,0,0,0,16,72V184a16,16,0,0,0,16,16H192a16,16,0,0,0,16-16V159l35.56,23.71A8,8,0,0,0,248,184a8,8,0,0,0,8-8V80A8,8,0,0,0,251.77,73ZM192,184H32V72H192V184Zm48-22.95-32-21.33V116.28L240,95Z",
  cube: "M223.68,66.15,135.68,18a15.88,15.88,0,0,0-15.36,0l-88,48.17a16,16,0,0,0-8.32,14v95.64a16,16,0,0,0,8.32,14l88,48.17a15.88,15.88,0,0,0,15.36,0l88-48.17a16,16,0,0,0,8.32-14V80.18A16,16,0,0,0,223.68,66.15ZM128,32l80.34,44L128,120,47.66,76ZM40,90l80,43.78v85.79L40,175.82Zm96,129.57V133.82L216,90v85.78Z",
  stack: "M230.91,172A8,8,0,0,1,228,182.91l-96,56a8,8,0,0,1-8.06,0l-96-56A8,8,0,0,1,36,169.09l92,53.65,92-53.65A8,8,0,0,1,230.91,172ZM220,121.09l-92,53.65L36,121.09A8,8,0,0,0,28,134.91l96,56a8,8,0,0,0,8.06,0l96-56A8,8,0,1,0,220,121.09ZM24,80a8,8,0,0,1,4-6.91l96-56a8,8,0,0,1,8.06,0l96,56a8,8,0,0,1,0,13.82l-96,56a8,8,0,0,1-8.06,0l-96-56A8,8,0,0,1,24,80Zm23.88,0L128,126.74,208.12,80,128,33.26Z",
  dots: "M140,128a12,12,0,1,1-12-12A12,12,0,0,1,140,128Zm56-12a12,12,0,1,0,12,12A12,12,0,0,0,196,116ZM60,116a12,12,0,1,0,12,12A12,12,0,0,0,60,116Z",
  plus: "M224,128a8,8,0,0,1-8,8H136v80a8,8,0,0,1-16,0V136H40a8,8,0,0,1,0-16h80V40a8,8,0,0,1,16,0v80h80A8,8,0,0,1,224,128Z",
  trend: "M240,56v64a8,8,0,0,1-16,0V75.31l-82.34,82.35a8,8,0,0,1-11.32,0L96,123.31,29.66,189.66a8,8,0,0,1-11.32-11.32l72-72a8,8,0,0,1,11.32,0L136,140.69,212.69,64H168a8,8,0,0,1,0-16h64A8,8,0,0,1,240,56Z",
};
export type IconName = keyof typeof P;
export function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  return (
    <svg viewBox="0 0 256 256" width={size} height={size} aria-hidden="true" focusable="false" className="ls-icon">
      <path d={P[name]} fill="currentColor" />
    </svg>
  );
}

// ------------------------------------------------------------------ 3D panes

/** Stage3D with props that only change when they mean something, so a 10 Hz re-render of the page is not a re-render of the canvas. */
const Stage = memo(Stage3D);

/**
 * A 3D angle in a panel of its own, with its honesty tag in the corner: every angle but
 * the camera's is an estimate (DESIGN.md §7h), so it says "SIDE · est.".
 */
export function AnglePane({ l, angle, focus }: { l: Lesson; angle: ViewId; focus?: boolean }) {
  return (
    <div className="ls-pane">
      <Stage
        doc={l.doc}
        selectedIndex={l.selected}
        view={angle}
        mirrored={l.mirrored}
        timeRef={l.timeRef}
        follow={l.follow}
        focusRef={focus ? l.focusRef : undefined}
        glbUrls={l.glbUrls}
        showEveryone={l.showEveryone}
      />
      <span className="ls-tag ls-corner" title={viewLabel(angle, l.mirrored)}>
        {angle}
        {l.mirrored && ` · ${copy.views.mirrored}`} · {copy.views.est}
      </span>
    </div>
  );
}

/**
 * The camera panel: the one `<video>` (the clock and the sound), with the mesh laid
 * over it from the clip's own camera ("On video") or bare ("Video"). With neither
 * picked it stays mounted off-screen, still playing: it is still the clock.
 */
export function MainStage({
  l,
  children,
  className = "",
  view,
  hidden = false,
}: {
  l: Lesson;
  children?: React.ReactNode;
  className?: string;
  view: "overlay" | "video";
  hidden?: boolean;
}) {
  const { mirrored } = l;
  const tag = view === "overlay" ? copy.views.overlay : l.crop.cropped ? copy.views.videoCropped : copy.views.video;
  return (
    <div className={`ls-stage ${hidden ? "ls-offstage" : ""} ${className}`} data-view={view} aria-hidden={hidden || undefined}>
      <video
        ref={l.setVideo}
        className="ls-video"
        src={l.videoUrl}
        playsInline
        preload="auto"
        onPlay={() => l.setPlaying(true)}
        onPause={() => l.setPlaying(false)}
      />
      {view === "overlay" && (
        // Mirrored by CSS with the video, never on the mesh, so the two flip together.
        <div className="ls-overlay" style={mirrored ? { transform: "scaleX(-1)" } : undefined}>
          <Stage doc={l.doc} selectedIndex={l.selected} view="overlay" mirrored={false} timeRef={l.timeRef} glbUrls={l.glbUrls} onAbsent={l.setAbsent} showEveryone={l.showEveryone} overlay />
        </div>
      )}
      {view === "overlay" && l.multi && <DancerMarkers l={l} />}
      <span className="ls-tag ls-corner">
        {tag}
        {mirrored && ` · ${copy.views.mirrored}`}
      </span>
      {/* Not in frame / unsure, for screen readers; sighted learners get it under "?". */}
      <p className="sr-only" aria-live="polite">
        {l.absent.join(", ")}
      </p>
      {children}
    </div>
  );
}

/** Numbered markers over the video, projected from each dancer's head through the clip's camera. */
function DancerMarkers({ l }: { l: Lesson }) {
  const box = useRef<HTMLDivElement>(null);
  const { doc, timeRef, mirrored } = l;
  useEffect(() => {
    let h = 0;
    let last = -1;
    const tick = () => {
      h = requestAnimationFrame(tick);
      const host = box.current;
      if (!host) return;
      const i = sampleIndexAt(doc.sample_times_s, timeRef.current);
      const w = host.clientWidth, hgt = host.clientHeight;
      const key = i * 1e7 + w * 1e3 + hgt;
      if (key === last) return;
      last = key;
      // object-fit: contain — the frame's box inside the element.
      const fit = containFit(sourceAspect(doc), w, hgt);
      const fw = w * fit.x, fh = hgt * fit.y;
      const ox = (w - fw) / 2, oy = (hgt - fh) / 2;
      doc.persons.forEach((_, k) => {
        const el = host.children[k] as HTMLElement | undefined;
        if (!el) return;
        const p = markerPoint(doc, k, i);
        if (!p || p.x < 0 || p.x > 1 || p.y < 0 || p.y > 1) {
          el.style.display = "none";
          return;
        }
        const x = mirrored ? 1 - p.x : p.x;
        el.style.display = "";
        el.style.transform = `translate(${(ox + x * fw).toFixed(1)}px, ${(oy + Math.max(p.y, 0.03) * fh).toFixed(1)}px) translate(-50%, -50%)`;
      });
    };
    h = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(h);
  }, [doc, timeRef, mirrored]);
  return (
    <div className="ls-markers" ref={box} aria-hidden="true">
      {doc.persons.map((p, k) => (
        <span
          key={p.person_id}
          className={k === l.selected ? "ls-marker ls-on" : "ls-marker"}
          style={{ ["--c" as string]: accentForPerson(doc, k) }}
        >
          {k + 1}
        </span>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ close-ups

/**
 * One region's close-up: real pixels from the SAME `<video>`, cropped to a steadied
 * `crop_rects[region]` and drawn onto a canvas — no second decode, no second clock.
 * A `null` sample clears the canvas (never a stale crop, DESIGN.md §7h).
 *
 * Feet carry a planted/lifted cue from the 3D (lib/footContact.ts). Nothing for hands:
 * MHR's fingers never leave a semi-curled band, so a hand-shape label would say the
 * same thing every frame (see the note in footContact.ts).
 */
export function CropPeek({
  l,
  region,
  contacts,
  onClick,
  pressed,
}: {
  l: Lesson;
  region: CropRegion;
  contacts: { left: FootContact; right: FootContact }[] | null;
  onClick?: () => void;
  pressed?: boolean;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const cueRef = useRef<HTMLSpanElement | null>(null);
  const [live, setLive] = useState(false);
  const { video, doc, timeRef, selected, mirrored } = l;

  useEffect(() => {
    if (!video) return;
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d") ?? null;
    if (!canvas || !ctx) return;
    let handle = 0;
    let reported = false;
    let lastCue = "";
    const sigma = prefersReducedMotion() ? STEADY_CROP_SIGMA_REDUCED_S : STEADY_CROP_SIGMA_S;
    const track = steadyCropTrack(doc, selected, region, sigma);
    const feet = region === "feet" || region === "left_foot" || region === "right_foot";

    const tick = () => {
      handle = requestAnimationFrame(tick);
      const t = timeRef.current;
      const rect = steadyCropAt(doc.sample_times_s, track, t);
      if (feet && contacts && cueRef.current) {
        const c = contacts[sampleIndexAt(doc.sample_times_s, t)];
        const word = (f: FootContact) => (f === "planted" ? copy.crop.down : f === "lifted" ? copy.crop.lifted : "");
        // Compact: "down" when both feet are planted, else which foot is lifted.
        const lifted = c && [c.right === "lifted" && copy.crop.rightShort, c.left === "lifted" && copy.crop.leftShort].filter(Boolean);
        const cue =
          !rect || !c
            ? ""
            : region === "left_foot"
              ? word(c.left)
              : region === "right_foot"
                ? word(c.right)
                : c.left === "unknown" || c.right === "unknown"
                  ? ""
                  : !lifted || lifted.length === 0
                    ? copy.crop.down
                    : lifted.length === 2
                      ? copy.crop.lifted
                      : `${lifted[0]} ${copy.crop.lifted}`;
        if (cue !== lastCue) {
          lastCue = cue;
          cueRef.current.textContent = cue;
          cueRef.current.dataset.lifted = /lifted/.test(cue) ? "1" : "0";
        }
      }
      if (!rect) {
        if (reported) {
          reported = false;
          setLive(false);
        }
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        return;
      }
      const vw = video.videoWidth || doc.source_video.width_px;
      const vh = video.videoHeight || doc.source_video.height_px;
      if (!vw || !vh) return;
      if (!reported) {
        reported = true;
        setLive(true);
      }
      const sx = rect.x * vw, sy = rect.y * vh, sw = rect.width * vw, sh = rect.height * vh;
      const scale = Math.min(canvas.width / sw, canvas.height / sh);
      const dw = sw * scale, dh = sh * scale;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(video, sx, sy, sw, sh, (canvas.width - dw) / 2, (canvas.height - dh) / 2, dw, dh);
    };
    handle = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(handle);
  }, [video, doc, timeRef, selected, region, contacts]);

  const Tag = onClick ? "button" : "div";
  return (
    <Tag
      className="ls-peek"
      {...(onClick ? { type: "button" as const, onClick, "aria-pressed": !!pressed, "aria-label": copy.crop.showIn3d(copy.crop[region]) } : {})}
    >
      <canvas ref={canvasRef} width={160} height={160} style={mirrored ? { transform: "scaleX(-1)" } : undefined} />
      <span className="ls-peek-label">{copy.crop[region]}</span>
      <span className="ls-peek-cue" ref={cueRef} />
      {!live && <span className="ls-peek-off">{copy.crop.unavailable}</span>}
    </Tag>
  );
}

/** Per-sample foot contact for the selected dancer, computed once per dancer. */
export function useFootContacts(l: Lesson, on: boolean) {
  const { doc, selected } = l;
  return useMemo(
    () => (on && doc.grounding.status === "grounded" ? doc.sample_times_s.map((_, i) => footContact(doc, selected, i)) : null),
    [on, doc, selected],
  );
}

/** The Hands or Feet panel: that region's close-ups (one per side when the lesson has them). */
export function CropPanel({ l, kind }: { l: Lesson; kind: "hands" | "feet" }) {
  const contacts = useFootContacts(l, kind === "feet");
  const regions = cropRegions(l.doc, l.selected, l.mirrored).filter((r) => (kind === "hands" ? r.includes("hand") : !r.includes("hand")));
  return (
    <div className="ls-pane ls-crops" data-n={regions.length}>
      {regions.map((r) => (
        <CropPeek key={r} l={l} region={r} contacts={contacts} />
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ counts

/**
 * The current eight's counts, large, over the stage. Weight and size carry the state
 * (DESIGN.md §7), and the numerals turn over on the beat (`useCount`), not on the
 * page's 10 Hz tick. Counts outside the loop fade; a count looped at full speed gets
 * a dot. With `select` (desktop) a count is where a loop starts: tap = loop the chosen
 * length from it, shift-tap or drag across counts = loop exactly those. Without it,
 * tapping a numeral seeks to that count.
 */
export function CountBar({ l, big = false, select = false }: { l: Lesson; big?: boolean; select?: boolean }) {
  const grid = l.structure.grid;
  const total = grid.countTotal;
  const half = useCount(l.timeRef, grid, 0.5);
  const count = Math.floor(half);
  const len = presetCounts(l.loopLen, total);
  const inDance = count >= 1 && count <= total;
  const first = eightStartCount(inDance ? count : (l.loop?.startCount ?? 1));
  const drag = useRef<{ anchor: number; moved: boolean } | null>(null);
  const countAt = (x: number, y: number) => Number(document.elementFromPoint(x, y)?.closest<HTMLElement>("[data-count]")?.dataset.count ?? 0);
  const out = (c: number) => !!l.loop && (c < l.loop.startCount || c > l.loop.endCount);
  return (
    <div
      className={`ls-counts${big ? " ls-big" : ""}`}
      role="group"
      aria-label={copy.countOne.now(inDance ? countLabel(count) : 0)}
      onPointerMove={(e) => {
        const d = drag.current;
        const c = d && countAt(e.clientX, e.clientY);
        if (!d || !c || (c === d.anchor && !d.moved)) return;
        d.moved = true;
        l.setLoop(countLoop(c, len, total, d.anchor), { via: "drag" });
      }}
      onPointerUp={() => (drag.current = null)}
      onPointerCancel={() => (drag.current = null)}
    >
      {Array.from({ length: 8 }, (_, i) => first + i).map((c) => (
        <button
          key={c}
          type="button"
          tabIndex={-1}
          data-count={c}
          className={`ls-count${c === count ? " ls-on" : ""}${out(c) ? " ls-out" : ""}${l.done.has(c) ? " ls-done" : ""}`}
          aria-label={select ? copy.loopLen.fromCount(c, len) : undefined}
          title={select ? copy.loopLen.countHint : undefined}
          onPointerDown={(ev) => {
            if (!select || (ev.pointerType === "mouse" && ev.button !== 0)) return;
            // A touch captures the pointer on this button; release it so a drag reaches the others.
            (ev.target as Element).releasePointerCapture?.(ev.pointerId);
            drag.current = { anchor: c, moved: false };
          }}
          onClick={(ev) => {
            if (!select) return l.seek(timeOfCount(grid, c));
            const d = drag.current;
            drag.current = null;
            if (d?.moved) return;
            const anchor = ev.shiftKey && l.loop ? extendAnchor(l.loop, c) : null;
            l.setLoop(countLoop(c, len, total, anchor), { play: l.playing, via: "count" });
          }}
          disabled={c > total}
        >
          {c <= total ? countLabel(c) : ""}
          {/* The "and" after the count: there to SEE, it lights on the off-beat. */}
          {c <= total && (
            <span className={`ls-and${half === c + 0.5 ? " ls-on" : ""}`} aria-hidden="true">
              &amp;
            </span>
          )}
        </button>
      ))}
    </div>
  );
}

/** "Loop 2 · 4 · 8 · 16 · All counts": how many counts a chip, a count or a preset loops. Under More. */
export function LoopLength({ l }: { l: Lesson }) {
  return (
    <div className="ls-looplen" role="group" aria-label={copy.loopLen.label}>
      <span aria-hidden="true">{copy.loopLen.lead}</span>
      <div className="ls-seg">
        {LOOP_LENGTHS.map((n) => (
          <button key={n} type="button" aria-pressed={l.loopLen === n} aria-label={copy.loopLen.option(n)} onClick={() => l.setLoopLen(n)}>
            {n === LOOP_ALL ? copy.loopLen.all : n}
          </button>
        ))}
      </div>
      <span aria-hidden="true">{copy.loopLen.unit}</span>
    </div>
  );
}

/**
 * The timeline: the whole dance, a tick per count and a taller one with a small "1"
 * on each eight's downbeat. Tap = go there; press and drag across it = loop exactly
 * those counts, snapped to counts and "and"s (Alt: unsnapped); the loop's two handles
 * drag to adjust it (44 px targets, arrow keys ½ a count). One pointer model for
 * mouse and touch, captured on the bar, and `touch-action: none` so a drag here is
 * never the page's swipe. Under it, the loop in words, ½-count nudges and ×.
 */
export function Timeline({ l }: { l: Lesson }) {
  const bar = useRef<HTMLDivElement>(null);
  const grid = l.structure.grid;
  const total = grid.countTotal;
  const endS = l.endS;
  const pct = (t: number) => `${(Math.min(Math.max(t / endS, 0), 1) * 100).toFixed(3)}%`;
  const g = useRef<{ kind: "new" | "start" | "end"; x0: number; from: number; moved: boolean } | null>(null);
  const [preview, setPreview] = useState<LoopSpan | null>(null);
  const timeAtX = (x: number) => {
    const r = bar.current!.getBoundingClientRect();
    return Math.min(Math.max((x - r.left) / r.width, 0), 1) * endS;
  };
  const countAtX = (x: number) => countAtTime(grid, timeAtX(x));
  // "And"s are implied, not marked — unless the click is counting them too.
  const ands = l.clickOn && l.clickMode === "ands";
  const ticks = useMemo(
    () =>
      Array.from({ length: total }, (_, i) => i + 1).flatMap((c) => [
        <span key={c} className="ls-tl-tick" style={{ left: pct(timeOfCount(grid, c)) }} />,
        ...(ands && c < total ? [<span key={`${c}&`} className="ls-tl-tick ls-and-tick" style={{ left: pct(timeOfCount(grid, c + 0.5)) }} />] : []),
      ]),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- pct is over endS
    [grid, total, endS, ands],
  );
  /** The section marker whose tooltip is open on a touch screen (first tap shows it, the tooltip loops). */
  const [secOpen, setSecOpen] = useState<string | null>(null);
  const touchTap = useRef(false);

  const spanFor = (d: NonNullable<typeof g.current>, x: number, free: boolean): LoopSpan | null => {
    const c = countAtX(x);
    if (d.kind === "new") return edgeLoop(d.from, c, total, free);
    const lp = l.loop!;
    // The other edge stays put; a handle dragged past it swaps roles.
    return d.kind === "start" ? edgeLoop(c, lp.endCount + 1, total, free) : edgeLoop(lp.startCount, c, total, free);
  };
  const onDown = (e: React.PointerEvent, kind: "new" | "start" | "end") => {
    if (e.pointerType === "mouse" && e.button !== 0) return;
    e.stopPropagation();
    e.preventDefault();
    setSecOpen(null);
    try {
      bar.current!.setPointerCapture(e.pointerId);
    } catch {
      /* a pointer that is already gone: the moves still reach the bar while over it */
    }
    g.current = { kind, x0: e.clientX, from: countAtX(e.clientX), moved: kind !== "new" };
  };
  const onMove = (e: React.PointerEvent) => {
    const d = g.current;
    if (!d) return;
    if (!d.moved && Math.abs(e.clientX - d.x0) < 6) return;
    d.moved = true;
    setPreview(spanFor(d, e.clientX, e.altKey));
  };
  const onUp = (e: React.PointerEvent) => {
    const d = g.current;
    g.current = null;
    setPreview(null);
    if (!d) return;
    if (!d.moved) return l.seek(timeAtX(e.clientX));
    const s = spanFor(d, e.clientX, e.altKey);
    if (s) l.setLoop(s, { play: l.playing, keep: d.kind !== "new", via: "drag" });
  };
  const nudge = (edge: "start" | "end", d: number) => l.loop && l.setLoop(nudgeEdge(l.loop, edge, d, total), { play: l.playing, keep: true, via: "drag" });

  const shown = preview ?? l.loop;
  const [a, b] = shown ? loopTimesS(grid, shown) : [0, 0];
  const handle = (edge: "start" | "end", t: number) => (
    <span
      role="slider"
      tabIndex={0}
      className={`ls-tl-handle ls-${edge}`}
      style={{ left: pct(t) }}
      aria-label={edge === "start" ? copy.timeline.start : copy.timeline.end}
      aria-valuemin={1}
      aria-valuemax={total}
      aria-valuenow={edge === "start" ? shown!.startCount : shown!.endCount}
      aria-valuetext={countName(edge === "start" ? shown!.startCount : shown!.endCount)}
      onPointerDown={(e) => onDown(e, edge)}
      onKeyDown={(e) => {
        if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
        e.preventDefault();
        e.stopPropagation(); // not the page's seek-by-a-count
        nudge(edge, e.key === "ArrowLeft" ? -0.5 : 0.5);
      }}
    />
  );
  const nudges = (edge: "start" | "end") => {
    const name = edge === "start" ? copy.timeline.start : copy.timeline.end;
    return (
      <span className="ls-tl-nudge">
        <button type="button" onClick={() => nudge(edge, -0.5)} aria-label={copy.timeline.earlier(name)}>
          <Icon name="left" size={14} />
        </button>
        <b>{countName(edge === "start" ? l.loop!.startCount : l.loop!.endCount)}</b>
        <button type="button" onClick={() => nudge(edge, 0.5)} aria-label={copy.timeline.later(name)}>
          <Icon name="right" size={14} />
        </button>
      </span>
    );
  };

  return (
    <div className="ls-tl-wrap">
      <div
        ref={bar}
        className="ls-tl"
        role="slider"
        tabIndex={-1}
        aria-label={copy.timeline.label}
        aria-valuemin={0}
        aria-valuemax={Math.round(endS)}
        aria-valuenow={Math.round(l.displayTime)}
        onPointerDown={(e) => onDown(e, "new")}
        onPointerMove={onMove}
        onPointerUp={onUp}
        onPointerCancel={() => ((g.current = null), setPreview(null))}
      >
        <div className="ls-tl-track">{ticks}</div>
        {/*
          Where each part starts (an eight until the learner edits them): a taller accent
          tick with a dot cap, no text. Hover shows "Section start · Loop this section"
          and a click loops it; on touch the first tap shows that tooltip and the
          tooltip is what loops.
        */}
        {l.eights.map((e) => {
          const on = sameSpan(l.loop, e);
          const loopIt = () => {
            setSecOpen(null);
            l.setLoop(on ? null : { startCount: e.startCount, endCount: e.endCount }, { play: l.playing, via: "marker" });
          };
          return (
            <span key={e.id} className={`ls-tl-sec${on ? " ls-on" : ""}${secOpen === e.id ? " ls-open" : ""}`} style={{ left: pct(timeOfCount(grid, e.startCount)) }}>
              <button
                type="button"
                className={`ls-tl-mark${spanDone(l.done, e) ? " ls-done" : ""}`}
                aria-pressed={on}
                aria-label={copy.timeline.section}
                onPointerDown={(ev) => {
                  ev.stopPropagation();
                  touchTap.current = ev.pointerType === "touch";
                }}
                onClick={() => (touchTap.current && secOpen !== e.id ? setSecOpen(e.id) : loopIt())}
              />
              <button type="button" className="ls-tl-tip" tabIndex={-1} onPointerDown={(ev) => ev.stopPropagation()} onClick={loopIt}>
                {copy.timeline.section}
              </button>
            </span>
          );
        })}
        {shown && <div className={`ls-tl-loop${preview ? " ls-preview" : ""}`} style={{ left: pct(a), width: `calc(${pct(b)} - ${pct(a)})` }} />}
        <div className="ls-tl-head" style={{ left: pct(l.displayTime) }} />
        {shown && handle("start", a)}
        {shown && handle("end", b)}
      </div>
      <div className="ls-tl-read" aria-live="polite">
        {l.loop && !preview ? (
          <>
            <span className="ls-tl-name">{copy.loopLen.lead}</span>
            {nudges("start")}
            <span aria-hidden="true">–</span>
            {nudges("end")}
            <button type="button" className="ls-tl-clear" onClick={() => l.setLoop(null)} aria-label={copy.timeline.clear} title={copy.timeline.clear}>
              <Icon name="x" size={16} />
            </button>
          </>
        ) : preview ? (
          <span className="ls-tl-name">{loopName(preview)}</span>
        ) : (
          <span className="ls-hint" title={copy.timeline.hintFree}>
            {copy.timeline.hint}
          </span>
        )}
      </div>
    </div>
  );
}

/** The top bar's toggles, in order: the camera (with or without the mesh), the 3D angles, then the close-ups. */
const VIEW_BAR: { id: PanelId; label: string }[] = [
  { id: "overlay", label: copy.views.overlay },
  { id: "video", label: copy.views.video },
  { id: "front", label: copy.views.front },
  { id: "side", label: copy.views.side },
  { id: "back", label: copy.views.back },
  { id: "top", label: copy.views.top },
];
const CLOSE_BAR: { id: PanelId; label: string }[] = [
  { id: "hands", label: copy.views.hands },
  { id: "feet", label: copy.views.feet },
];

/**
 * The one top bar: every view a toggle, and every view that is on is a panel. Mirror
 * is a modifier on all of them. Scrolls sideways on a phone.
 */
/**
 * "Original by @creator on TikTok", linking to the video a link lesson was made
 * from (docs/legal/legal-public-learning.md §6(a)2), and under it the choreo and
 * sound the post names ("Choreo @x · ♪ Track · Artist"). Nothing for an upload.
 * Pointer events stop here so a tap on it over the phone stage is not a pause.
 */
export function CreditLine({ l, className = "" }: { l: Lesson; className?: string }) {
  if (!l.credit) return null;
  const stop = (e: React.PointerEvent) => e.stopPropagation();
  const post = copy.postCredit(l.credit);
  const original = copy.credit(l.credit.host, l.credit.creator);
  return (
    <div className={`ls-credit ${className}`} onPointerDown={stop} onPointerUp={stop}>
      <a href={l.credit.url} target="_blank" rel="noopener noreferrer" title={original}>
        {original}
      </a>
      {post && <span className="ls-credit-post" title={copy.postCreditTitle(post)}>{post}</span>}
    </div>
  );
}

export function ViewBar({ l, start, end }: { l: Lesson; start?: React.ReactNode; end?: React.ReactNode }) {
  const toggle = (v: { id: PanelId; label: string }) => (
    <button key={v.id} type="button" className="ls-vbtn" aria-pressed={l.panels.includes(v.id)} onClick={() => l.toggleView(v.id)}>
      {v.label}
    </button>
  );
  return (
    <header className="ls-bar">
      {start}
      <nav className="ls-vbar" aria-label={copy.views.group}>
        {VIEW_BAR.map(toggle)}
        <button type="button" className="ls-vbtn" aria-pressed={l.mirrored} onClick={() => l.setMirrored((v) => !v)}>
          {copy.views.mirror}
        </button>
        <span className="ls-vsep" aria-hidden="true" />
        {CLOSE_BAR.map(toggle)}
      </nav>
      {end}
      <span className="ls-vnote" role="status">
        {l.bumped && copy.views.bumped(l.maxPanels, [...VIEW_BAR, ...CLOSE_BAR].find((v) => v.id === l.bumped)!.label)}
      </span>
    </header>
  );
}

/**
 * Every view that is on, tiled. With `grid` (desktop) the tiles take the grid
 * lib/tiles.ts picks for their count, their shapes and the space: 2 side by side or
 * stacked, 3 across or one big and two small, 4 a 2×2 — never four slivers. Without
 * it (phone) they sit side by side, or in portrait the second as an inset over the
 * first. `children` sit over the tiles — the counts, the phone's overlays. With no
 * camera panel on, the `<video>` stays mounted off-screen: it is the clock and the sound.
 */
export function Panels({
  l,
  grid = false,
  children,
  ...rest
}: { l: Lesson; grid?: boolean; children?: React.ReactNode } & React.HTMLAttributes<HTMLDivElement>) {
  const cam = l.panels.find((p): p is "overlay" | "video" => p === "overlay" || p === "video");
  const others = l.panels.filter((p) => p !== cam);
  // The first 3D angle frames the video crop (useVideoCrop).
  const firstAngle = others.find((p) => p !== "hands" && p !== "feet");
  const stage = <MainStage l={l} view={cam ?? "overlay"} hidden={!cam} />;
  const tiles: string[] = [...(cam ? ["cam"] : []), ...others];
  // The panels' own content size, for the grid (rounded, so a resize settles).
  const box = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState<[number, number]>([0, 0]);
  useEffect(() => {
    const el = box.current;
    if (!el || !grid || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([e]) => setSize([Math.round(e.contentRect.width), Math.round(e.contentRect.height)]));
    ro.observe(el);
    return () => ro.disconnect();
  }, [grid]);
  // Each tile's shape: the camera the clip's, the close-ups two squares, a 3D angle 3:4.
  const shape = (t: string) => (t === "cam" ? l.aspect : t === "hands" || t === "feet" ? 2 : 3 / 4);
  const layout = grid && size[0] > 0 ? tileGrid(tiles.map(shape), size[0], size[1]) : null;
  const fr = (w: number[]) => w.map((x) => `minmax(0, ${x.toFixed(3)}fr)`).join(" ");
  return (
    <div
      ref={box}
      className="ls-panels"
      data-n={tiles.length}
      data-cam={cam ? "" : undefined}
      style={layout ? { gridTemplateColumns: fr(layout.cols), gridTemplateRows: fr(layout.rows) } : undefined}
      {...rest}
    >
      {!cam && stage}
      {tiles.map((t, i) => {
        const a = layout?.areas[i];
        return (
          <div
            key={t}
            className={`ls-tile${t === "cam" ? " ls-cam" : ""}${i === 1 ? " ls-second" : ""}`}
            style={a ? { gridArea: `${a[1]} / ${a[0]} / span ${a[3]} / span ${a[2]}` } : undefined}
          >
            {t === "cam" ? (
              stage
            ) : t === "hands" || t === "feet" ? (
              <CropPanel l={l} kind={t} />
            ) : (
              <AnglePane l={l} angle={t as ViewId} focus={t === firstAngle} />
            )}
          </div>
        );
      })}
      {children}
    </div>
  );
}

/** "0:03.4" — the transport's clock, to a tenth. */
const clock = (t: number) => `${Math.floor(t / 60)}:${(t % 60).toFixed(1).padStart(4, "0")}`;

/**
 * The one thin bar under the panels: play, the time, the speed pill (tap for the
 * next speed), Build up, the click (its settings in a small popover), More — and
 * under it the full-width timeline.
 */
export function BottomBar({ l, more }: { l: Lesson; more: React.ReactNode }) {
  return (
    <div className="ls-bottom">
      <div className="ls-transport">
        <button type="button" className="ls-play" onClick={l.togglePlay} aria-label={l.playing ? copy.transport.pause : copy.transport.play}>
          <Icon name={l.playing ? "pause" : "play"} size={22} />
        </button>
        <span className="ls-time">
          {clock(Math.min(l.displayTime, l.endS))}
          <span className="ls-time-total"> / {clock(l.endS)}</span>
        </span>
        <button
          type="button"
          className="ls-pill"
          onClick={l.cycleSpeed}
          aria-label={copy.transport.speedNext(l.speed)}
          title={copy.transport.speedNext(l.speed)}
        >
          {l.speed}×
        </button>
        <button
          type="button"
          className={`ls-pill${l.buildUp ? " ls-on" : ""}`}
          aria-pressed={l.buildUp}
          onClick={() => l.setBuildUp(!l.buildUp)}
          title={copy.transport.buildHint}
        >
          {copy.transport.build}
        </button>
        <span className="ls-pill-pair">
          <button
            type="button"
            className={`ls-pill${l.clickOn ? " ls-on" : ""}`}
            aria-pressed={l.clickOn}
            onClick={() => l.setClickOn(!l.clickOn)}
            title={copy.click.toggleHint}
          >
            {copy.click.toggle}
          </button>
          <button type="button" className="ls-pill ls-pill-more" popoverTarget="ls-click" aria-label={copy.click.settings}>
            <Icon name="dots" size={16} />
          </button>
        </span>
        <div id="ls-click" popover="auto" className="ls-panel ls-panel-sm">
          <ClickTools l={l} />
        </div>
        {l.next && (
          <button type="button" className="ls-pill ls-next" onClick={() => l.setLoop(l.next, { play: l.playing, via: "step" })}>
            {copy.chips.next(spanLabel(l.next))}
          </button>
        )}
        {more}
      </div>
      <Timeline l={l} />
    </div>
  );
}

/**
 * Count 1: one tap while it plays ("Tap on 1", snaps to the nearest beat), a whole
 * count either way, or one of the beat tracker's other candidates for the 1. All of
 * them are `setCountOne` in packages/navigation.
 */
export function CountOneTools({ l }: { l: Lesson }) {
  const alts = l.alternates.filter((a) => a.shift_counts !== 0);
  return (
    <div className="ls-group" role="group" aria-labelledby="ls-one-h">
      <span className="ls-group-label" id="ls-one-h">
        {copy.countOne.heading}
        {l.countsFrom !== "hand" && <small> {copy.countOne.guess}</small>}
      </span>
      <div className="ls-group-row">
        <button type="button" className="ls-chip ls-strong" onClick={l.tapOne} title={copy.countOne.tapHint}>
          {copy.countOne.tap}
        </button>
        <button type="button" className="ls-chip" onClick={() => l.nudgeOne(-1)} aria-label={copy.countOne.earlierLabel}>
          {copy.countOne.earlier}
        </button>
        <button type="button" className="ls-chip" onClick={() => l.nudgeOne(1)} aria-label={copy.countOne.laterLabel}>
          {copy.countOne.later}
        </button>
      </div>
      {alts.length > 0 && (
        <div className="ls-group-row">
          <span className="ls-hint">{copy.countOne.tryAnother}</span>
          {alts.map((a) => (
            <button key={a.count_one_s} type="button" className="ls-chip" onClick={() => l.tryOne(a.count_one_s)} aria-label={copy.countOne.altLabel(a.shift_counts)}>
              {a.shift_counts > 0 ? `+${a.shift_counts}` : `−${-a.shift_counts}`}
            </button>
          ))}
        </div>
      )}
      <span className="ls-hint">{copy.countOne.tapHint}</span>
    </div>
  );
}

/**
 * The click's options: counts or counts + and, its own volume and the music's, so the
 * two can be balanced. iOS ignores a page setting a video's volume, so no music slider
 * there (it would move and do nothing).
 */
export function ClickTools({ l }: { l: Lesson }) {
  const [ios, setIos] = useState(false);
  useEffect(() => setIos(/iPhone|iPad|iPod/.test(navigator.userAgent)), []);
  return (
    <div className="ls-group" role="group" aria-labelledby="ls-click-h">
      <span className="ls-group-label" id="ls-click-h">
        {copy.click.heading}
      </span>
      <div className="ls-group-row">
        <button type="button" className="ls-chip" aria-pressed={l.clickOn} onClick={() => l.setClickOn(!l.clickOn)}>
          {l.clickOn ? copy.click.on : copy.click.off}
        </button>
        {(["counts", "ands"] as const).map((m) => (
          <button key={m} type="button" className="ls-chip" aria-pressed={l.clickMode === m} onClick={() => (l.setClickMode(m), l.setClickOn(true))}>
            {copy.click[m]}
          </button>
        ))}
      </div>
      <label className="ls-vol">
        <span>{copy.click.volume}</span>
        <input type="range" min={0} max={1} step={0.05} value={l.clickVol} onChange={(e) => l.setClickVol(Number(e.target.value))} />
      </label>
      {!ios && (
        <label className="ls-vol">
          <span>{copy.click.music}</span>
          <input type="range" min={0} max={1} step={0.05} value={l.musicVol} onChange={(e) => l.setMusicVol(Number(e.target.value))} />
        </label>
      )}
      <span className="ls-hint">{l.countsFrom === "hand" ? copy.click.yours : copy.click.guess}</span>
    </div>
  );
}

export function doneLine(l: Lesson) {
  return copy.chips.doneCount(l.done.size, l.structure.grid.countTotal);
}

// ------------------------------------------------------------------ dancers

/**
 * "Who are you learning?" — each dancer as a still from THIS clip, at their first
 * well-observed frame, cropped to them, with their number in their colour. The mesh
 * takes the same colour.
 */
export function DancerPicker({ l, shots }: { l: Lesson; shots: DancerShots }) {
  const { doc } = l;
  const [choice, setChoice] = useState(l.selected);
  if (!l.pickerOpen) return null;
  return (
    <div className="ls-picker" role="dialog" aria-modal="true" aria-labelledby="ls-picker-title">
      <div className="ls-picker-box">
        <h2 id="ls-picker-title">{copy.dancers.title}</h2>
        <p className="ls-muted">{copy.dancers.lead}</p>
        <div className="ls-picker-grid">
          {doc.persons.map((p, k) => {
            const side = sideWord(shots.boxes[k]);
            return (
              <button
                key={p.person_id}
                type="button"
                className="ls-pick"
                aria-pressed={choice === k}
                style={{ ["--c" as string]: accentForPerson(doc, k) }}
                onClick={() => setChoice(k)}
              >
                <span className="ls-pick-img" style={shots.urls[k] ? { backgroundImage: `url(${shots.urls[k]})` } : undefined}>
                  {shots.urls[k] === null && <LiveStill l={l} t={shots.times[k]} box={shots.boxes[k]} />}
                  <span className="ls-ring">{k + 1}</span>
                </span>
                <span className="ls-pick-name">
                  {copy.dancers.name(k + 1)}
                  {side && <small>{copy.dancers.side[side]}</small>}
                </span>
              </button>
            );
          })}
        </div>
        <button
          type="button"
          className="ls-btn ls-accent ls-start"
          style={{ ["--accent" as string]: accentForPerson(doc, choice) }}
          onClick={() => {
            l.chooseDancer(choice);
            l.setPickerOpen(false);
          }}
        >
          {copy.dancers.start}
        </button>
      </div>
    </div>
  );
}

/** One still per dancer from this clip, shared by the picker and the "who" chip. */
export interface DancerShots {
  /** undefined = still coming, null = could not capture (the live fallback shows). */
  urls: (string | null | undefined)[];
  boxes: ReturnType<typeof dancerBox>[];
  times: number[];
}

/**
 * The fallback when a still cannot be captured: the clip itself, paused on that
 * dancer's frame and cropped by CSS to the same `stillCrop` window. Displaying a
 * cross-origin video needs no CORS, so this works where the canvas could not.
 */
function LiveStill({ l, t, box }: { l: Lesson; t: number; box: ReturnType<typeof dancerBox> }) {
  const r = stillCrop(box, l.doc.source_video.width_px, l.doc.source_video.height_px);
  return (
    <video
      className="ls-live-still"
      // #t= puts the first painted frame there even before the seek below lands (iOS).
      src={`${l.videoUrl}#t=${t.toFixed(3)}`}
      muted
      playsInline
      preload="auto"
      aria-hidden="true"
      tabIndex={-1}
      onLoadedMetadata={(e) => (e.currentTarget.currentTime = Math.max(0.001, t))}
      style={{
        width: `${100 / r.width}%`,
        height: `${100 / r.height}%`,
        left: `${(-r.x / r.width) * 100}%`,
        top: `${(-r.y / r.height) * 100}%`,
      }}
    />
  );
}
export function useDancerShots(l: Lesson): DancerShots {
  const { doc } = l;
  const requests = useMemo(
    () =>
      doc.persons.map((_, k) => {
        const i = firstWellObserved(doc, k);
        return { t: doc.sample_times_s[i], box: dancerBox(doc, k, i) };
      }),
    [doc],
  );
  const urls = useFrameGrabs(l.videoUrl, requests, l.multi);
  return { urls, boxes: requests.map((r) => r.box), times: requests.map((r) => r.t) };
}

export function WhoChip({ l, shots, withName = true }: { l: Lesson; shots: DancerShots; withName?: boolean }) {
  if (!l.multi) return null;
  return (
    <button
      type="button"
      className="ls-who"
      style={{ ["--c" as string]: accentOf(l) }}
      onClick={() => l.setPickerOpen(true)}
      aria-label={`${copy.dancers.change}: ${copy.dancers.name(l.selected + 1)}`}
    >
      <span className="ls-who-img" style={shots.urls[l.selected] ? { backgroundImage: `url(${shots.urls[l.selected]})` } : undefined}>
        <b>{l.selected + 1}</b>
      </span>
      {withName && <span>{copy.dancers.name(l.selected + 1)}</span>}
    </button>
  );
}

// ------------------------------------------------------------------ more

/**
 * Everything that is not the views, play, speed, the click or the timeline, in one
 * place: "More" is a popover panel (a bottom sheet on a phone). The legend, what is
 * out of frame and where the counts came from sit at the bottom of it, so the default
 * view is the dance.
 */
export function MoreContent({ l, extra }: { l: Lesson; extra?: React.ReactNode }) {
  const perMinute = Math.round(60 / l.structure.grid.secondsPerCount);
  const counts =
    l.countsFrom === "music"
      ? copy.counts.proposed(perMinute)
      : l.countsFrom === "weak"
        ? copy.counts.weak(perMinute)
        : l.countsFrom === "none"
          ? copy.counts.placeholder(perMinute)
          : null;
  return (
    <div className="ls-more">
      {extra}
      <div className="ls-group">
        <span className="ls-group-label">{copy.loopLen.label}</span>
        <LoopLength l={l} />
      </div>
      <div className="ls-group-row">
        <button type="button" className="ls-chip" aria-pressed={l.follow} onClick={() => l.setFollow((v) => !v)}>
          {l.follow ? copy.transport.followOn : copy.transport.followOff}
        </button>
      </div>
      <CountOneTools l={l} />
      {l.multi && (
        <div className="ls-group">
          <span className="ls-group-label">{copy.views.dancer}</span>
          <div className="ls-group-row">
            <button type="button" className="ls-chip" onClick={() => l.setPickerOpen(true)}>
              {copy.dancers.change}
            </button>
            <button type="button" className="ls-chip" aria-pressed={l.showEveryone} onClick={() => l.setShowEveryone(!l.showEveryone)}>
              {copy.dancers.everyone}
            </button>
          </div>
        </div>
      )}
      <div className="ls-group">
        <span className="ls-group-label">{copy.menu.heading}</span>
        <div className="ls-group-row">
          <button type="button" className="ls-chip" disabled={!l.onRemoveFromMyLessons} onClick={() => l.onRemoveFromMyLessons?.()}>
            {copy.menu.removeMine}
          </button>
          <button type="button" className="ls-chip" disabled={!l.onReportOrRemove} onClick={() => l.onReportOrRemove?.()}>
            {copy.menu.report}
          </button>
          {/* The phone layout never scrolls to the site footer, so the policy is reachable here. */}
          <Link href="/privacy" className="ls-chip">
            {copy.menu.privacy}
          </Link>
        </div>
      </div>
      <details className="ls-about">
        <summary>{copy.help.button}</summary>
        <p>{copy.help.legend}</p>
        <p>{copy.help.estimated}</p>
        {l.doc.grounding.status === "none" && <p>{copy.help.noFloor}</p>}
        {l.absent.length > 0 && <p>{l.absent.join(", ")}.</p>}
        {l.follow && l.crop.clipped && <p>{copy.help.clipped}</p>}
        {counts && <p>{counts}</p>}
        <p className="ls-keys">{copy.help.keys}</p>
        <StructureEditor
          result={l.doc}
          structure={l.structure}
          onStructureChange={l.editStructure}
          countsFrom={l.countsFrom === "hand" ? "hand" : "music"}
          timeS={l.displayTime}
          onSeek={l.seek}
          playing={l.playing}
          onPlayingChange={(p) => (p ? l.play() : l.pause())}
          mode={l.loop ? "loop" : "all"}
          onModeChange={() => {}}
          loop={l.loop ?? { startCount: 1, endCount: l.structure.grid.countTotal }}
          onLoopChange={(s) => l.setLoop(s)}
          selectedPersonId={l.doc.persons[l.selected].person_id}
          onSelectPerson={() => {}}
          endS={l.endS}
        />
      </details>
    </div>
  );
}

// ------------------------------------------------------------------ keyboard

/** DESIGN.md §8 keys, plus B for build up and T for "Tap on 1". Never while a field has focus. */
export function useLessonKeys(l: Lesson) {
  const ref = useRef(l);
  ref.current = l;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName))) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const x = ref.current;
      const k = e.key.toLowerCase();
      if (e.code === "Space") {
        if (el?.tagName === "BUTTON") return; // the focused button gets its own space
        e.preventDefault();
        x.togglePlay();
      } else if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
        e.preventDefault();
        const d = e.key === "ArrowLeft" ? -1 : 1;
        if (e.shiftKey) x.stepLoop(d);
        else x.seek(x.timeRef.current + d * x.structure.grid.secondsPerCount);
      } else if (k === "m") x.setMirrored((v) => !v);
      else if (k === "s") x.cycleSpeed();
      else if (k === "b") x.setBuildUp(!x.buildUp);
      else if (k === "f") x.setFollow((v) => !v);
      else if (k === "t") x.tapOne();
      else if (k === "l") (x.loop ? x.setLoop(null) : x.stepLoop(0));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}

export type { MotionResult };
