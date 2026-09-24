/**
 * The navigation and authoring surface — two scales, always both visible (DESIGN.md §7).
 *
 * Deliberately renderer-free: nothing here imports three.js, a video element, or
 * anything from the viewer. It is fully controlled — the host owns the clock and
 * the structure and passes them down. That is the seam the 3D viewer plugs into.
 *
 * Two exports, because the desktop composition (DESIGN.md §6) is not the phone
 * layout widened: the parts list is a persistent left rail on desktop, while the
 * two navigation tiers and the transport are a full-width foot on both.
 *
 *   phone    <LessonNavigator/>                  (rail folds into the editor)
 *   desktop  <PartsRail/> in the left rail  +  <LessonNavigator/> in the foot
 */

import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import type { MotionResult } from "../../motion-contract/src/ts/generated/motion-result";
import {
  accentForPerson,
  advance,
  clockLabel,
  countAtTime,
  countLabel,
  currentCount,
  deletePart,
  eightStartCount,
  gridFromTaps,
  loopLabel,
  loopSpanForPart,
  loopTimesS,
  mergePartWithNext,
  nearestCountBoundary,
  partLabel,
  partRangeAtCount,
  partRanges,
  renamePart,
  retempo,
  setCountOne,
  splitPartAt,
  timeOfCount,
  timelineEndS,
} from "./core";
import type { LessonStructure, LoopSpan, PlaybackMode } from "./core";
import { copy } from "./copy";

export interface LessonNavigatorProps {
  result: MotionResult;
  structure: LessonStructure;
  onStructureChange: (next: LessonStructure) => void;
  timeS: number;
  onSeek: (timeS: number) => void;
  playing: boolean;
  onPlayingChange: (playing: boolean) => void;
  mode: PlaybackMode;
  onModeChange: (mode: PlaybackMode) => void;
  loop: LoopSpan;
  onLoopChange: (loop: LoopSpan) => void;
  selectedPersonId: string;
  onSelectPerson: (personId: string) => void;
  /**
   * Where the grid on screen came from. A machine-proposed grid
   * (`MotionResult.proposed_counts`) and a hand-set one are the same shape, so
   * this component cannot tell them apart and the host must say. Defaults to
   * `"hand"` — the honest answer for every caller that predates beat detection,
   * and the one that only ever understates.
   */
  countsFrom?: "hand" | "music";
  /** The host's own transport controls — speed and mirror belong to the viewer. */
  children?: ReactNode;
}

const clamp01 = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v);

// ------------------------------------------------------------------ dragging

/**
 * Pointer dragging over a track. `touch-action: none` in the stylesheet means the
 * browser never claims the gesture, so a swipe always scrubs and never does
 * anything else — Soundslice's lesson, and DESIGN.md §12.9.
 */
function useTrackDrag(onFraction: (f: number, settled: boolean) => void) {
  const ref = useRef<HTMLDivElement>(null);
  const startX = useRef(0);
  const moved = useRef(false);

  const fractionAt = (clientX: number) => {
    const el = ref.current;
    if (!el) return 0;
    const r = el.getBoundingClientRect();
    return clamp01((clientX - r.left) / r.width);
  };

  return {
    ref,
    fractionAt,
    handlers: {
      onPointerDown: (e: React.PointerEvent) => {
        e.currentTarget.setPointerCapture(e.pointerId);
        startX.current = e.clientX;
        moved.current = false;
        onFraction(fractionAt(e.clientX), false);
      },
      onPointerMove: (e: React.PointerEvent) => {
        if (!e.currentTarget.hasPointerCapture(e.pointerId)) return;
        if (Math.abs(e.clientX - startX.current) > 4) moved.current = true;
        onFraction(fractionAt(e.clientX), false);
      },
      onPointerUp: (e: React.PointerEvent) => {
        onFraction(fractionAt(e.clientX), !moved.current);
      },
    },
  };
}

// ------------------------------------------------------------------ loop veil

/**
 * Loop de-emphasises the outside; it never highlights the inside (DESIGN.md §7,
 * §12.8). Two paper veils with a soft gradient edge, so the excerpt stays
 * connected to its context instead of being cut out of it.
 */
function LoopVeil({ startFrac, endFrac }: { startFrac: number; endFrac: number }) {
  return (
    <>
      {startFrac > 0.001 && (
        <div className="sw-veil sw-veil-left" style={{ left: 0, width: `${startFrac * 100}%` }} />
      )}
      {endFrac < 0.999 && (
        <div className="sw-veil sw-veil-right" style={{ left: `${endFrac * 100}%`, right: 0 }} />
      )}
    </>
  );
}

// --------------------------------------------------------------- overview bar

/** Tier 1 — the whole dance, always visible, draggable anywhere. */
function OverviewBar(p: LessonNavigatorProps & { endS: number; accent: string }) {
  const { structure, endS, timeS, mode, loop } = p;
  // A ref, not state: a pointermove can arrive in the same tick as its pointerdown,
  // and a state update would not have landed yet — the drag would be dropped.
  const dragging = useRef<null | "start" | "end">(null);

  const track = useTrackDrag((f) => {
    if (dragging.current) return;
    p.onSeek(f * endS);
  });

  const fracOfTime = (t: number) => clamp01(endS > 0 ? t / endS : 0);
  const fracOfCount = (c: number) => fracOfTime(timeOfCount(structure.grid, c));

  const ranges = partRanges(structure);
  const here = partRangeAtCount(structure, currentCount(structure.grid, timeS));
  const [loopStartS, loopEndS] = loopTimesS(structure.grid, loop);

  const dragHandle = (edge: "start" | "end") => ({
    onPointerDown: (e: React.PointerEvent) => {
      e.stopPropagation();
      e.currentTarget.setPointerCapture(e.pointerId);
      dragging.current = edge;
    },
    onPointerMove: (e: React.PointerEvent) => {
      if (dragging.current !== edge) return;
      e.stopPropagation();
      // Loop edges snap to count boundaries, always (DESIGN.md §7).
      const boundary = nearestCountBoundary(structure.grid, track.fractionAt(e.clientX) * endS);
      if (edge === "start") p.onLoopChange({ ...loop, startCount: Math.min(boundary, loop.endCount) });
      else p.onLoopChange({ ...loop, endCount: Math.max(boundary - 1, loop.startCount) });
    },
    onPointerUp: (e: React.PointerEvent) => {
      e.stopPropagation();
      dragging.current = null;
    },
  });

  return (
    <div className="sw-overview">
      <div className="sw-overview-labels">
        <span>{copy.overview.wholeDance}</span>
        <span className="sw-figures">{clockLabel(0)}</span>
        <span className="sw-overview-rule" />
        <span className="sw-figures">{clockLabel(endS)}</span>
      </div>

      <div className="sw-track-hit" ref={track.ref} {...track.handlers}>
        <div className="sw-track">
          {/* The current part, filled in the accent. */}
          <div
            className="sw-track-part"
            style={{
              left: `${fracOfCount(here.startCount) * 100}%`,
              width: `${(fracOfCount(here.endCount + 1) - fracOfCount(here.startCount)) * 100}%`,
              background: p.accent,
            }}
          />
          {/* Part boundaries: heavier ticks. */}
          {ranges.slice(1).map((r) => (
            <div key={r.part.id} className="sw-track-tick" style={{ left: `${fracOfCount(r.startCount) * 100}%` }} />
          ))}
          {mode === "loop" && (
            <LoopVeil startFrac={fracOfTime(loopStartS)} endFrac={fracOfTime(loopEndS)} />
          )}
          <div className="sw-playhead" style={{ left: `${fracOfTime(timeS) * 100}%` }} />
        </div>

        {mode === "loop" && (
          <>
            <div
              className="sw-loop-handle"
              style={{ left: `${fracOfTime(loopStartS) * 100}%` }}
              aria-label={copy.transport.loopStartHandle(loop.startCount)}
              {...dragHandle("start")}
            />
            <div
              className="sw-loop-handle"
              style={{ left: `${fracOfTime(loopEndS) * 100}%` }}
              aria-label={copy.transport.loopEndHandle(loop.endCount)}
              {...dragHandle("end")}
            />
          </>
        )}
      </div>

      <div className="sw-overview-parts">
        {ranges.map((r) => (
          <span
            key={r.part.id}
            className={r.index === here.index ? "sw-overview-part sw-on" : "sw-overview-part"}
            style={{
              left: `${fracOfCount(r.startCount) * 100}%`,
              width: `${(fracOfCount(r.endCount + 1) - fracOfCount(r.startCount)) * 100}%`,
            }}
          >
            {r.part.name}
          </span>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- count strip

/** Tier 2 — the current eight, large. Weight and size carry the state (DESIGN.md §7). */
function CountStrip(p: LessonNavigatorProps & { accent: string }) {
  const { structure, timeS, mode, loop } = p;
  const grid = structure.grid;
  const active = currentCount(grid, timeS);
  const first = eightStartCount(active);
  const counts = Array.from({ length: 8 }, (_, i) => first + i);

  const track = useTrackDrag((f, settled) => {
    const c = first + f * 8;
    p.onSeek(timeOfCount(grid, settled ? Math.floor(c) : c));
  });

  const fracOfCount = (c: number) => clamp01((c - first) / 8);
  const playhead = clamp01((countAtTime(grid, timeS) - first) / 8);

  return (
    <div className="sw-counts-hit" ref={track.ref} {...track.handlers}>
      <div className="sw-counts">
        {counts.map((c) => (
          <span key={c} className={c === active ? "sw-count sw-on" : "sw-count"}>
            {c <= grid.countTotal ? countLabel(c) : ""}
          </span>
        ))}
      </div>
      <div className="sw-count-ticks">
        {counts.map((c) => (
          <span key={c} className="sw-count-tick" />
        ))}
        <div className="sw-count-dot" style={{ left: `${playhead * 100}%`, background: p.accent }} />
      </div>
      {mode === "loop" && <LoopVeil startFrac={fracOfCount(loop.startCount)} endFrac={fracOfCount(loop.endCount + 1)} />}
    </div>
  );
}

// -------------------------------------------------------------- dancer chips

/**
 * One tap, not two (DESIGN.md §7a2). Only the selected dancer is saturated; the
 * others are a muted neutral, so the screen never carries two competing accents.
 */
function DancerChips(p: LessonNavigatorProps) {
  if (p.result.persons.length < 2) return null;
  return (
    <div className="sw-chips" role="group" aria-label={copy.dancers.groupLabel}>
      {p.result.persons.map((person, i) => {
        const on = person.person_id === p.selectedPersonId;
        return (
          <button
            key={person.person_id}
            type="button"
            className={on ? "sw-chip sw-on" : "sw-chip"}
            aria-pressed={on}
            onClick={() => p.onSelectPerson(person.person_id)}
          >
            <span className="sw-swatch" style={{ background: on ? accentForPerson(p.result, i) : "var(--ink-faint)" }} />
            {copy.dancers.chip(i + 1)}
          </button>
        );
      })}
    </div>
  );
}

// ------------------------------------------------------------------ parts rail

/** The persistent desktop left rail (DESIGN.md §6). Not rendered on phone. */
export function PartsRail(p: LessonNavigatorProps) {
  const here = partRangeAtCount(p.structure, currentCount(p.structure.grid, p.timeS));
  const endS = timelineEndS(p.result.sample_times_s);
  return (
    <nav className="sw-rail" aria-label={copy.parts.railLabel}>
      <div className="sw-rail-label">{copy.parts.railLabel}</div>
      {partRanges(p.structure).map((r) => (
        <button
          key={r.part.id}
          type="button"
          className={r.index === here.index ? "sw-rail-part sw-on" : "sw-rail-part"}
          onClick={() => {
            p.onSeek(timeOfCount(p.structure.grid, r.startCount));
            if (p.mode === "loop") p.onLoopChange(loopSpanForPart(r));
          }}
        >
          {partLabel(r)}
        </button>
      ))}
      <button
        type="button"
        className="sw-rail-add"
        onClick={() => p.onStructureChange(splitPartAt(p.structure, currentCount(p.structure.grid, p.timeS), endS))}
      >
        {copy.parts.startHere(currentCount(p.structure.grid, p.timeS))}
      </button>
    </nav>
  );
}

// ------------------------------------------------------------------- transport

const PlayIcon = () => (
  <svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true" focusable="false">
    <path d="M4 2.5 13 8l-9 5.5z" fill="currentColor" />
  </svg>
);

const LoopIcon = () => (
  <svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true" focusable="false">
    <path
      d="M3 6.5a4 4 0 0 1 4-4h5M13 9.5a4 4 0 0 1-4 4H4"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
    />
    <path d="M10 .8 12.6 2.5 10 4.2z M6 11.8 3.4 13.5 6 15.2z" fill="currentColor" />
  </svg>
);

// -------------------------------------------------------------- structure editor

/**
 * Counts and parts, set by hand (PRD §5). Kept behind a native disclosure because
 * it is authoring, not practice — the learner sets counts once and then loops for
 * forty minutes.
 *
 * OPEN-DECISIONS.md A4/A5 are still open on *how* this should feel (drag the grid
 * vs. tap it; long-press a count vs. an explicit control). Nothing gestural is
 * invented here: every edit is a labelled button acting on the playhead.
 */
export function StructureEditor(p: LessonNavigatorProps & { endS: number }) {
  const [taps, setTaps] = useState<number[]>([]);
  const grid = p.structure.grid;
  const count = currentCount(grid, p.timeS);
  const here = partRangeAtCount(p.structure, count);
  const perMinute = Math.round(60 / grid.secondsPerCount);

  const tap = () => {
    const now = performance.now() / 1000;
    const next = taps.length && now - taps[taps.length - 1] > 2.5 ? [now] : [...taps, now];
    setTaps(next);
    const applied = gridFromTaps(p.structure, next, p.endS);
    if (applied) p.onStructureChange(applied);
  };

  return (
    <details className="sw-editor">
      <summary className="sw-btn sw-editor-summary">{copy.counts.editor}</summary>

      <div className="sw-editor-body">
        <p className="sw-editor-note">
          {copy.counts.summary(grid.countTotal, perMinute, `${grid.countOneS.toFixed(2)}s`)}{" "}
          {p.countsFrom === "music" ? copy.counts.byMusic : copy.counts.byHand}
        </p>

        <div className="sw-editor-row">
          <button type="button" className="sw-btn" onClick={() => p.onStructureChange(setCountOne(p.structure, p.timeS, p.endS))}>
            {copy.counts.setOne}
          </button>
          <button type="button" className="sw-btn" onClick={tap}>
            {taps.length < 2 ? copy.counts.tap(taps.length) : copy.counts.tapping(perMinute)}
          </button>
          <button type="button" className="sw-btn" onClick={() => p.onStructureChange(retempo(p.structure, "half", p.endS))}>
            {copy.counts.half}
          </button>
          <button type="button" className="sw-btn" onClick={() => p.onStructureChange(retempo(p.structure, "double", p.endS))}>
            {copy.counts.double}
          </button>
        </div>

        <div className="sw-editor-row">
          <label className="sw-field">
            <span>{copy.parts.nameField}</span>
            <input
              className="sw-input"
              value={here.part.name}
              onChange={(e) => p.onStructureChange(renamePart(p.structure, here.part.id, e.target.value))}
            />
          </label>
          <button
            type="button"
            className="sw-btn"
            onClick={() => p.onStructureChange(splitPartAt(p.structure, count, p.endS))}
          >
            {copy.parts.startHere(count)}
          </button>
          <button
            type="button"
            className="sw-btn"
            onClick={() => p.onStructureChange(mergePartWithNext(p.structure, here.part.id, p.endS))}
          >
            {copy.parts.joinNext(here.part.name)}
          </button>
          <button
            type="button"
            className="sw-btn"
            onClick={() => p.onStructureChange(deletePart(p.structure, here.part.id, p.endS))}
          >
            {copy.parts.remove(here.part.name)}
          </button>
        </div>
      </div>
    </details>
  );
}

// ------------------------------------------------------------------- navigator

export function LessonNavigator(p: LessonNavigatorProps) {
  const endS = timelineEndS(p.result.sample_times_s);
  const personIndex = Math.max(0, p.result.persons.findIndex((x) => x.person_id === p.selectedPersonId));
  const accent = accentForPerson(p.result, personIndex);
  const grid = p.structure.grid;
  const here = partRangeAtCount(p.structure, currentCount(grid, p.timeS));

  const stepCount = (delta: number) => {
    const c = Math.max(1, Math.min(grid.countTotal, currentCount(grid, p.timeS) + delta));
    p.onSeek(timeOfCount(grid, c));
  };
  const stepPart = (delta: number) => {
    const ranges = partRanges(p.structure);
    const next = ranges[Math.max(0, Math.min(ranges.length - 1, here.index + delta))];
    p.onSeek(timeOfCount(grid, next.startCount));
    if (p.mode === "loop") p.onLoopChange(loopSpanForPart(next));
  };

  // DESIGN.md §8 keyboard. Never fires while a field has focus, and never traps
  // focus in the canvas (OPEN-DECISIONS.md C6).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName))) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.code === "Space") {
        e.preventDefault();
        p.onPlayingChange(!p.playing);
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        e.shiftKey ? stepPart(-1) : stepCount(-1);
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        e.shiftKey ? stepPart(1) : stepCount(1);
      } else if (e.key === "l" || e.key === "L") {
        const next: PlaybackMode = p.mode === "loop" ? "all" : "loop";
        if (next === "loop") p.onLoopChange(loopSpanForPart(here));
        p.onModeChange(next);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const chooseMode = (next: PlaybackMode) => {
    if (next === "loop") p.onLoopChange(loopSpanForPart(here));
    p.onModeChange(next);
    p.onPlayingChange(true);
  };

  return (
    <div className="sw-nav" style={{ ["--accent" as string]: accent }}>
      <OverviewBar {...p} endS={endS} accent={accent} />
      <DancerChips {...p} />
      <div className="sw-partline">{partLabel(here)}</div>
      <CountStrip {...p} accent={accent} />

      {/*
        Two rows on a phone: what is playing, then how it is playing. The two mode
        buttons are DESIGN.md §7's pair; the pause control is not in that spec, and
        keeping it on its own row is what stops "Play" and "Play all" reading as
        rivals — they were genuinely confusable side by side.
      */}
      <div className="sw-transport">
        <button type="button" className="sw-btn sw-play" onClick={() => p.onPlayingChange(!p.playing)}>
          {p.playing ? copy.transport.pause : copy.transport.play}
        </button>
        <div className="sw-modes" role="group" aria-label={copy.transport.modeGroupLabel}>
          <button
            type="button"
            className={p.mode === "all" ? "sw-btn sw-on" : "sw-btn"}
            aria-pressed={p.mode === "all"}
            onClick={() => chooseMode("all")}
          >
            <PlayIcon /> {copy.transport.playAll}
          </button>
          <button
            type="button"
            className={p.mode === "loop" ? "sw-btn sw-on" : "sw-btn"}
            aria-pressed={p.mode === "loop"}
            onClick={() => chooseMode("loop")}
          >
            <LoopIcon /> {loopLabel(p.structure, p.loop)}
          </button>
        </div>
        {p.children}
        <span className="sw-keys">{copy.transport.keys}</span>
      </div>

      <StructureEditor {...p} endS={endS} />
    </div>
  );
}

export { advance };
