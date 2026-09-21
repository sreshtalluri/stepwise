"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Stage3D from "./Stage3D";
import {
  defaultPersonIndex,
  dancerColor,
  viewLabel,
  VIEW_PRESETS,
  SPEEDS,
  type MotionResult,
  type ViewId,
} from "../lib/motion";

/**
 * The video is the clock. `requestVideoFrameCallback` hands back the exact
 * `mediaTime` of the frame the compositor is about to show, which is the only value
 * that stays locked to the picture through playbackRate changes, seeks and dropped
 * frames — a wall-clock timer drifts within seconds. 95%+ of browsers, Safari 15.4+.
 *
 * The ~5% without it fall back to rAF + `currentTime`, which is coarser (it is
 * quantised to whatever the media element last reported) but never wrong by more
 * than a frame or two.
 */
function useVideoClock(video: HTMLVideoElement | null) {
  const timeRef = useRef(0);
  const [displayTime, setDisplayTime] = useState(0);

  useEffect(() => {
    if (!video) return;
    let cancelled = false;
    let rvfcHandle = 0;
    let rafHandle = 0;
    let lastPublished = -1;

    const publish = (t: number) => {
      timeRef.current = t;
      // The scrubber is React state; the 3D is a ref. Only the cheap one re-renders,
      // and only ~10x a second.
      if (Math.abs(t - lastPublished) > 0.1) {
        lastPublished = t;
        setDisplayTime(t);
      }
    };

    const hasRvfc = typeof (video as any).requestVideoFrameCallback === "function";
    if (hasRvfc) {
      const step = (_now: number, meta: { mediaTime: number }) => {
        if (cancelled) return;
        publish(meta.mediaTime);
        rvfcHandle = (video as any).requestVideoFrameCallback(step);
      };
      rvfcHandle = (video as any).requestVideoFrameCallback(step);
    } else {
      const tick = () => {
        if (cancelled) return;
        publish(video.currentTime);
        rafHandle = requestAnimationFrame(tick);
      };
      rafHandle = requestAnimationFrame(tick);
    }

    // rVFC does not fire while paused, so a scrub with the video stopped would leave
    // the body on the old pose without this.
    const onSeek = () => publish(video.currentTime);
    video.addEventListener("seeked", onSeek);
    video.addEventListener("loadedmetadata", onSeek);

    return () => {
      cancelled = true;
      if (hasRvfc && rvfcHandle) (video as any).cancelVideoFrameCallback(rvfcHandle);
      if (rafHandle) cancelAnimationFrame(rafHandle);
      video.removeEventListener("seeked", onSeek);
      video.removeEventListener("loadedmetadata", onSeek);
    };
  }, [video]);

  return { timeRef, displayTime };
}

export interface LessonViewerProps {
  doc: MotionResult;
  title: string;
  videoUrl: string;
  /** One GLB URL per entry in `doc.persons`. */
  glbUrls: string[];
}

export default function LessonViewer({ doc, title, videoUrl, glbUrls }: LessonViewerProps) {
  const [video, setVideo] = useState<HTMLVideoElement | null>(null);
  const { timeRef, displayTime } = useVideoClock(video);

  const [selected, setSelected] = useState(() => defaultPersonIndex(doc));
  const [view, setView] = useState<ViewId>("camera");
  const [compareView, setCompareView] = useState<ViewId | null>(null);
  const [mirrored, setMirrored] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [playing, setPlaying] = useState(false);
  const [loop, setLoop] = useState<{ a: number; b: number } | null>(null);
  const [loopAnchor, setLoopAnchor] = useState<number | null>(null);
  const [absent, setAbsent] = useState<string[]>([]);
  // D2: the two stages start equal and either can be promoted. Remembered per person
  // in v2 — this session-only version is the honest placeholder.
  const [promoted, setPromoted] = useState<"none" | "3d" | "video">("none");

  const duration = doc.source_video.duration_s;

  useEffect(() => {
    if (video) video.playbackRate = speed;
  }, [video, speed]);

  const seek = useCallback(
    (t: number) => {
      if (!video) return;
      video.currentTime = Math.min(Math.max(t, 0), duration);
    },
    [video, duration],
  );

  // A-B loop. Edges are plain times here; snapping them to count boundaries belongs
  // to the count strip, which is W6's package (DESIGN.md §7).
  useEffect(() => {
    if (!video || !loop) return;
    const onTime = () => {
      if (video.currentTime >= loop.b) video.currentTime = loop.a;
    };
    video.addEventListener("timeupdate", onTime);
    return () => video.removeEventListener("timeupdate", onTime);
  }, [video, loop]);

  const togglePlay = useCallback(() => {
    if (!video) return;
    if (video.paused) void video.play();
    else video.pause();
  }, [video]);

  const cycleLoop = useCallback(() => {
    if (loop) {
      setLoop(null);
      setLoopAnchor(null);
    } else if (loopAnchor === null) {
      setLoopAnchor(timeRef.current);
    } else {
      const a = Math.min(loopAnchor, timeRef.current);
      const b = Math.max(loopAnchor, timeRef.current);
      if (b - a > 0.2) setLoop({ a, b });
      setLoopAnchor(null);
    }
  }, [loop, loopAnchor, timeRef]);

  // DESIGN.md §8 keyboard map. Ignored while a control has focus so the canvas never
  // traps keys away from the rest of the page (OPEN-DECISIONS C6).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable)) return;
      const k = e.key.toLowerCase();
      if (k === " ") { e.preventDefault(); togglePlay(); }
      else if (k === "m") setMirrored((v) => !v);
      else if (k === "l") cycleLoop();
      else if (k === "s") setSpeed((s) => SPEEDS[(SPEEDS.indexOf(s as 1) + 1) % SPEEDS.length]);
      // One count is a W6 concept; until the count strip exists, an arrow steps a
      // quarter-second so the shortcut is not silently dead.
      else if (k === "arrowleft") seek(timeRef.current - 0.25);
      else if (k === "arrowright") seek(timeRef.current + 0.25);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [togglePlay, cycleLoop, seek, timeRef]);

  const grounded = doc.grounding.status === "grounded";
  const chipColor = useMemo(
    () => doc.persons.map((_, i) => dancerColor(doc, i, selected)),
    [doc, selected],
  );

  const stageClass = (which: "3d" | "video") =>
    `stage ${promoted === "none" ? "" : promoted === which ? "promoted" : "demoted"}`;

  return (
    <main className="lesson" data-compare={compareView ? "on" : "off"}>
      <header className="lesson-head">
        <h1 className="title">{title}</h1>
        <p className="sub">Learning from your clip · {formatLength(duration)}</p>
      </header>

      <div className="stages">
        <section className={stageClass("3d")}>
          <span className="view-label">{viewLabel(view, mirrored)}</span>
          <button className="swap" onClick={() => setPromoted(promoted === "3d" ? "none" : "3d")}>
            {promoted === "3d" ? "Show both" : "Show larger"}
          </button>
          <Stage3D
            doc={doc}
            selectedIndex={selected}
            view={view}
            mirrored={mirrored}
            timeRef={timeRef}
            glbUrls={glbUrls}
            onAbsent={setAbsent}
            onResetView={() => setView("camera")}
          />
          <div className="vignette" />
          {compareView && (
            <div className="inset">
              <span className="view-label">{viewLabel(compareView, mirrored)}</span>
              <Stage3D
                doc={doc}
                selectedIndex={selected}
                view={compareView}
                mirrored={mirrored}
                timeRef={timeRef}
                glbUrls={glbUrls}
              />
            </div>
          )}
        </section>

        <section className={stageClass("video")}>
          <span className="view-label">camera view</span>
          <button className="swap" onClick={() => setPromoted(promoted === "video" ? "none" : "video")}>
            {promoted === "video" ? "Show both" : "Show larger"}
          </button>
          <video
            ref={setVideo}
            className="video"
            src={videoUrl}
            playsInline
            preload="auto"
            style={{ transform: mirrored ? "scaleX(-1)" : undefined }}
            onPlay={() => setPlaying(true)}
            onPause={() => setPlaying(false)}
          />
        </section>
      </div>

      <p className="legend">solid = seen · sketchy = unsure · dotted = out of frame</p>
      {!grounded && <p className="note">No floor — feet not visible in this clip.</p>}
      {absent.length > 0 && <p className="note">{absent.join(" · ")}.</p>}

      {doc.persons.length > 1 && (
        <div className="chips dancers" role="group" aria-label="Dancers">
          {doc.persons.map((person, i) => (
            <button
              key={person.person_id}
              className={`chip ${i === selected ? "on" : ""}`}
              onClick={() => setSelected(i)}
              aria-pressed={i === selected}
            >
              <span className="swatch" style={{ background: chipColor[i] }} />
              Dancer {i + 1}
            </button>
          ))}
        </div>
      )}

      <div className="rails">
        <div className="chips views" role="group" aria-label="Views">
          {VIEW_PRESETS.map((preset) => (
            <button
              key={preset.id}
              className={`chip ${view === preset.id ? "on" : ""}`}
              onClick={() => setView(preset.id)}
              aria-pressed={view === preset.id}
            >
              {preset.label}
              {preset.id !== "camera" && <small>est.</small>}
            </button>
          ))}
        </div>
      </div>

      {/* Tier 1, the overview bar. The count strip that sits under it is W6's package
          (DESIGN.md §7); this bar is the whole-dance scrubber it describes, and the
          region outside an active loop is dimmed rather than the inside highlighted. */}
      <div className="overview">
        {loop && (
          <>
            <span className="loop-out" style={{ left: 0, width: `${(loop.a / duration) * 100}%` }} />
            <span className="loop-out" style={{ left: `${(loop.b / duration) * 100}%`, right: 0 }} />
          </>
        )}
        <input
          className="scrub"
          type="range"
          min={0}
          max={duration}
          step={0.01}
          value={displayTime}
          onChange={(e) => seek(Number(e.target.value))}
          aria-label="Scrub the whole dance"
        />
      </div>

      <div className="transport">
        <button className={`btn ${playing ? "active" : ""}`} onClick={togglePlay}>
          {playing ? "Pause" : "Play all"}
          <small>space</small>
        </button>
        <button
          className="btn"
          onClick={() => setSpeed(SPEEDS[(SPEEDS.indexOf(speed as 1) + 1) % SPEEDS.length])}
        >
          {speed}×<small>speed</small>
        </button>
        <button className={`btn ${mirrored ? "active" : ""}`} onClick={() => setMirrored((v) => !v)}>
          {mirrored ? "Mirror on" : "Mirror off"}
          <small>M</small>
        </button>
        <button className={`btn ${loop ? "active" : ""}`} onClick={cycleLoop}>
          {loop ? "Loop on" : loopAnchor !== null ? "Set loop end" : "Loop off"}
          <small>L</small>
        </button>
        <button
          className={`btn ${compareView ? "active" : ""}`}
          onClick={() => setCompareView(compareView ? null : view === "side" ? "front" : "side")}
        >
          {compareView ? "Compare on" : "Compare off"}
          <small>two angles</small>
        </button>
      </div>

      {compareView && (
        <div className="chips views second" role="group" aria-label="Second angle">
          {VIEW_PRESETS.map((preset) => (
            <button
              key={preset.id}
              className={`chip ${compareView === preset.id ? "on" : ""}`}
              onClick={() => setCompareView(preset.id)}
              aria-pressed={compareView === preset.id}
            >
              {preset.label}
            </button>
          ))}
        </div>
      )}
    </main>
  );
}

function formatLength(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}
