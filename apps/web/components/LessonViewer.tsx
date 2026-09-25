"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Focus } from "./Stage3D";
import { defaultPersonIndex, sourceAspect, type MotionResult } from "../lib/motion";
import { load, openingStructure, save } from "../lib/structure";
import { parseHandoff } from "../lib/flow";
import type { Credit } from "../lib/lessons";
import {
  buildUpSpeed,
  clampSpeed,
  DEFAULT_LOOP_LENGTH,
  eightOf,
  eightsOf,
  loadDone,
  loadLoopLength,
  loadShowAnds,
  saveShowAnds,
  markDone,
  nextLoop,
  sameSpan,
  saveDone,
  saveLoopLength,
  spanDone,
  stepLoop as stepLoopBy,
  loopLength,
  nextPreset,
  presetCounts,
  SPEED_GRID,
  stepSpeed,
  ONE_SURE,
  type Eight,
} from "../lib/lessonEngine";
import { loadClickVolume, loadMusicVolume, saveClickVolume, saveMusicVolume, type ClickMode } from "../lib/metronome";
import {
  currentCount,
  eightStartCount,
  timeOfCount,
  loopTimesS,
  nudgeCountOne,
  setCountOne,
  tapOnOne,
  timelineEndS,
} from "../../../packages/navigation/src/core";
import type { LessonStructure, LoopSpan } from "../../../packages/navigation/src/core";
import { PHONE_QUERY, unlockAudio, useMedia, useMetronome, useVideoClock, useVideoCrop } from "./lesson/hooks";
import DesktopLesson from "./lesson/DesktopLesson";
import PhoneLesson from "./lesson/PhoneLesson";
import { addPlay, referrerHost, track } from "../lib/analytics";
import "./lesson/lesson.css";

/** Where a loop came from, for `loop_created` (lib/analytics.ts). */
export type LoopVia = "drag" | "count" | "marker" | "preset" | "step" | "handoff" | "other";

/** Calls `fn(value)` when `value` changes after mount; never for the first value. */
function useOnChange<T>(value: T, fn: (v: T) => void) {
  // Compared with the last value rather than "skip the first run": React's
  // strict mode runs a mount effect twice, and that must not look like a change.
  const prev = useRef(value);
  useEffect(() => {
    if (Object.is(prev.current, value)) return;
    prev.current = value;
    fn(value);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fires on value only
  }, [value]);
}

/**
 * The lesson page's one state, shared by two compositions (DESIGN.md §6: phone and
 * desktop are different layouts, not one stretched). Same URL for both; the phone one
 * is switched in on narrow or sideways screens, and both read and write only this.
 *
 * One mode, nothing forced: the whole dance plays with its counts until the learner
 * drags a loop across the timeline (or taps a shortcut), a speed, optionally Build up
 * and a click on the counts, and follow. There is exactly one clock — the `<video>` — and one
 * loop, applied inside it (`useVideoClock`); build-up and the full-speed ticks count
 * that clock's loop passes.
 */
export interface LessonViewerProps {
  doc: MotionResult;
  title: string;
  videoUrl: string;
  /** Who made the original video, for a link lesson; null for an upload. */
  credit?: Credit | null;
  /** One GLB URL per entry in `doc.persons`. */
  glbUrls: string[];
  /** Scope for the learner's counts, parts, full-speed ticks and dancer. */
  lessonId: string;
  /** "⋯" menu entries. Wired by the host once those flows exist; absent = shown disabled. */
  onRemoveFromMyLessons?: () => void;
  onReportOrRemove?: () => void;
}

/**
 * The views the top bar toggles, in tiling order. "overlay" (the mesh on the video)
 * and "video" are the one camera panel, with or without the mesh, so they exclude
 * each other; the rest are 3D angles and the close-ups.
 */
export const PANELS = ["overlay", "video", "front", "side", "back", "top", "hands", "feet"] as const;
export type PanelId = (typeof PANELS)[number];
const isCamera = (p: PanelId) => p === "overlay" || p === "video";
/** A phone shows a main panel and one inset; a desktop tiles up to four. */
const MAX_PANELS = { phone: 2, desk: 4 };

/**
 * Toggle a panel in the picks, which are kept in the order they were picked: camera
 * views swap, the oldest pick drops when full, never zero panels. (They are drawn in
 * PANELS order; this order only says which goes first.)
 */
export function togglePanel(picks: readonly PanelId[], id: PanelId, max: number): PanelId[] {
  if (picks.includes(id)) return picks.length > 1 ? picks.filter((p) => p !== id) : [...picks];
  return [...picks.filter((p) => !(isCamera(id) && isCamera(p))), id].slice(-max);
}

const DANCER_KEY = (id: string) => `stepwise.lesson-dancer.v1.${id}`;
const EVERYONE_KEY = (id: string) => `stepwise.lesson-everyone.v1.${id}`;

export default function LessonViewer(props: LessonViewerProps) {
  const phone = useMedia(PHONE_QUERY);
  const l = useLesson(props, phone);
  return phone ? <PhoneLesson l={l} /> : <DesktopLesson l={l} />;
}

export type Lesson = ReturnType<typeof useLesson>;

function useLesson(
  { doc, title, videoUrl, credit = null, glbUrls, lessonId, onRemoveFromMyLessons, onReportOrRemove }: LessonViewerProps,
  phone: boolean,
) {
  const [video, setVideo] = useState<HTMLVideoElement | null>(null);
  const endS = useMemo(() => timelineEndS(doc.sample_times_s), [doc]);
  useEffect(() => track("lesson_opened", { ref: referrerHost(document.referrer, location.hostname) }, lessonId), [lessonId]);

  // ---- counts and parts: the proposal until the learner edits; manual always wins.
  const opening = useMemo(() => openingStructure(doc, endS), [doc, endS]);
  const [structure, setStructure] = useState<LessonStructure>(opening.structure);
  const [authored, setAuthored] = useState(false);
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
    // Persist edits only; see load(). The proposal is re-read from the lesson
    // every time, so a better grid from the pipeline reaches returning learners.
    if (restored && authored) save(lessonId, { structure, authored });
  }, [restored, lessonId, structure, authored]);
  const editStructure = useCallback((next: LessonStructure) => {
    setStructure(next);
    setAuthored(true);
  }, []);
  /** "music" = proposed and untouched, so still a guess; "weak" = a poor guess; "none" = placeholder. */
  const countsFrom: "hand" | "music" | "weak" | "none" = authored
    ? "hand"
    : !doc.proposed_counts
      ? "none"
      : doc.proposed_counts.confidence < 0.5
        ? "weak"
        : "music";
  /** The tracker does not know which beat is 1 (a guess, not just a proposal). Lessons
   * from before `count_one_confidence` existed carry none and read as before. */
  const oneUnsure = !authored && (doc.proposed_counts?.count_one_confidence ?? 1) < ONE_SURE;
  /** A person (the owner, via /owner) checked which beat is 1 on this lesson, so
   * "count 1 is a guess" would no longer be true. */
  const oneChecked = !authored && doc.proposed_counts?.count_one_source === "owner";

  // ---- the loop: any run of counts, or null for the whole dance
  const eights = useMemo(() => eightsOf(structure), [structure]);
  const total = structure.grid.countTotal;
  const [loop, setLoopState] = useState<LoopSpan | null>(null);
  const [loopLen, setLoopLenState] = useState(DEFAULT_LOOP_LENGTH);
  useEffect(() => setLoopLenState(loadLoopLength(lessonId)), [lessonId]);
  const [speedPick, setSpeed] = useState(1);
  const [buildUp, setBuildUpState] = useState(false);
  const [passes, setPasses] = useState(0);
  const [holdSlow, setHoldSlow] = useState(false);
  const speed = holdSlow ? 0.5 : buildUp && loop ? buildUpSpeed(passes) : speedPick;
  const [done, setDone] = useState<Set<number>>(new Set());
  useEffect(() => setDone(loadDone(lessonId)), [lessonId]);

  // ---- dancer
  const multi = doc.persons.length > 1;
  const [selected, setSelected] = useState(() => defaultPersonIndex(doc));
  const [pickerOpen, setPickerOpen] = useState(false);
  useEffect(() => {
    if (!multi) return;
    let stored: string | null = null;
    try {
      stored = window.localStorage.getItem(DANCER_KEY(lessonId));
    } catch {
      /* private mode: ask every time */
    }
    const i = doc.persons.findIndex((p) => p.person_id === stored);
    if (i >= 0) setSelected(i);
    else setPickerOpen(true);
  }, [multi, doc, lessonId]);
  const chooseDancer = useCallback(
    (i: number) => {
      setSelected(i);
      track("dancer_picked", { persons: doc.persons.length, index: i }, lessonId);
      try {
        window.localStorage.setItem(DANCER_KEY(lessonId), doc.persons[i].person_id);
      } catch {
        /* see above */
      }
    },
    [doc, lessonId],
  );
  // The other dancers' meshes, faint. Off by default so the 3D is one body to copy.
  const [showEveryone, setShowEveryoneState] = useState(false);
  useEffect(() => {
    try {
      setShowEveryoneState(multi && window.localStorage.getItem(EVERYONE_KEY(lessonId)) === "1");
    } catch {
      setShowEveryoneState(false);
    }
  }, [multi, lessonId]);
  const setShowEveryone = useCallback(
    (on: boolean) => {
      setShowEveryoneState(on);
      try {
        window.localStorage.setItem(EVERYONE_KEY(lessonId), on ? "1" : "0");
      } catch {
        /* private mode: this visit only */
      }
    },
    [lessonId],
  );

  // ---- the source frame's shape: a 9:16 short and a 16:9 YouTube clip lay out differently.
  const aspect = useMemo(() => sourceAspect(doc), [doc]);
  /** Square or wider: on a phone the video goes full-width on top with the 3D under it. */
  const wide = aspect >= 1;

  // ---- views: the top bar's toggles, tiled. The mesh on the video, plus the front on a
  // desktop — and on a phone too when the clip is wide, since the 3D fills the space under it.
  const maxPanels = phone ? MAX_PANELS.phone : MAX_PANELS.desk;
  const [panelPicks, setPanels] = useState<PanelId[]>(phone && !wide ? ["overlay"] : ["overlay", "front"]);
  // Rotating a desktop-sized pick onto a phone keeps the picks, just draws the first two.
  const picks = panelPicks.slice(0, maxPanels);
  const panels = PANELS.filter((p) => picks.includes(p));
  // The view a full grid just turned off to make room, said for a moment under the bar.
  const [bumped, setBumped] = useState<PanelId | null>(null);
  useEffect(() => {
    if (!bumped) return;
    const t = setTimeout(() => setBumped(null), 2600);
    return () => clearTimeout(t);
  }, [bumped]);
  const toggleView = useCallback(
    (id: PanelId) => {
      track("view_toggled", { view: id, on: !picks.includes(id) }, lessonId);
      const next = togglePanel(picks, id, maxPanels);
      setPanels(next);
      setBumped(picks.find((p) => !next.includes(p) && p !== id && !(isCamera(id) && isCamera(p))) ?? null);
    },
    [maxPanels, picks, lessonId],
  );
  const [mirrored, setMirrored] = useState(false);
  const [follow, setFollow] = useState(true);
  const [absent, setAbsent] = useState<string[]>([]);
  const focusRef = useRef<Focus | null>(null);
  useEffect(() => {
    // A camera that pans through a scene is the motion reduced-motion exists for.
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) setFollow(false);
  }, []);

  // ---- the clock and its loop
  const loopTimes = (s: LoopSpan | null): [number, number] | null => {
    if (!s) return null;
    const [a, b] = loopTimesS(structure.grid, s);
    return [Math.max(0, a), Math.min(b, endS)];
  };
  const loopRef = useRef<[number, number] | null>(null);
  loopRef.current = loopTimes(loop);
  const onWrapRef = useRef<(() => void) | null>(null);
  const { timeRef, displayTime } = useVideoClock(video, loopRef, onWrapRef);
  const [playing, setPlayingState] = useState(false);
  const playingRef = useRef(false);
  const setPlaying = useCallback((p: boolean) => {
    // A pause fired by the old <video> being unmounted must not count as the learner's.
    if (!p && video && !video.isConnected) return;
    playingRef.current = p;
    setPlayingState(p);
  }, [video]);

  // Playing time, wall-clock, for `play_seconds` (30 s buckets, lib/analytics.ts).
  useEffect(() => {
    if (!playing) return;
    let last = Date.now();
    const tick = () => {
      const now = Date.now();
      addPlay((now - last) / 1000, lessonId);
      last = now;
    };
    const id = window.setInterval(tick, 5000);
    return () => (window.clearInterval(id), tick());
  }, [playing, lessonId]);

  // One pass of the loop: build-up steps up, and counts played through at full
  // speed get their tick.
  const speedRef = useRef(speed);
  speedRef.current = speed;
  onWrapRef.current = () => {
    setPasses((p) => p + 1);
    // 1.25× is full speed and then some: it counts.
    if (loop && speedRef.current >= 1 && !spanDone(done, loop)) {
      const next = markDone(done, loop);
      setDone(next);
      saveDone(lessonId, next);
    }
  };

  // A layout switch (rotating the phone) mounts a new <video>; carry the time over.
  // Playing carries over too: a rotation mid-loop keeps dancing.
  const resumeAt = useRef<number | null>(null);
  const resumePlaying = useRef(false);
  useEffect(() => {
    if (!video) return;
    const seekIn = () => {
      video.currentTime = resumeAt.current ?? loopRef.current?.[0] ?? 0;
      if (resumePlaying.current) void video.play().catch(() => {});
    };
    if (video.readyState >= 1) seekIn();
    else video.addEventListener("loadedmetadata", seekIn, { once: true });
    return () => {
      resumeAt.current = timeRef.current;
      // Not `video.paused`: a <video> leaving the document pauses itself first.
      resumePlaying.current = playingRef.current;
    };
  }, [video, timeRef]);

  // Count 1 moved while paused: stay on the same counts, now one count over.
  useEffect(() => {
    const lp = loopRef.current;
    if (!video || !video.paused || !lp || video.readyState < 1) return;
    if (video.currentTime < lp[0] - 0.05 || video.currentTime >= lp[1]) video.currentTime = lp[0];
  }, [video, structure]);

  useEffect(() => {
    if (!video) return;
    // Slower, not lower: the song keeps its key at 0.25× (the default, set anyway
    // because some engines have shipped it off; Safari before 17 reads the prefixed one).
    video.preservesPitch = true;
    (video as { webkitPreservesPitch?: boolean }).webkitPreservesPitch = true;
    video.playbackRate = speed;
  }, [video, speed]);

  const play = useCallback(() => {
    if (!video) return;
    const lp = loopRef.current;
    // Play starts inside the loop, not wherever the playhead drifted.
    if (lp && (video.currentTime < lp[0] - 0.05 || video.currentTime >= lp[1])) video.currentTime = lp[0];
    if (!lp && video.currentTime >= endS - 0.05) video.currentTime = 0;
    if (clickOnRef.current) unlockAudio(); // inside the tap: iOS suspends audio between plays
    void video.play().catch(() => {});
  }, [video, endS]);
  const pause = useCallback(() => video?.pause(), [video]);
  const togglePlay = useCallback(() => (video?.paused ? play() : pause()), [video, play, pause]);
  const seek = useCallback(
    (t: number) => {
      if (video) video.currentTime = Math.min(Math.max(t, 0), endS);
    },
    [video, endS],
  );

  /**
   * Change the loop: build-up starts over, and the playhead jumps into the new loop —
   * or, with `keep` (a handle dragged), stays put if it is already inside it.
   */
  const loopVia = useRef<LoopVia>("other");
  const setLoop = useCallback(
    (next: LoopSpan | null, opts: { play?: boolean; keep?: boolean; via?: LoopVia } = {}) => {
      loopVia.current = opts.via ?? "other";
      setLoopState(next);
      setPasses(0);
      // Sync before seeking: the seek's own clock tick must not wrap back into the old loop.
      loopRef.current = loopTimes(next);
      const lp = loopRef.current;
      const inside = !!video && !!lp && video.currentTime >= lp[0] && video.currentTime < lp[1];
      if (video && lp && !(opts.keep && inside)) video.currentTime = lp[0];
      if (video && opts.play) void video.play().catch(() => {});
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps -- loopTimes is pure over structure/endS
    [video, structure, endS],
  );
  // `loop_created` once a loop has settled for a second, so a drag across the
  // counts is one loop, not one per count it crossed.
  useEffect(() => {
    if (!loop) return;
    const half = (c: number) => Number.isInteger(c * 2);
    const id = window.setTimeout(() => track("loop_created", {
      counts: loopLength(loop), start: loop.startCount,
      snapped: half(loop.startCount) && half(loop.endCount), via: loopVia.current,
    }, lessonId), 1000);
    return () => window.clearTimeout(id);
  }, [loop, lessonId]);

  const setBuildUp = useCallback((on: boolean) => {
    setBuildUpState(on);
    setPasses(0);
  }, []);

  /** The chip under the playhead, and the count (for swipes from the whole dance). */
  const hereCount = currentCount(structure.grid, displayTime);
  const here: Eight | null = eights.find((e) => hereCount >= e.startCount && hereCount <= e.endCount) ?? null;
  const loopEight = eightOf(eights, loop);
  /**
   * Next or previous: the loop moves by its own length (a dragged 3& – 6 steps on by
   * 3½). With no loop, the playhead moves by an eight and nothing starts looping.
   * 0 = loop the preset length from here.
   */
  const preset = presetCounts(loopLen, total);
  const stepLoop = useCallback(
    (delta: number, opts: { play?: boolean } = {}) => {
      if (!loop && delta !== 0) {
        const c = Math.min(Math.max(1, eightStartCount(hereCount) + delta * 8), total);
        seek(timeOfCount(structure.grid, c));
        if (opts.play && video) void video.play().catch(() => {});
        return;
      }
      setLoop(stepLoopBy(loop, hereCount, delta === 0 || !loop ? preset : loopLength(loop), delta, total), {
        ...opts, via: delta === 0 ? "preset" : "step",
      });
    },
    [loop, hereCount, preset, total, setLoop, seek, structure, video],
  );
  /** A preset re-cuts the current loop from its first count, or loops that many from here. */
  const setLoopLen = useCallback(
    (len: number) => {
      setLoopLenState(len);
      saveLoopLength(lessonId, len);
      setLoop(stepLoopBy(loop, hereCount, presetCounts(len, total), 0, total), { play: playingRef.current, via: "preset" });
    },
    [lessonId, loop, hereCount, total, setLoop],
  );
  const next = passes >= 1 && loop ? nextLoop(loop, loopLength(loop), total) : null;

  // ---- first open: the whole dance, unless the hand-off brought a loop
  const opened = useRef(false);
  useEffect(() => {
    if (!restored || opened.current || !video) return;
    opened.current = true;
    // The processing screen's hand-off (lib/flow.ts handoffHref): the learner was
    // already practising a speed and some counts, so the lesson opens on the same ones.
    const q = parseHandoff(window.location.search, SPEED_GRID, total);
    if (q.speed !== null) setSpeed(q.speed);
    if (q.loop) setLoop(q.loop, { via: "handoff" });
  }, [restored, video, total, setLoop]);

  // ---- the click: on our count grid, locked to the video clock (useMetronome)
  const [clickOn, setClickOnState] = useState(false);
  const clickOnRef = useRef(false);
  clickOnRef.current = clickOn;
  const [clickMode, setClickMode] = useState<ClickMode>("counts");
  const [clickVol, setClickVolState] = useState(0.3);
  const [musicVol, setMusicVolState] = useState(1);
  useEffect(() => {
    setClickVolState(loadClickVolume());
    setMusicVolState(loadMusicVolume());
  }, []);
  /** Must run inside the tap that turns it on: iOS only starts audio from a gesture. */
  const setClickOn = useCallback((on: boolean) => {
    if (on) unlockAudio();
    setClickOnState(on);
  }, []);
  const setClickVol = useCallback((v: number) => (setClickVolState(v), saveClickVolume(v)), []);
  const setMusicVol = useCallback((v: number) => (setMusicVolState(v), saveMusicVolume(v)), []);
  useEffect(() => {
    if (video) video.volume = musicVol;
  }, [video, musicVol]);
  useMetronome(video, loopRef, structure.grid, clickOn, clickMode, clickVol);

  // ---- the "&" between the counts on screen: per device, and apart from the click's own "and"s
  const [showAnds, setShowAndsState] = useState(true);
  useEffect(() => setShowAndsState(loadShowAnds()), []);
  const setShowAnds = useCallback((on: boolean) => (setShowAndsState(on), saveShowAnds(on)), []);

  // ---- count 1: one tap, a nudge, or one of the tracker's other candidates
  // Each is also a `count_one_*` event: how often count 1 needs correcting.
  const alternates = doc.proposed_counts?.count_one_alternates ?? [];
  const tapOne = useCallback(() => {
    track("tap_on_one", undefined, lessonId);
    editStructure(tapOnOne(structure, timeRef.current, endS));
  }, [structure, timeRef, endS, editStructure, lessonId]);
  const nudgeOne = useCallback((d: number) => {
    track("count_one_nudged", { by: d }, lessonId);
    editStructure(nudgeCountOne(structure, d, endS));
  }, [structure, endS, editStructure, lessonId]);
  const tryOne = useCallback((s: number) => {
    const shift = alternates.find((a) => a.count_one_s === s)?.shift_counts;
    track("count_one_alternate", shift === undefined ? undefined : { shift }, lessonId);
    editStructure(setCountOne(structure, s, endS));
  }, [structure, endS, editStructure, lessonId, alternates]);

  // Picking a speed, a preset or a fine step, is the learner taking over from Build up.
  const pickSpeed = useCallback((s: number) => {
    setBuildUp(false);
    setSpeed(clampSpeed(s));
  }, [setBuildUp]);
  /** S: the next preset up. */
  const cycleSpeed = useCallback(() => pickSpeed(nextPreset(speedPick)), [pickSpeed, speedPick]);
  /** − / + (and < / >): 0.05× slower or faster. */
  const nudgeSpeed = useCallback((dir: number) => pickSpeed(stepSpeed(speedPick, dir)), [pickSpeed, speedPick]);

  // `speed_changed` once the speed has settled for a second: five taps on + are one change.
  const firstSpeed = useRef(speedPick);
  useEffect(() => {
    if (speedPick === firstSpeed.current) return;
    firstSpeed.current = NaN; // from here on, every settled change counts (back to 1× too)
    const id = window.setTimeout(() => track("speed_changed", { speed: speedPick }, lessonId), 1000);
    return () => window.clearTimeout(id);
  }, [speedPick, lessonId]);
  useOnChange(buildUp, (on) => track("build_up_toggled", { on }, lessonId));
  useOnChange(`${clickOn}|${clickMode}`, () => track("click_toggled", { on: clickOn, mode: clickMode }, lessonId));

  const crop = useVideoCrop(video, doc, focusRef, timeRef, selected, follow && panels.includes("video"), mirrored);

  return {
    doc, title, videoUrl, credit, glbUrls, lessonId, endS, aspect, wide,
    video, setVideo, timeRef, displayTime, playing, setPlaying, play, pause, togglePlay, seek,
    structure, editStructure, authored, countsFrom, oneUnsure, oneChecked, tapOne, nudgeOne, tryOne, alternates,
    eights, loop, setLoop, loopEight, here, hereCount, stepLoop, loopLen, setLoopLen, next, done, sameSpan,
    speed, speedPick, pickSpeed, cycleSpeed, nudgeSpeed, buildUp, setBuildUp, passes, setHoldSlow,
    clickOn, setClickOn, clickMode, setClickMode, clickVol, setClickVol, musicVol, setMusicVol, showAnds, setShowAnds,
    multi, selected, chooseDancer, pickerOpen, setPickerOpen, showEveryone, setShowEveryone,
    panels, maxPanels, bumped, toggleView, mirrored, setMirrored, follow, setFollow,
    absent, setAbsent, focusRef, crop,
    onRemoveFromMyLessons, onReportOrRemove,
  };
}

export type { LoopSpan };
