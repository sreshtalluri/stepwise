"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Stage3D from "./Stage3D";
import {
  defaultPersonIndex,
  viewLabel,
  VIEW_PRESETS,
  SPEEDS,
  type MotionResult,
  type ViewId,
} from "../lib/motion";
import { LessonNavigator } from "../../../packages/navigation/src/index";
import type { LessonStructure, LoopSpan, PlaybackMode } from "../../../packages/navigation/src/index";
import { isStillProposed, loopTimesS, timelineEndS } from "../../../packages/navigation/src/index";
import "../../../packages/navigation/src/navigation.css";
import { restore, save as saveStructure, seed } from "../lib/lessonStructure";

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
  /** Storage scope for the counts and parts the learner authors here. */
  lessonId: string;
}

export default function LessonViewer({ doc, title, videoUrl, glbUrls, lessonId }: LessonViewerProps) {
  const [video, setVideo] = useState<HTMLVideoElement | null>(null);
  const { timeRef, displayTime } = useVideoClock(video);

  const [selected, setSelected] = useState(() => defaultPersonIndex(doc));
  const [view, setView] = useState<ViewId>("camera");
  const [compareView, setCompareView] = useState<ViewId | null>(null);
  const [mirrored, setMirrored] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [playing, setPlaying] = useState(false);
  const [absent, setAbsent] = useState<string[]>([]);

  // The clip ends at the last sample slot, never at source_video.duration_s
  // (packages/navigation/src/core.ts, and the reason the contract insists
  // sample_times_s exists).
  const endS = useMemo(() => timelineEndS(doc.sample_times_s), [doc]);

  // The learner's counts and parts. See lib/lessonStructure.ts for why the
  // store is client-side and where a server store attaches once D5 lands.
  //
  // Two steps, not one. The initial value must be identical on the server and
  // the client, because this page is prerendered -- so it is the machine's
  // proposal (or the plain default), and the browser's saved copy is applied
  // after mount. Reading localStorage during render would hydrate a different
  // count strip than the HTML shipped.
  const [structure, setStructure] = useState<LessonStructure>(() => seed(doc, endS));
  useEffect(() => {
    const saved = restore(lessonId, endS);
    if (saved) setStructure(saved);
  }, [lessonId, endS]);
  const [mode, setMode] = useState<PlaybackMode>("all");
  const [loop, setLoop] = useState<LoopSpan>(() => ({ startCount: 1, endCount: Math.min(8, structure.grid.countTotal) }));

  const changeStructure = useCallback(
    (next: LessonStructure) => {
      setStructure(next);
      saveStructure(lessonId, next);
    },
    [lessonId],
  );
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

  /**
   * Looping, in counts.
   *
   * THE VIDEO REMAINS THE ONLY CLOCK. The navigation package ships an
   * `advance(timeS, dtS, ...)` helper for a host that owns its own clock; this
   * host deliberately does not use it. Running it would mean a second clock
   * ticking beside `requestVideoFrameCallback`, and the two would drift on
   * every playbackRate change and seek -- the exact failure `useVideoClock`
   * exists to avoid. So the package converts counts to seconds
   * (`loopTimesS`), and the video element still does the looping.
   *
   * `timeupdate` fires ~4x/s, so the wrap can overshoot the loop end by a few
   * frames. That is the same behaviour this viewer already had, and a tighter
   * wrap would mean polling in rAF -- i.e. a second clock again.
   */
  useEffect(() => {
    if (!video || mode !== "loop") return;
    const [a, b] = loopTimesS(structure.grid, loop);
    const end = Math.min(b, endS);
    const onTime = () => {
      if (video.currentTime >= end) video.currentTime = a;
    };
    video.addEventListener("timeupdate", onTime);
    return () => video.removeEventListener("timeupdate", onTime);
  }, [video, mode, structure.grid, loop, endS]);

  const setPlayingFromNav = useCallback(
    (want: boolean) => {
      if (!video) return;
      if (want) void video.play();
      else video.pause();
    },
    [video],
  );

  // DESIGN.md §8 keyboard map. space / ←→ / L now belong to <LessonNavigator>,
  // which steps by COUNT rather than by a made-up quarter-second and knows what
  // "loop" means. Registering them here too would double-handle every press
  // (space would toggle twice and appear dead), so only the two keys the
  // navigator does not own are handled here.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable)) return;
      const k = e.key.toLowerCase();
      if (k === "m") setMirrored((v) => !v);
      else if (k === "s") setSpeed((s) => SPEEDS[(SPEEDS.indexOf(s as 1) + 1) % SPEEDS.length]);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const grounded = doc.grounding.status === "grounded";
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

      {/*
        Both navigation tiers (DESIGN.md §7), from W6's package. It is fully
        controlled and renderer-free: it reads `timeS` from the video clock and
        calls `onSeek`, which sets `video.currentTime`; the next
        requestVideoFrameCallback republishes that into `timeRef`, and
        Stage3D's useFrame calls `mixer.setTime(timeRef.current)`. So one
        scrub moves the video and the mesh through a single clock, and this
        component owns no clock of its own.

        The dancer chips the viewer used to draw itself now come from the
        package (same four DESIGN.md §3 colours, same one-tap switch) -- two
        rows of dancer chips would be two controls for one piece of state.
      */}
      <LessonNavigator
        result={doc}
        structure={structure}
        onStructureChange={changeStructure}
        timeS={displayTime}
        onSeek={seek}
        playing={playing}
        onPlayingChange={setPlayingFromNav}
        mode={mode}
        onModeChange={setMode}
        loop={loop}
        onLoopChange={setLoop}
        selectedPersonId={doc.persons[selected].person_id}
        onSelectPerson={(id) => setSelected(Math.max(0, doc.persons.findIndex((p) => p.person_id === id)))}
      >
        {/* Viewer-owned controls, passed through into the transport row so
            there is one row of controls rather than two competing ones. */}
        <button
          className="sw-btn"
          onClick={() => setSpeed(SPEEDS[(SPEEDS.indexOf(speed as 1) + 1) % SPEEDS.length])}
        >
          {speed}× speed
        </button>
        <button className={`sw-btn ${mirrored ? "sw-on" : ""}`} onClick={() => setMirrored((v) => !v)}>
          {mirrored ? "Mirror on" : "Mirror off"}
        </button>
        <button
          className={`sw-btn ${compareView ? "sw-on" : ""}`}
          onClick={() => setCompareView(compareView ? null : view === "side" ? "front" : "side")}
        >
          {compareView ? "Compare on" : "Compare off"}
        </button>
      </LessonNavigator>

      {/*
        DESIGN.md §7h, at the one place it bites hardest. A proposed count 1
        rendered as a fact is precisely the failure this project guards
        against, so the label says which it is -- and says it in the label
        rather than in a tooltip or a separate readout (§8, state in the
        label). It stops saying "proposed" the moment the learner moves the
        grid, because from then on it genuinely is theirs.
      */}
      {doc.beat_proposal && (
        <p className="note">
          {!isStillProposed(doc, structure) ? (
            "Counts set by you."
          ) : (
            <>
              {/* The raw score, not a "high/low" word: the score is not
                  calibrated against ground truth, so banding it into a
                  confident-sounding adjective would mislead someone who
                  understood how it was computed. And it scores the TEMPO —
                  count 1 is the weaker half of the guess, so the note says
                  so rather than letting one number cover both. */}
              Counts proposed from the music — {Math.round(doc.beat_proposal.bpm)} BPM, tempo confidence{" "}
              {doc.beat_proposal.confidence}. Count 1 is the first beat found, not a detected downbeat — set your own
              in “Counts and parts”.
              {doc.beat_proposal.warnings.map((w) => (
                <span key={w}> {w}.</span>
              ))}
            </>
          )}
        </p>
      )}

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
