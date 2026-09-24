"use client";

/**
 * The parts both lesson layouts are built from. Each reads the shared `Lesson`
 * state (LessonViewer.tsx); none keeps a clock of its own — anything that moves
 * per frame reads `timeRef` on its own rAF and writes the DOM directly.
 */
import { memo, useEffect, useMemo, useRef, useState } from "react";
import Stage3D from "../Stage3D";
import {
  cropRegions,
  sampleIndexAt,
  steadyCropAt,
  steadyCropTrack,
  viewLabel,
  STEADY_CROP_SIGMA_REDUCED_S,
  STEADY_CROP_SIGMA_S,
  VIEW_PRESETS,
  type CropRegion,
  type MotionResult,
  type ViewId,
} from "../../lib/motion";
import { accentForPerson, countLabel, eightStartCount, timeOfCount } from "../../../../packages/navigation/src/core";
import { footContact, type FootContact } from "../../lib/footContact";
import { dancerBox, firstWellObserved, markerPoint, sideWord, stillCrop } from "../../lib/dancers";
import { chipLoop, countLoop, extendAnchor, LOOP_LENGTHS, spanDone, spanLabel, type Eight } from "../../lib/lessonEngine";
import { lesson as copy } from "../../lib/copy";
import { prefersReducedMotion } from "../../lib/reveal";
import { useCount, useFrameGrabs } from "./hooks";
import type { Lesson, MainView } from "../LessonViewer";
import { StructureEditor } from "../../../../packages/navigation/src/LessonNavigator";
import "../../../../packages/navigation/src/navigation.css";

export const accentOf = (l: Lesson) => accentForPerson(l.doc, l.selected);

/** 3D angles a pane can take. "overlay" is not an angle — it is the main stage's "On video". */
export const ANGLES = VIEW_PRESETS.filter((p) => p.id !== "overlay");

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

/** A 3D angle in a pane of its own (desktop extra angles, the phone inset). */
export function AnglePane({
  l,
  angle,
  onAngle,
  onRemove,
  compact,
  focus,
}: {
  l: Lesson;
  angle: ViewId;
  onAngle?: (v: ViewId) => void;
  onRemove?: () => void;
  compact?: boolean;
  /** This pane frames the video crop too (see useVideoCrop). */
  focus?: boolean;
}) {
  return (
    <div className={`ls-pane${compact ? " ls-compact" : ""}`}>
      <Stage
        doc={l.doc}
        selectedIndex={l.selected}
        view={angle}
        mirrored={l.mirrored}
        timeRef={l.timeRef}
        follow={l.follow}
        focusRef={focus ? l.focusRef : undefined}
        glbUrls={l.glbUrls}
      />
      <div className="ls-pane-bar">
        {onAngle ? (
          <label className="ls-select">
            <span className="sr-only">{copy.views.angle}</span>
            <select value={angle} onChange={(e) => onAngle(e.target.value as ViewId)}>
              {ANGLES.map((a) => (
                <option key={a.id} value={a.id}>
                  {viewLabel(a.id, l.mirrored)}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <span className="ls-tag">{viewLabel(angle, l.mirrored)}</span>
        )}
        {onRemove && (
          <button type="button" className="ls-icon-btn" onClick={onRemove} aria-label={copy.views.removeAngle}>
            <Icon name="x" size={16} />
          </button>
        )}
      </div>
    </div>
  );
}

/**
 * The main stage: the one `<video>` (the clock), with the mesh laid over it from the
 * clip's own camera ("On video"), or a 3D angle over it ("3D"). In 3D the video stays
 * mounted and playing underneath — it is still the clock and the sound.
 */
export function MainStage({
  l,
  children,
  className = "",
  view = l.view,
}: {
  l: Lesson;
  children?: React.ReactNode;
  className?: string;
  /** The phone on its side shows the 3D in a pane of its own, so its main stage never is one. */
  view?: Lesson["view"];
}) {
  const { mirrored } = l;
  const tag =
    view === "3d"
      ? viewLabel(l.angle, mirrored)
      : view === "overlay"
        ? viewLabel("overlay", mirrored)
        : l.crop.cropped
          ? "camera view, cropped"
          : "camera view";
  return (
    <div className={`ls-stage ${className}`} data-view={view}>
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
          <Stage doc={l.doc} selectedIndex={l.selected} view="overlay" mirrored={false} timeRef={l.timeRef} glbUrls={l.glbUrls} onAbsent={l.setAbsent} overlay />
        </div>
      )}
      {view === "overlay" && l.multi && <DancerMarkers l={l} />}
      {view === "3d" && (
        <div className="ls-3d">
          <Stage
            doc={l.doc}
            selectedIndex={l.selected}
            view={l.angle}
            mirrored={mirrored}
            timeRef={l.timeRef}
            follow={l.follow}
            focusRef={l.focusRef}
            glbUrls={l.glbUrls}
            onAbsent={l.setAbsent}
            onResetView={() => l.setAngle("camera")}
          />
        </div>
      )}
      <span className="ls-tag ls-stage-tag">
        {tag}
        {view === "3d" && l.doc.grounding.status === "none" ? `, ${copy.help.noFloor.toLowerCase()}` : ""}
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
      const aspect = doc.source_video.width_px / doc.source_video.height_px;
      const fw = Math.min(w, hgt * aspect), fh = fw / aspect;
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

export function CloseUps({ l, className = "", onRegion }: { l: Lesson; className?: string; onRegion?: (r: CropRegion) => void }) {
  const contacts = useFootContacts(l, l.showCrops);
  if (!l.showCrops) return null;
  const regions = cropRegions(l.doc, l.selected, l.mirrored);
  return (
    <div className={`ls-closeups ${regions.length > 2 ? "ls-sides" : ""} ${className}`}>
      {regions.map((r) => (
        <CropPeek key={r} l={l} region={r} contacts={contacts} onClick={onRegion ? () => onRegion(r) : undefined} />
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
  const count = useCount(l.timeRef, grid);
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
        l.setLoop(countLoop(c, l.loopLen, total, d.anchor));
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
          aria-label={select ? copy.loopLen.fromCount(c, l.loopLen) : undefined}
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
            l.setLoop(countLoop(c, l.loopLen, total, anchor), { play: l.playing });
          }}
          disabled={c > total}
        >
          {c <= total ? countLabel(c) : ""}
        </button>
      ))}
    </div>
  );
}

/** "Loop 2 · 4 · 8 counts": how many counts a tap on a chip or a count loops. */
export function LoopLength({ l }: { l: Lesson }) {
  return (
    <div className="ls-looplen" role="group" aria-label={copy.loopLen.label}>
      <span aria-hidden="true">{copy.loopLen.lead}</span>
      <div className="ls-seg">
        {LOOP_LENGTHS.map((n) => (
          <button key={n} type="button" aria-pressed={l.loopLen === n} aria-label={copy.loopLen.option(n)} onClick={() => l.setLoopLen(n)}>
            {n}
          </button>
        ))}
      </div>
      <span aria-hidden="true">{copy.loopLen.unit}</span>
    </div>
  );
}

/**
 * The one row that drives the lesson: a chip per part (an eight until the learner
 * edits them). Tap = loop the chosen length from its first count; tap again (or
 * "All") = the whole dance; shift-tap or drag across chips = loop those whole chips.
 * A quiet tick marks a chip whose counts have all been looped at full speed. Above
 * it, a plain scrubber for the whole clip, and the loop length.
 */
export function EightChips({ l }: { l: Lesson }) {
  const drag = useRef<{ anchor: number; moved: boolean } | null>(null);
  const chipAt = (x: number, y: number) => {
    const el = document.elementFromPoint(x, y)?.closest<HTMLElement>("[data-eight]");
    return el ? Number(el.dataset.eight) : -1;
  };
  // Lit when the loop touches it, so four counts inside an eight still show where they are.
  const inLoop = (e: Eight) => !!l.loop && e.startCount <= l.loop.endCount && e.endCount >= l.loop.startCount;
  const endS = l.endS;
  const total = l.structure.grid.countTotal;
  return (
    <div className="ls-chips-wrap">
      <div className="ls-chips-top">
        <input
          className="ls-scrub"
          type="range"
          min={0}
          max={endS}
          step={0.01}
          value={Math.min(l.displayTime, endS)}
          onChange={(e) => l.seek(Number(e.target.value))}
          aria-label={copy.chips.scrub}
        />
        <LoopLength l={l} />
      </div>
      <div
        className="ls-chips"
        role="group"
        aria-label={copy.chips.group}
        onPointerMove={(e) => {
          const d = drag.current;
          if (!d) return;
          const k = chipAt(e.clientX, e.clientY);
          if (k < 0 || (k === d.anchor && !d.moved)) return;
          d.moved = true;
          l.setLoop(chipLoop(l.loop, l.eights[k], l.loopLen, total, l.eights[d.anchor]));
        }}
        onPointerUp={() => (drag.current = null)}
        onPointerCancel={() => (drag.current = null)}
      >
        {l.eights.map((e, k) => {
          const looped = inLoop(e);
          const playing = l.here?.id === e.id;
          const done = spanDone(l.done, e);
          const span = spanLabel(e);
          return (
            <button
              key={e.id}
              type="button"
              data-eight={k}
              className={`ls-chip8${looped ? " ls-on" : ""}${playing ? " ls-here" : ""}`}
              aria-pressed={looped}
              aria-label={`${e.label === span ? span : `${e.label}, ${span}`}${done ? `, ${copy.chips.done}` : ""}`}
              onPointerDown={(ev) => {
                if (ev.pointerType === "mouse" && ev.button !== 0) return;
                drag.current = { anchor: k, moved: false };
              }}
              onClick={(ev) => {
                const d = drag.current;
                drag.current = null;
                if (d?.moved) return;
                const from = l.loop?.startCount ?? 0;
                const anchor = ev.shiftKey ? (l.eights.find((x) => x.startCount <= from && x.endCount >= from) ?? null) : null;
                l.setLoop(chipLoop(l.loop, e, l.loopLen, total, anchor), { play: l.playing });
              }}
            >
              <span>{e.n}</span>
              {done && <Icon name="check" size={12} />}
            </button>
          );
        })}
        <button
          type="button"
          className={`ls-chip8 ls-all${!l.loop ? " ls-on" : ""}`}
          aria-pressed={!l.loop}
          onClick={() => l.setLoop(null)}
        >
          {copy.chips.all}
        </button>
      </div>
    </div>
  );
}

/** Play · speed · Build up · More. Everything else lives under More. */
export function Transport({ l, more, className = "" }: { l: Lesson; more: React.ReactNode; className?: string }) {
  return (
    <div className={`ls-transport ${className}`}>
      <button type="button" className="ls-play" onClick={l.togglePlay} aria-label={l.playing ? copy.transport.pause : copy.transport.play}>
        <Icon name={l.playing ? "pause" : "play"} size={26} />
      </button>
      <div className="ls-seg ls-speeds" role="group" aria-label={copy.transport.speedLabel}>
        {TRANSPORT_SPEEDS.map((s) => (
          <button key={s} type="button" aria-pressed={!l.buildUp && l.speedPick === s} onClick={() => (l.setBuildUp(false), l.setSpeed(s))}>
            {s}×
          </button>
        ))}
      </div>
      <button
        type="button"
        className={`ls-build${l.buildUp ? " ls-on" : ""}`}
        aria-pressed={l.buildUp}
        onClick={() => l.setBuildUp(!l.buildUp)}
        title={copy.transport.buildHint}
      >
        <Icon name="trend" size={18} />
        <span>
          {copy.transport.build}
          {l.buildUp && <b> {l.speed}×</b>}
        </span>
      </button>
      {l.next && (
        <button type="button" className="ls-next" onClick={() => l.setLoop(l.next, { play: l.playing })}>
          {copy.chips.next(spanLabel(l.next))}
          <Icon name="right" size={16} />
        </button>
      )}
      {more}
    </div>
  );
}
const TRANSPORT_SPEEDS = [0.5, 0.75, 1] as const;

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

const VIEWS: { id: MainView; label: string }[] = [
  { id: "overlay", label: copy.views.overlay },
  { id: "video", label: copy.views.video },
  { id: "3d", label: copy.views.threeD },
];
const cap = (s: string) => s[0].toUpperCase() + s.slice(1);

/**
 * Everything that is not play, speed or the loop, in one place: "More" is a panel
 * on a desktop and the expanded bottom sheet on a phone. The legend, what is out of
 * frame and where the counts came from — the paragraphs the old page printed under
 * the stage — sit at the bottom of it, so the default view is the dance.
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
      <div className="ls-group" role="group" aria-label={copy.views.group}>
        <span className="ls-group-label">{copy.views.group}</span>
        <div className="ls-group-row">
          {VIEWS.map((v) => (
            <button key={v.id} type="button" className="ls-chip" aria-pressed={l.view === v.id} onClick={() => l.setView(v.id)}>
              {v.label}
            </button>
          ))}
        </div>
        {l.view === "3d" && (
          <div className="ls-group-row">
            {ANGLES.map((a) => (
              <button key={a.id} type="button" className="ls-chip" aria-pressed={l.angle === a.id} onClick={() => l.setAngle(a.id)}>
                {cap(a.label)}
                {a.id !== "camera" && <small>{copy.views.est}</small>}
              </button>
            ))}
          </div>
        )}
        <div className="ls-group-row">
          <button type="button" className="ls-chip" aria-pressed={l.mirrored} onClick={() => l.setMirrored((v) => !v)}>
            {l.mirrored ? copy.transport.mirrorOn : copy.transport.mirrorOff}
          </button>
          <button type="button" className="ls-chip" aria-pressed={l.showCrops} onClick={() => l.setShowCrops((v) => !v)}>
            {l.showCrops ? copy.crop.toggleOn : copy.crop.toggleOff}
          </button>
          <button type="button" className="ls-chip" aria-pressed={l.follow} onClick={() => l.setFollow((v) => !v)}>
            {l.follow ? copy.transport.followOn : copy.transport.followOff}
          </button>
          <button type="button" className="ls-chip" aria-pressed={l.speedPick === 0.25 && !l.buildUp} onClick={() => (l.setBuildUp(false), l.setSpeed(0.25))}>
            0.25×
          </button>
        </div>
      </div>
      {extra}
      <CountOneTools l={l} />
      {l.multi && (
        <div className="ls-group">
          <span className="ls-group-label">{copy.views.dancer}</span>
          <div className="ls-group-row">
            <button type="button" className="ls-chip" onClick={() => l.setPickerOpen(true)}>
              {copy.dancers.change}
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
