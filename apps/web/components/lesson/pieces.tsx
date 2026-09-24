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
import { dancerBox, firstWellObserved, markerPoint, sideWord } from "../../lib/dancers";
import { STEPS, stepProgress, type Step } from "../../lib/lessonEngine";
import { legend, lesson as copy } from "../../lib/copy";
import { prefersReducedMotion } from "../../lib/reveal";
import { useCount, useFrameGrabs } from "./hooks";
import type { Lesson } from "../LessonViewer";
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
  up: "M213.66,165.66a8,8,0,0,1-11.32,0L128,91.31,53.66,165.66a8,8,0,0,1-11.32-11.32l80-80a8,8,0,0,1,11.32,0l80,80A8,8,0,0,1,213.66,165.66Z",
  down: "M213.66,101.66l-80,80a8,8,0,0,1-11.32,0l-80-80A8,8,0,0,1,53.66,90.34L128,164.69l74.34-74.35a8,8,0,0,1,11.32,11.32Z",
  left: "M165.66,202.34a8,8,0,0,1-11.32,11.32l-80-80a8,8,0,0,1,0-11.32l80-80a8,8,0,0,1,11.32,11.32L91.31,128Z",
  right: "M181.66,133.66l-80,80a8,8,0,0,1-11.32-11.32L164.69,128,90.34,53.66a8,8,0,0,1,11.32-11.32l80,80A8,8,0,0,1,181.66,133.66Z",
  check: "M229.66,77.66l-128,128a8,8,0,0,1-11.32,0l-56-56a8,8,0,0,1,11.32-11.32L96,188.69,218.34,66.34a8,8,0,0,1,11.32,11.32Z",
  x: "M205.66,194.34a8,8,0,0,1-11.32,11.32L128,139.31,61.66,205.66a8,8,0,0,1-11.32-11.32L116.69,128,50.34,61.66A8,8,0,0,1,61.66,50.34L128,116.69l66.34-66.35a8,8,0,0,1,11.32,11.32L139.31,128Z",
  mirror: "M224,168a8,8,0,0,1-8,8H59.31l18.35,18.34a8,8,0,0,1-11.32,11.32l-32-32a8,8,0,0,1,0-11.32l32-32a8,8,0,0,1,11.32,11.32L59.31,160H216A8,8,0,0,1,224,168ZM189.66,50.34a8,8,0,0,0-11.32,11.32L196.69,80H40a8,8,0,0,0,0,16H196.69l-18.35,18.34a8,8,0,0,0,11.32,11.32l32-32a8,8,0,0,0,0-11.32Z",
  hand: "M188,48a27.75,27.75,0,0,0-12,2.71V44a28,28,0,0,0-54.65-8.6A28,28,0,0,0,80,60v64l-3.82-6.13a28,28,0,0,0-48.6,27.82c16,33.77,28.93,57.72,43.72,72.69C86.24,233.54,103.2,240,128,240a88.1,88.1,0,0,0,88-88V76A28,28,0,0,0,188,48Zm12,104a72.08,72.08,0,0,1-72,72c-20.38,0-33.51-4.88-45.33-16.85C69.44,193.74,57.26,171,41.9,138.58a6.36,6.36,0,0,1-.3-.58,12,12,0,0,1,20.79-12,1.76,1.76,0,0,0,.14.23l18.67,30A8,8,0,0,0,96,152V60a12,12,0,0,1,24,0v60a8,8,0,0,0,16,0V44a12,12,0,0,1,24,0v76a8,8,0,0,0,16,0V76a12,12,0,0,1,24,0Z",
  video: "M251.77,73a8,8,0,0,0-8.21.39L208,97.05V72a16,16,0,0,0-16-16H32A16,16,0,0,0,16,72V184a16,16,0,0,0,16,16H192a16,16,0,0,0,16-16V159l35.56,23.71A8,8,0,0,0,248,184a8,8,0,0,0,8-8V80A8,8,0,0,0,251.77,73ZM192,184H32V72H192V184Zm48-22.95-32-21.33V116.28L240,95Z",
  cube: "M223.68,66.15,135.68,18a15.88,15.88,0,0,0-15.36,0l-88,48.17a16,16,0,0,0-8.32,14v95.64a16,16,0,0,0,8.32,14l88,48.17a15.88,15.88,0,0,0,15.36,0l88-48.17a16,16,0,0,0,8.32-14V80.18A16,16,0,0,0,223.68,66.15ZM128,32l80.34,44L128,120,47.66,76ZM40,90l80,43.78v85.79L40,175.82Zm96,129.57V133.82L216,90v85.78Z",
  stack: "M230.91,172A8,8,0,0,1,228,182.91l-96,56a8,8,0,0,1-8.06,0l-96-56A8,8,0,0,1,36,169.09l92,53.65,92-53.65A8,8,0,0,1,230.91,172ZM220,121.09l-92,53.65L36,121.09A8,8,0,0,0,28,134.91l96,56a8,8,0,0,0,8.06,0l96-56A8,8,0,1,0,220,121.09ZM24,80a8,8,0,0,1,4-6.91l96-56a8,8,0,0,1,8.06,0l96,56a8,8,0,0,1,0,13.82l-96,56a8,8,0,0,1-8.06,0l-96-56A8,8,0,0,1,24,80Zm23.88,0L128,126.74,208.12,80,128,33.26Z",
  plus: "M224,128a8,8,0,0,1-8,8H136v80a8,8,0,0,1-16,0V136H40a8,8,0,0,1,0-16h80V40a8,8,0,0,1,16,0v80h80A8,8,0,0,1,224,128Z",
  question: "M140,180a12,12,0,1,1-12-12A12,12,0,0,1,140,180ZM128,72c-22.06,0-40,16.15-40,36v4a8,8,0,0,0,16,0v-4c0-11,10.77-20,24-20s24,9,24,20-10.77,20-24,20a8,8,0,0,0-8,8v8a8,8,0,0,0,16,0v-.72c18.24-3.35,32-17.9,32-35.28C168,88.15,150.06,72,128,72Zm104,56A104,104,0,1,1,128,24,104.11,104.11,0,0,1,232,128Zm-16,0a88,88,0,1,0-88,88A88.1,88.1,0,0,0,216,128Z",
  eye: "M247.31,124.76c-.35-.79-8.82-19.58-27.65-38.41C194.57,61.26,162.88,48,128,48S61.43,61.26,36.34,86.35C17.51,105.18,9,124,8.69,124.76a8,8,0,0,0,0,6.5c.35.79,8.82,19.57,27.65,38.4C61.43,194.74,93.12,208,128,208s66.57-13.26,91.66-38.34c18.83-18.83,27.3-37.61,27.65-38.4A8,8,0,0,0,247.31,124.76ZM128,192c-30.78,0-57.67-11.19-79.93-33.25A133.47,133.47,0,0,1,25,128,133.33,133.33,0,0,1,48.07,97.25C70.33,75.19,97.22,64,128,64s57.67,11.19,79.93,33.25A133.46,133.46,0,0,1,231.05,128C223.84,141.46,192.43,192,128,192Zm0-112a48,48,0,1,0,48,48A48.05,48.05,0,0,0,128,80Zm0,80a32,32,0,1,1,32-32A32,32,0,0,1,128,160Z",
  hourglass: "M200,75.64V40a16,16,0,0,0-16-16H72A16,16,0,0,0,56,40V76a16.07,16.07,0,0,0,6.4,12.8L114.67,128,62.4,167.2A16.07,16.07,0,0,0,56,180v36a16,16,0,0,0,16,16H184a16,16,0,0,0,16-16V180.36a16.09,16.09,0,0,0-6.35-12.77L141.27,128l52.38-39.6A16.05,16.05,0,0,0,200,75.64ZM184,216H72V180l56-42,56,42.35Zm0-140.36L128,118,72,76V40H184Z",
  trend: "M240,56v64a8,8,0,0,1-16,0V75.31l-82.34,82.35a8,8,0,0,1-11.32,0L96,123.31,29.66,189.66a8,8,0,0,1-11.32-11.32l72-72a8,8,0,0,1,11.32,0L136,140.69,212.69,64H168a8,8,0,0,1,0-16h64A8,8,0,0,1,240,56Z",
  gauge: "M207.06,72.67A111.24,111.24,0,0,0,128,40h-.4C66.07,40.21,16,91,16,153.13V176a16,16,0,0,0,16,16H224a16,16,0,0,0,16-16V152A111.25,111.25,0,0,0,207.06,72.67ZM224,176H119.71l54.76-75.3a8,8,0,0,0-12.94-9.42L99.92,176H32V153.13c0-3.08.15-6.12.43-9.13H56a8,8,0,0,0,0-16H35.27c10.32-38.86,44-68.24,84.73-71.66V80a8,8,0,0,0,16,0V56.33A96.14,96.14,0,0,1,221,128H200a8,8,0,0,0,0,16h23.67c.21,2.65.33,5.31.33,8Z",
};
export type IconName = keyof typeof P;
export function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  return (
    <svg viewBox="0 0 256 256" width={size} height={size} aria-hidden="true" focusable="false" className="ls-icon">
      <path d={P[name]} fill="currentColor" />
    </svg>
  );
}
export const STEP_ICON: Record<Step, IconName> = { watch: "eye", slow: "hourglass", build: "trend", full: "gauge" };

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
    <div className={`ls-pane${compact ? " ls-compact" : ""}${l.yourTurn ? " ls-dim" : ""}`}>
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
    <div className={`ls-stage ${className}`} data-view={view} data-turn={l.yourTurn ? "on" : "off"}>
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
      {l.yourTurn && (
        <div className="ls-turn" aria-live="polite">
          <b>{copy.path.yourTurn}</b>
          <span>{copy.path.yourTurnHint}</span>
        </div>
      )}
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
 * The current eight, large. Weight and size carry the state (DESIGN.md §7), and the
 * numerals turn over on the beat (`useCount`), not on the page's 10 Hz tick.
 * Tapping a numeral seeks to that count.
 */
export function CountBar({ l, big = false }: { l: Lesson; big?: boolean }) {
  const grid = l.structure.grid;
  const count = useCount(l.timeRef, grid);
  const inDance = count >= 1 && count <= grid.countTotal;
  const first = eightStartCount(inDance ? count : l.unit.startCount);
  return (
    <div className={`ls-counts${big ? " ls-big" : ""}`} role="group" aria-label={`Count ${inDance ? countLabel(count) : ""}`}>
      {Array.from({ length: 8 }, (_, i) => first + i).map((c) => (
        <button
          key={c}
          type="button"
          tabIndex={-1}
          className={c === count ? "ls-count ls-on" : c < l.unit.startCount || c > l.unit.endCount ? "ls-count ls-out" : "ls-count"}
          onClick={() => l.seek(timeOfCount(grid, c))}
          disabled={c > grid.countTotal}
        >
          {c <= grid.countTotal ? countLabel(c) : ""}
        </button>
      ))}
    </div>
  );
}

/**
 * Count 1, fixed in one tap: "Tap on 1" while it plays (snaps to the nearest beat),
 * or nudge a whole count either way. Both are `setCountOne` in packages/navigation.
 */
export function CountOneTools({ l, className = "" }: { l: Lesson; className?: string }) {
  const [flash, setFlash] = useState("");
  const note = (s: string) => {
    setFlash(s);
    window.setTimeout(() => setFlash(""), 1400);
  };
  return (
    <div className={`ls-one ${className}`} role="group" aria-label={copy.countOne.heading}>
      <button
        type="button"
        className="ls-btn ls-one-tap"
        onClick={() => {
          l.tapOne();
          note(copy.countOne.tap);
        }}
        title={copy.countOne.tapHint}
        aria-describedby="ls-one-hint"
      >
        {copy.countOne.tap}
      </button>
      <button type="button" className="ls-btn ls-one-nudge" onClick={() => (l.nudgeOne(-1), note(copy.countOne.fixed(-1)))} aria-label={copy.countOne.earlierLabel}>
        {copy.countOne.earlier}
      </button>
      <button type="button" className="ls-btn ls-one-nudge" onClick={() => (l.nudgeOne(1), note(copy.countOne.fixed(1)))} aria-label={copy.countOne.laterLabel}>
        {copy.countOne.later}
      </button>
      <span id="ls-one-hint" className="ls-hint" aria-live="polite">
        {flash || (l.countsFrom !== "hand" ? copy.countOne.guess : "")}
      </span>
    </div>
  );
}

// ------------------------------------------------------------------ the ladder

export function Steps({ l, compact = false }: { l: Lesson; compact?: boolean }) {
  const here = l.mode === "lesson" ? (l.complete ? "done" : l.current.step) : null;
  return (
    <div className="ls-steps" role="group" aria-label={copy.path.stepGroup}>
      {STEPS.map((s) => {
        const prog = stepProgress(l.rounds, l.round, s);
        if (!prog.total) return null;
        const on = here === s;
        const done = l.mode === "lesson" && (here === "done" || prog.done === prog.total);
        return (
          <button
            key={s}
            type="button"
            className={`ls-step${on ? " ls-on" : ""}${done && !on ? " ls-done" : ""}`}
            aria-pressed={on}
            onClick={() => l.setStep(s)}
          >
            <span className="ls-step-top">
              {compact && <Icon name={STEP_ICON[s]} size={18} />}
              <b>{copy.path.steps[s]}</b>
            </span>
            {!compact && <small>{on && s === "build" ? `${l.speed}×` : copy.path.stepSub[s]}</small>}
            <span className="ls-pips" aria-hidden="true">
              {Array.from({ length: prog.total }, (_, k) => (
                <i key={k} className={k < prog.done || (l.mode === "lesson" && here === "done") ? "ls-f" : ""} />
              ))}
            </span>
          </button>
        );
      })}
    </div>
  );
}

export function PlayButton({ l, className = "", label = true, short = false }: { l: Lesson; className?: string; label?: boolean; short?: boolean }) {
  return (
    <button type="button" className={`ls-play ${className}`} onClick={l.togglePlay} aria-label={l.playing ? copy.transport.pause : copy.transport.play}>
      <Icon name={l.playing ? "pause" : "play"} size={26} />
      {label && <span>{l.playing ? copy.transport.pause : short ? copy.transport.play : copy.transport.playUnit(l.unit.label)}</span>}
    </button>
  );
}

export function CheckIn({ l, className = "" }: { l: Lesson; className?: string }) {
  if (!l.checkIn) return null;
  return (
    <div className={`ls-check ${className}`} role="dialog" aria-label={copy.path.check(l.unit.label)}>
      <p>{copy.path.check(l.unit.label)}</p>
      <button type="button" className="ls-btn ls-ghost" onClick={l.again}>
        {copy.path.again}
      </button>
      <button type="button" className="ls-btn ls-accent" onClick={l.gotIt}>
        <Icon name="check" size={18} /> {copy.path.gotIt}
      </button>
    </div>
  );
}

// ------------------------------------------------------------------ path

export function PathNav({ l, row = false }: { l: Lesson; row?: boolean }) {
  const onRef = useRef<HTMLButtonElement | null>(null);
  useEffect(() => {
    onRef.current?.scrollIntoView?.({ block: "nearest", inline: "center" });
  }, [l.unitIndex]);
  return (
    <nav className={`ls-path${row ? " ls-row" : ""}`} aria-label={copy.path.label}>
      {l.units.map((u, i) => {
        const on = i === l.unitIndex;
        const done = l.learned.has(u.id);
        return (
          <button
            key={u.id}
            ref={on ? onRef : undefined}
            type="button"
            className={`ls-node ls-${u.kind}${on ? " ls-on" : ""}${done ? " ls-done" : ""}`}
            aria-current={on ? "step" : undefined}
            onClick={() => l.goUnit(i, { play: false })}
          >
            <span className="ls-dot">{done ? <Icon name="check" size={16} /> : u.kind === "join" ? u.short : u.short}</span>
            <span className="ls-node-lbl">
              {u.label}
              <small>{done ? copy.path.learnedTag : ""}</small>
            </span>
          </button>
        );
      })}
    </nav>
  );
}

export function learnedLine(l: Lesson) {
  return copy.path.learned(l.eights.filter((u) => l.learned.has(u.id)).length, l.eights.length);
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
  urls: (string | null)[];
  boxes: ReturnType<typeof dancerBox>[];
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
  return { urls, boxes: requests.map((r) => r.box) };
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

// ------------------------------------------------------------------ help

/**
 * Everything the old page printed in paragraphs under the stage — the legend, what
 * is out of frame, where the counts came from, the keys — behind one "?", so the
 * default view is the dance and not the caveats. Native `popover`: no focus trap to
 * get wrong, Escape closes it.
 */
export function Help({ l, id }: { l: Lesson; id: string }) {
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
    <>
      <button type="button" className="ls-icon-btn ls-help-btn" popoverTarget={id} aria-label={copy.help.button}>
        <Icon name="question" size={20} />
      </button>
      <div id={id} popover="auto" className="ls-help">
        <p>{legend}</p>
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
          mode="loop"
          onModeChange={() => {}}
          loop={{ startCount: l.unit.startCount, endCount: l.unit.endCount }}
          onLoopChange={() => {}}
          selectedPersonId={l.doc.persons[l.selected].person_id}
          onSelectPerson={() => {}}
          endS={l.endS}
        />
      </div>
    </>
  );
}

// ------------------------------------------------------------------ keyboard

/** DESIGN.md §8 keys, plus T for "Tap on 1". Never while a field has focus. */
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
        if (e.shiftKey) x.stepEight(d);
        else x.seek(x.timeRef.current + d * x.structure.grid.secondsPerCount);
      } else if (k === "m") x.setMirrored((v) => !v);
      else if (k === "s") x.cycleFreeSpeed();
      else if (k === "f") x.setFollow((v) => !v);
      else if (k === "t") x.tapOne();
      else if (k === "l") {
        x.setMode("free");
        x.setFreeLoop((v) => (v === "all" ? "unit" : "all"));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}

/** Speed options for free practice: the old 0.25–1 set (lib/motion SPEEDS). */
export { SPEEDS } from "../../lib/motion";
export type { MotionResult };
