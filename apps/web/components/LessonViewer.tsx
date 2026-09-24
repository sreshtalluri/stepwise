"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Stage3D, { type Focus } from "./Stage3D";
import {
  defaultPersonIndex,
  viewLabel,
  projectBoxToFrame,
  cropTransform,
  cropRegions,
  steadyCropTrack,
  steadyCropAt,
  STEADY_CROP_SIGMA_S,
  STEADY_CROP_SIGMA_REDUCED_S,
  followStep,
  damp,
  travelExtent,
  travelsMeaningfully,
  FOLLOW,
  VIEW_PRESETS,
  SPEEDS,
  type CropRegion,
  type MotionResult,
  type Rect,
  type Vec3,
  type ViewId,
} from "../lib/motion";
import { lesson as lessonCopy } from "../lib/copy";
import { load, openingStructure, save } from "../lib/structure";
import { prefersReducedMotion } from "../lib/reveal";
// Relative, same as lib/motion.ts reaches into motion-contract — there is no
// workspace root and no node_modules link between these packages.
import { LessonNavigator } from "../../../packages/navigation/src/LessonNavigator";
import {
  currentCount,
  loopSpanForPart,
  loopTimesS,
  partRangeAtCount,
  timelineEndS,
} from "../../../packages/navigation/src/core";
import type { LessonStructure, LoopSpan, PlaybackMode } from "../../../packages/navigation/src/core";
import "../../../packages/navigation/src/navigation.css";

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
function useVideoClock(
  video: HTMLVideoElement | null,
  /**
   * `[start, end)` in timeline seconds, or null. The count-based loop is applied
   * HERE, inside the one clock this page has, rather than on a `timeupdate`
   * listener (which fires ~4x a second, so a loop could overshoot by a quarter
   * of a second — audible on an 8-count) and rather than by running W6's
   * `advance()` (which is for a host that owns a synthetic clock; this one does
   * not, and a second clock is the bug this comment exists to prevent).
   */
  loopRef: React.RefObject<[number, number] | null>,
) {
  const timeRef = useRef(0);
  const [displayTime, setDisplayTime] = useState(0);

  useEffect(() => {
    if (!video) return;
    let cancelled = false;
    let rvfcHandle = 0;
    let rafHandle = 0;
    let lastPublished = -1;

    const publish = (t: number) => {
      const loop = loopRef.current;
      // Only the trailing edge. An earlier version also snapped a playhead that
      // was BEFORE the loop, which sounds symmetric and is wrong: it silently
      // undid any deliberate seek outside the loop, so dragging the overview bar
      // in loop mode looked broken. Running into the loop from before it is
      // harmless — it loops once it arrives.
      if (loop && t >= loop[1]) {
        // Wrap on the same value the compositor just showed. `currentTime` is
        // set, not stepped, so no arithmetic accumulates and the loop cannot
        // drift over forty minutes of repeats.
        video.currentTime = loop[0];
        t = loop[0];
      }
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
  }, [video, loopRef]);

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

/**
 * One region's close-up: real pixels from the SAME `<video>` element this page
 * already has, cropped to a steadied `crop_rects[region]` (`steadyCropTrack`:
 * fixed zoom, zero-phase smoothed pan) and drawn onto a canvas — no
 * second `<video>`, no second decode, no second clock. Reads `timeRef` on its
 * own rAF loop exactly like `useVideoCrop` above, and only touches React state
 * when a sample flips between having a rect and not having one.
 *
 * WHY A CANVAS. The main video pane already owns `style.transform` for its own
 * body-follow crop; a second, differently-cropped view of the same element
 * needs its own pixels, not a second style on the one `<video>` DOM node. This
 * is the "crop-transform... or draw canvas from it" the brief asks for, and it
 * costs nothing extra to decode — `drawImage` samples whatever the browser has
 * already decoded for display.
 *
 * DESIGN.md §7h — the crux. A `null` sample means the pipeline did not
 * confidently localize this region, and `crop_rects.hands`/`.feet` say so
 * per-sample by contract (`hand_crops.py`'s emission rules). Holding the last
 * drawn crop on a `null` sample would show a stale frame as if it were the
 * current one — the exact confident-wrong-output failure this project exists
 * to guard against — so the canvas is cleared and a plain label takes over.
 */
function CropPeek({
  video,
  doc,
  timeRef,
  personIndex,
  region,
  mirrored,
}: {
  video: HTMLVideoElement | null;
  doc: MotionResult;
  timeRef: React.RefObject<number>;
  personIndex: number;
  region: CropRegion;
  mirrored: boolean;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [live, setLive] = useState(false);

  useEffect(() => {
    if (!video) return;
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d") ?? null;
    if (!canvas || !ctx) return;
    let handle = 0;
    let reported = false;
    // Steadied once per dancer/region, not per frame — see `steadyCropTrack`.
    const sigma = prefersReducedMotion() ? STEADY_CROP_SIGMA_REDUCED_S : STEADY_CROP_SIGMA_S;
    const track = steadyCropTrack(doc, personIndex, region, sigma);

    const tick = () => {
      handle = requestAnimationFrame(tick);
      const rect = steadyCropAt(doc.sample_times_s, track, timeRef.current);
      if (!rect) {
        if (reported) {
          reported = false;
          setLive(false);
        }
        ctx.clearRect(0, 0, canvas.width, canvas.height); // never hold a stale crop — §7h
        return;
      }
      // `videoWidth`/`videoHeight` fall back to the contract's own dimensions
      // before the element has a frame decoded yet; ingest already bakes
      // rotation into both, so the two agree once the video is ready.
      const vw = video.videoWidth || doc.source_video.width_px;
      const vh = video.videoHeight || doc.source_video.height_px;
      if (!vw || !vh) return;
      if (!reported) {
        reported = true;
        setLive(true);
      }
      const sx = rect.x * vw;
      const sy = rect.y * vh;
      const sw = rect.width * vw;
      const sh = rect.height * vh;
      // Contain-fit inside the fixed canvas so the crop never stretches. The
      // steadied rect is square in source pixels, so this fills the canvas.
      const scale = Math.min(canvas.width / sw, canvas.height / sh);
      const dw = sw * scale;
      const dh = sh * scale;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(video, sx, sy, sw, sh, (canvas.width - dw) / 2, (canvas.height - dh) / 2, dw, dh);
    };
    handle = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(handle);
  }, [video, doc, timeRef, personIndex, region]);

  return (
    <div className="crop-peek">
      <span className="crop-peek-label">{lessonCopy.crop[region]}</span>
      <canvas
        ref={canvasRef}
        width={128}
        height={128}
        style={mirrored ? { transform: "scaleX(-1)" } : undefined}
      />
      {!live && <span className="crop-peek-msg">{lessonCopy.crop.unavailable}</span>}
    </div>
  );
}

export interface LessonViewerProps {
  doc: MotionResult;
  title: string;
  videoUrl: string;
  /** One GLB URL per entry in `doc.persons`. */
  glbUrls: string[];
  /** Scope for the learner's authored counts and parts. See lib/structure.ts. */
  lessonId: string;
}

export default function LessonViewer({ doc, title, videoUrl, glbUrls, lessonId }: LessonViewerProps) {
  const [video, setVideo] = useState<HTMLVideoElement | null>(null);
  // The end of the clip is the last SAMPLE SLOT, never source_video.duration_s
  // — the contract says so and W6's whole grid is sized off it.
  const endS = useMemo(() => timelineEndS(doc.sample_times_s), [doc]);

  // ---- authored structure ------------------------------------------------
  // Opens on the machine proposal when there is one, and is overwritten by the
  // learner's own the moment there is one of those. Manual always wins.
  const opening = useMemo(() => openingStructure(doc, endS), [doc, endS]);
  const [structure, setStructure] = useState<LessonStructure>(opening.structure);
  const [authored, setAuthored] = useState(false);
  // Hydration: the server has no localStorage, so the first client render must
  // match the server's (the proposal) and the saved copy lands one tick later.
  // `restored` also guards the save effect below — without it the proposal
  // would be written over a real authored structure before it was ever read.
  const [restored, setRestored] = useState(false);
  useEffect(() => {
    const saved = load(lessonId, endS);
    if (saved) {
      setStructure(saved.structure);
      setAuthored(saved.authored);
    }
    setRestored(true);
  }, [lessonId, endS]);
  useEffect(() => {
    if (restored) save(lessonId, { structure, authored });
  }, [restored, lessonId, structure, authored]);

  const editStructure = useCallback((next: LessonStructure) => {
    setStructure(next);
    setAuthored(true);
  }, []);

  /**
   * Whether the counts on screen are still a guess, and how loudly to say so.
   *
   * DESIGN.md §7h, aimed at the counts instead of at the 3D: a proposed count 1
   * presented as a fact is exactly the failure this project guards against, and
   * the count grid is worse than the mesh for it because a learner who trusts
   * the wrong count 1 practises the whole dance off the beat. The note is
   * always visible, not inside the `Counts and parts` disclosure, because the
   * disclosure is closed by default — a learner who never opens it would never
   * be told.
   *
   * It disappears the moment the learner edits anything. Once the grid is
   * theirs, still calling it a guess is the same lie the other way round.
   */
  const counts = useMemo(() => {
    if (authored) return { from: "hand" as const, note: null };
    const perMinute = Math.round(60 / structure.grid.secondsPerCount);
    const proposed = doc.proposed_counts;
    if (!proposed) return { from: "hand" as const, note: lessonCopy.counts.placeholder(perMinute) };
    // 0.5 sits just above the 0.4 the beat module caps itself at whenever the
    // tempo lands outside the plausible dance band — so every implausible-tempo
    // proposal reads as weak, which is the case that is usually a half/double
    // lock rather than a genuinely fast dance.
    const note = proposed.confidence < 0.5
      ? lessonCopy.counts.weak(perMinute)
      : lessonCopy.counts.proposed(perMinute);
    return { from: "music" as const, note };
  }, [authored, doc, structure.grid.secondsPerCount]);

  const [mode, setMode] = useState<PlaybackMode>("all");
  const [loopSpan, setLoopSpan] = useState<LoopSpan>({ startCount: 1, endCount: 8 });
  /**
   * The loop the clock enforces, as a ref so changing it never restarts the
   * rVFC loop. `null` in "play all" — the mode IS the switch, so there is no
   * second piece of state that could disagree with the button's label (§8).
   */
  const loopTimes = useRef<[number, number] | null>(null);
  loopTimes.current = mode === "loop" ? loopTimesS(structure.grid, loopSpan) : null;

  const [selected, setSelected] = useState(() => defaultPersonIndex(doc));
  const [view, setView] = useState<ViewId>("camera");
  const [compareView, setCompareView] = useState<ViewId | null>(null);
  const [mirrored, setMirrored] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [playing, setPlaying] = useState(false);
  const [absent, setAbsent] = useState<string[]>([]);
  // D2: the two stages start equal and either can be promoted. Remembered per person
  // in v2 — this session-only version is the honest placeholder.
  const [promoted, setPromoted] = useState<"none" | "3d" | "video">("none");
  /**
   * Follow is ON by default. Three reasons, in order:
   *
   * 1. Under the deadzone it is a NO-OP for a dancer working in place, so it does not
   *    move anything on its own and does not contradict DESIGN.md §9's
   *    MOTION_INTENSITY 3. This used to say "which is every clip today, because
   *    `root_trajectory` is pinned"; world placement landed on `grounding-wiring`, so
   *    the served document now carries real travel and this is earning itself. NOTE
   *    the seam that is still open: the 3D stage animates the GLB, and the GLB still
   *    carries the character-local root, so the *rendered* dancer does not travel yet
   *    even though the document says they do (OPEN-DECISIONS E6, item 5).
   * 2. The failure it prevents is silent. A dancer who drifts away and shrinks to
   *    forty pixels looks like a badly shot video, not like a setting the learner
   *    could have changed — they will not go looking for a control they do not know
   *    exists.
   * 3. It is one tap off, and the button says which state it is in (§8).
   */
  const [follow, setFollow] = useState(true);
  /** Written every frame by the main 3D stage; read by the video pane's crop. */
  const focusRef = useRef<Focus | null>(null);
  /**
   * Hand/feet close-up, on by default. Builder-dance feedback names specific
   * hand shapes as one of the things the product has to get right, and
   * `crop_rects` is the one honest way to show them at this source resolution
   * (see `hand_crops.py`'s header) — so it defaults to visible rather than a
   * discovery a learner might never make. It stays a real toggle (§8) because
   * it is one more box on a phone screen and someone may just want the video.
   */
  const [showCrops, setShowCrops] = useState(true);

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
  const { timeRef, displayTime } = useVideoClock(video, loopTimes);
  // The overlay is drawn in the frame's own coordinates, so the video under it must
  // not be cropped (ponytail: crop-follow is simply off in overlay; apply the same
  // transform to the overlay canvas if both are ever wanted at once).
  const overlay = view === "overlay";
  const crop = useVideoCrop(video, doc, focusRef, follow && !overlay, mirrored);
  const peekRegions = cropRegions(doc, selected, mirrored);
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

  /**
   * The navigator is fully controlled and does not own the clock, so "play" has
   * to mean the same thing whichever side asked for it: drive the video element
   * and let `onPlay`/`onPause` report back. Nothing here mirrors playback state
   * into a second variable that could disagree with the picture.
   */
  const setPlayingFromNav = useCallback(
    (next: boolean) => {
      if (!video) return;
      if (next) void video.play();
      else video.pause();
    },
    [video],
  );

  const chooseMode = useCallback((next: PlaybackMode) => setMode(next), []);

  /**
   * While "play all" is the mode, the loop button is an OFFER, not a state — so
   * it has to name the part it would actually loop, which is the one under the
   * playhead. Without this it kept whatever span was last set and read
   * "Loop part 1" while sitting in part 2, then looped part 2 when pressed.
   * That is DESIGN.md §8's state-in-label rule failing in the one place it is
   * easiest to miss: the label was true of the state and false of the action.
   *
   * Caught in the browser, not in review. Only runs in "all" — in "loop" the
   * span is the learner's, including handles they have dragged off a boundary.
   */
  useEffect(() => {
    if (mode !== "all") return;
    const span = loopSpanForPart(partRangeAtCount(structure, currentCount(structure.grid, displayTime)));
    setLoopSpan((prev) =>
      prev.startCount === span.startCount && prev.endCount === span.endCount ? prev : span,
    );
  }, [mode, structure, displayTime]);

  /**
   * DESIGN.md §8 keyboard map, minus the four keys the navigator owns.
   *
   * `space`, `L` and `←/→` moved to `<LessonNavigator>` — it is the thing that
   * knows what a count is, and an arrow key that steps a quarter-second was
   * always a stand-in for stepping a count (the old comment here said so). Two
   * listeners on `window` for the same key would both fire, so this is a
   * deletion, not a duplication. `M`, `S` and `F` stay: mirror, speed and
   * follow are the viewer's, not the navigation surface's.
   */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable)) return;
      const k = e.key.toLowerCase();
      if (k === "m") setMirrored((v) => !v);
      else if (k === "s") setSpeed((s) => SPEEDS[(SPEEDS.indexOf(s as 1) + 1) % SPEEDS.length]);
      // `F` is an addition to the §8 map, which predates this control.
      else if (k === "f") setFollow((v) => !v);
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
          <span className="view-label">{viewLabel(overlay ? "camera" : view, mirrored)}</span>
          <button className="swap" onClick={() => setPromoted(promoted === "3d" ? "none" : "3d")}>
            {promoted === "3d" ? "Show both" : "Show larger"}
          </button>
          <Stage3D
            doc={doc}
            selectedIndex={selected}
            view={overlay ? "camera" : view}
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
          <span className="view-label">
            {overlay ? viewLabel("overlay", mirrored) : crop.cropped ? "camera view · cropped" : "camera view"}
          </span>
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
          {/* SPIKE: the body over the video, from the source camera. Semi-transparent
              as a whole layer so the dancer shows through — not an uncertainty
              encoding (§12.4 still holds: the region materials carry that). Mirrored
              by CSS with the video, never on the mesh, so the two flip together. */}
          {overlay && (
            <div
              style={{
                position: "absolute",
                inset: 0,
                opacity: 0.55,
                pointerEvents: "none",
                transform: mirrored ? "scaleX(-1)" : undefined,
              }}
            >
              <Stage3D
                doc={doc}
                selectedIndex={selected}
                view="overlay"
                mirrored={false}
                timeRef={timeRef}
                glbUrls={glbUrls}
                overlay
              />
            </div>
          )}
          {/* Hidden when the video pane itself is demoted to a 96px strip (D2) —
              there is no room to make a close-up legible, and the strip is
              already the close-up-of-everything at that point. Placed in the
              video stage only, so it can never crowd the 3D stage or (being
              absolutely positioned inside a fixed-height box) the count strip
              below the stages. */}
          {showCrops && promoted !== "3d" && !overlay && (
            <div className={`crop-peek-group${peekRegions.length > 2 ? " sides" : ""}`}>
              {peekRegions.map((region) => (
                <CropPeek key={region} video={video} doc={doc} timeRef={timeRef} personIndex={selected} region={region} mirrored={mirrored} />
              ))}
            </div>
          )}
        </section>
      </div>

      <p className="legend">solid = seen · sketchy = unsure · dotted = out of frame</p>
      {!grounded && <p className="note">No floor — feet not visible in this clip.</p>}
      {absent.length > 0 && <p className="note">{absent.join(" · ")}.</p>}
      {/* The crop stops at the edge of the shot rather than panning past it, so the
          dancer slides off centre instead. Say that, rather than let it look like a
          bug or — worse — let the crop imply the dancer filled a frame they did not. */}
      {follow && crop.clipped && <p className="note">Dancer at the edge of the shot — the crop stops there.</p>}

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
              {preset.id !== "camera" && preset.id !== "overlay" && <small>est.</small>}
            </button>
          ))}
        </div>
      </div>

      {/*
        The two navigation tiers, the dancer chips, the transport modes and the
        count/part editor are all W6's `<LessonNavigator>` (DESIGN.md §7, §8).
        It replaces the placeholder overview bar, the dancer chip row and the
        A–B loop that lived here — the placeholders' own comments said this was
        coming ("snapping loop edges to count boundaries belongs to the count
        strip, which is W6's package").

        It is fully controlled and renderer-free: it takes the time and emits a
        seek, and this component keeps the only clock on the page. The viewer's
        own controls — speed, mirror, follow, compare — are handed down through
        `children` and render inside its transport row, which is the seam W6
        left for exactly this.
      */}
      {counts.note && <p className="note">{counts.note}</p>}
      <LessonNavigator
        result={doc}
        structure={structure}
        onStructureChange={editStructure}
        countsFrom={counts.from}
        timeS={displayTime}
        onSeek={seek}
        playing={playing}
        onPlayingChange={setPlayingFromNav}
        mode={mode}
        onModeChange={chooseMode}
        loop={loopSpan}
        onLoopChange={setLoopSpan}
        selectedPersonId={doc.persons[selected]?.person_id ?? doc.persons[0].person_id}
        onSelectPerson={(id) => {
          const i = doc.persons.findIndex((p) => p.person_id === id);
          if (i >= 0) setSelected(i);
        }}
      >
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
            while you orbit. The `small` carries the travel fact: when there is no
            floor to slide underneath the dancer (§10 forbids drawing one when
            grounding is "none") this readout is what stops three metres of travel
            looking identical to standing still. Shown only when the document
            actually carries travel — printing "0.0 m" for a track that fell back to
            the pinned constant would claim a stillness nobody measured.
            Two clauses here went stale on `grounding-wiring` and are corrected: a
            real clip is no longer always `none` (solo-01 now solves `grounded`), and
            `root_trajectory` is no longer always pinned. OPEN-DECISIONS E6. */}
        <button className={`btn ${follow ? "active" : ""}`} onClick={() => setFollow((v) => !v)}>
          {follow ? "Follow on" : "Follow off"}
          <small>{travels ? `travels ${travelExtent(doc, selected).toFixed(1)} m` : "F"}</small>
        </button>
        <button
          className={`btn ${compareView ? "active" : ""}`}
          onClick={() => setCompareView(compareView ? null : view === "side" ? "front" : "side")}
        >
          {compareView ? "Compare on" : "Compare off"}
          <small>two angles</small>
        </button>
        <button className={`btn ${showCrops ? "active" : ""}`} onClick={() => setShowCrops((v) => !v)}>
          {showCrops ? lessonCopy.crop.toggleOn : lessonCopy.crop.toggleOff}
          <small>{lessonCopy.crop.toggleHint}</small>
        </button>
      </LessonNavigator>

      {compareView && (
        <div className="chips views second" role="group" aria-label="Second angle">
          {VIEW_PRESETS.filter((p) => p.id !== "overlay").map((preset) => (
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
