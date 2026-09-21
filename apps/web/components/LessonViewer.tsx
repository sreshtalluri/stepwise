"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Stage3D, { type Focus } from "./Stage3D";
import {
  defaultPersonIndex,
  dancerColor,
  viewLabel,
  projectBoxToFrame,
  cropTransform,
  followStep,
  damp,
  travelExtent,
  travelsMeaningfully,
  FOLLOW,
  VIEW_PRESETS,
  SPEEDS,
  type MotionResult,
  type Rect,
  type Vec3,
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

/**
 * Crop-follow for the video pane, so the two stages do not disagree.
 *
 * A following 3D view next to a static wide shot reads as out of sync — the whole
 * point of the pair is that they are the same moment. So the video pane crops to the
 * same dancer, and it does it from the SAME number: `focusRef.body` is the world box
 * the 3D camera is framing, projected through the clip's own pinhole camera. There is
 * no second tracker to drift.
 *
 * WHY NOT `crop_rects`. The frozen v1 contract carries `crop_rects.hands` and
 * `crop_rects.feet` and nothing for the body. Unioning the two is not a body box (it
 * misses a raised head entirely) and it is null-heavy — on the `failure-lesson`
 * fixture `feet` is non-null in 8 of 90 samples. Projecting the posed bounds needs no
 * contract change, and is exactly as wrong as the 3D pane whenever the solve is bad.
 * A `crop_rects.body` would be the better source; it is a contract gap, reported.
 *
 * Runs on its own rAF loop, writes `style.transform` directly, and only touches React
 * state when a boolean flips. Nothing here re-renders at frame rate.
 */
function useVideoCrop(
  video: HTMLVideoElement | null,
  doc: MotionResult,
  focusRef: React.RefObject<Focus | null>,
  follow: boolean,
  mirrored: boolean,
) {
  const [status, setStatus] = useState({ cropped: false, clipped: false });

  useEffect(() => {
    if (!video) return;
    const mirror = mirrored ? "scaleX(-1) " : "";
    if (!follow) {
      video.style.transform = mirrored ? "scaleX(-1)" : "";
      setStatus({ cropped: false, clipped: false });
      return;
    }

    let handle = 0;
    let last = performance.now();
    // Damped in FRAME space with the same tuning the 3D rig uses, rather than being
    // driven off the 3D camera's own aim point: the two panes then lag identically
    // and read as one motion, while each still frames for its own aspect ratio.
    let centre: Vec3 | null = null;
    let height = 0;
    let reported = { cropped: false, clipped: false };

    const tick = (now: number) => {
      handle = requestAnimationFrame(tick);
      const dt = Math.min((now - last) / 1000, 0.1);
      last = now;
      const focus = focusRef.current;
      if (!focus) return;

      const raw: Rect | null = projectBoxToFrame(
        doc,
        [focus.body.min.x, focus.body.min.y, focus.body.min.z],
        [focus.body.max.x, focus.body.max.y, focus.body.max.z],
      );
      // Behind the camera plane, or no bounds yet: hold the last good crop rather
      // than snap to centre. A jump is a worse lie than a stale frame.
      if (!raw || raw.height <= 0) return;

      const target: Vec3 = [raw.x + raw.width / 2, raw.y + raw.height / 2, 0];
      if (!centre) {
        centre = target;
        height = raw.height;
      } else {
        // Deadzone as a fraction of the dancer's own projected height, which is the
        // same dimensionless rule the 3D rig applies in metres.
        centre = followStep(centre, target, FOLLOW.deadzoneFraction * raw.height, dt);
        height = damp(height, raw.height, FOLLOW.tauDistance, dt);
      }

      const win = cropTransform({ x: centre[0] - raw.width / 2, y: centre[1] - height / 2, width: raw.width, height });
      // translate() percentages resolve against the ELEMENT box, but the crop is in
      // frame coordinates and `object-fit: contain` letterboxes the frame inside that
      // box. Convert once, here, instead of restyling the element.
      const elW = video.clientWidth;
      const elH = video.clientHeight;
      const aspect = doc.source_video.width_px / doc.source_video.height_px;
      const imgW = Math.min(elW, elH * aspect);
      const imgH = imgW / aspect;
      const tx = elW > 0 ? (win.tx * imgW) / elW : 0;
      const ty = elH > 0 ? (win.ty * imgH) / elH : 0;
      video.style.transform = `${mirror}translate(${(tx * 100).toFixed(3)}%, ${(ty * 100).toFixed(3)}%) scale(${win.zoom.toFixed(4)})`;

      // `clipped` is judged on the RAW projection, not the damped one: the question
      // is whether the dancer is actually outside what the phone shot.
      const next = {
        cropped: win.zoom > 1.05,
        clipped: raw.x < 0 || raw.y < 0 || raw.x + raw.width > 1 || raw.y + raw.height > 1,
      };
      if (next.cropped !== reported.cropped || next.clipped !== reported.clipped) {
        reported = next;
        setStatus(next);
      }
    };
    handle = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(handle);
      video.style.transform = mirrored ? "scaleX(-1)" : "";
    };
  }, [video, doc, focusRef, follow, mirrored]);

  return status;
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
  /**
   * Follow is ON by default. Three reasons, in order:
   *
   * 1. Under the deadzone it is a NO-OP for a dancer working in place, which is every
   *    clip today (`root_trajectory` is pinned — OPEN-DECISIONS E6). So it does not
   *    move anything on its own and does not contradict DESIGN.md §9's
   *    MOTION_INTENSITY 3. The moment world placement lands it starts earning itself.
   * 2. The failure it prevents is silent. A dancer who drifts away and shrinks to
   *    forty pixels looks like a badly shot video, not like a setting the learner
   *    could have changed — they will not go looking for a control they do not know
   *    exists.
   * 3. It is one tap off, and the button says which state it is in (§8).
   */
  const [follow, setFollow] = useState(true);
  /** Written every frame by the main 3D stage; read by the video pane's crop. */
  const focusRef = useRef<Focus | null>(null);

  // ...except under `prefers-reduced-motion`. A camera that pans through a 3D scene
  // is exactly the motion that setting exists for — unlike the contact shadow, which
  // DESIGN.md §9 keeps moving because it is information the learner cannot get
  // otherwise. Follow is turned OFF rather than removed: the control is still there,
  // still says what it does, and the learner can opt in.
  // Set in an effect, not in the initial state, so the server and the first client
  // render agree and the button label does not hydrate-mismatch.
  useEffect(() => {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) setFollow(false);
  }, []);

  const duration = doc.source_video.duration_s;
  const crop = useVideoCrop(video, doc, focusRef, follow, mirrored);
  const travels = travelsMeaningfully(doc, selected);

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
      // `F` is an addition to the §8 map, which predates this control.
      else if (k === "f") setFollow((v) => !v);
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
            follow={follow}
            focusRef={focusRef}
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
                follow={follow}
                glbUrls={glbUrls}
              />
            </div>
          )}
        </section>

        <section className={stageClass("video")}>
          {/* A cropped camera view is still camera evidence, but it is no longer the
              framing the phone shot — so it says so. Never a silent crop (§7h). */}
          <span className="view-label">{crop.cropped ? "camera view · cropped" : "camera view"}</span>
          <button className="swap" onClick={() => setPromoted(promoted === "video" ? "none" : "video")}>
            {promoted === "video" ? "Show both" : "Show larger"}
          </button>
          <video
            ref={setVideo}
            className="video"
            src={videoUrl}
            playsInline
            preload="auto"
            /* transform is owned by useVideoCrop, mirroring included, so the two
               never fight over the same property. */
            onPlay={() => setPlaying(true)}
            onPause={() => setPlaying(false)}
          />
        </section>
      </div>

      <p className="legend">solid = seen · sketchy = unsure · dotted = out of frame</p>
      {!grounded && <p className="note">No floor — feet not visible in this clip.</p>}
      {absent.length > 0 && <p className="note">{absent.join(" · ")}.</p>}
      {/* The crop stops at the edge of the shot rather than panning past it, so the
          dancer slides off centre instead. Say that, rather than let it look like a
          bug or — worse — let the crop imply the dancer filled a frame they did not. */}
      {follow && crop.clipped && <p className="note">Dancer at the edge of the shot — the crop stops there.</p>}

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
        {/* Framing, not angle — a separate axis from the views rail, and it stays on
            while you orbit. The `small` carries the travel fact: with no floor to
            slide underneath the dancer (§10 forbids drawing one when grounding is
            "none", which is every real clip today) this readout is what stops three
            metres of travel looking identical to standing still. Shown only when the
            document actually carries travel — printing "0.0 m" for a pinned
            trajectory would claim a stillness nobody measured (OPEN-DECISIONS E6). */}
        <button className={`btn ${follow ? "active" : ""}`} onClick={() => setFollow((v) => !v)}>
          {follow ? "Follow on" : "Follow off"}
          <small>{travels ? `travels ${travelExtent(doc, selected).toFixed(1)} m` : "F"}</small>
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
