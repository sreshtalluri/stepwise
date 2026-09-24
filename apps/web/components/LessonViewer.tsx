"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Focus } from "./Stage3D";
import { defaultPersonIndex, SPEEDS, type MotionResult, type ViewId } from "../lib/motion";
import { load, openingStructure, save } from "../lib/structure";
import { parseHandoff } from "../lib/flow";
import { buildUpSpeed, eightOf, eightsOf, loadDone, nextEight, saveDone, sameSpan, type Eight } from "../lib/lessonEngine";
import {
  currentCount,
  loopTimesS,
  nudgeCountOne,
  setCountOne,
  tapOnOne,
  timelineEndS,
} from "../../../packages/navigation/src/core";
import type { LessonStructure, LoopSpan } from "../../../packages/navigation/src/core";
import { PHONE_QUERY, useMedia, useVideoClock, useVideoCrop } from "./lesson/hooks";
import DesktopLesson from "./lesson/DesktopLesson";
import PhoneLesson from "./lesson/PhoneLesson";
import "./lesson/lesson.css";

/**
 * The lesson page's one state, shared by two compositions (DESIGN.md §6: phone and
 * desktop are different layouts, not one stretched). Same URL for both; the phone one
 * is switched in on narrow or sideways screens, and both read and write only this.
 *
 * One mode, nothing forced: pick an 8-count (or a range, or the whole dance), a speed,
 * optionally Build up, and follow. There is exactly one clock — the `<video>` — and one
 * loop, applied inside it (`useVideoClock`); build-up and the full-speed ticks count
 * that clock's loop passes.
 */
export interface LessonViewerProps {
  doc: MotionResult;
  title: string;
  videoUrl: string;
  /** One GLB URL per entry in `doc.persons`. */
  glbUrls: string[];
  /** Scope for the learner's counts, parts, full-speed ticks and dancer. */
  lessonId: string;
  /** "⋯" menu entries. Wired by the host once those flows exist; absent = shown disabled. */
  onRemoveFromMyLessons?: () => void;
  onReportOrRemove?: () => void;
}

export type MainView = "video" | "overlay" | "3d";

const DANCER_KEY = (id: string) => `stepwise.lesson-dancer.v1.${id}`;

export default function LessonViewer(props: LessonViewerProps) {
  const phone = useMedia(PHONE_QUERY);
  const l = useLesson(props, phone);
  return phone ? <PhoneLesson l={l} /> : <DesktopLesson l={l} />;
}

export type Lesson = ReturnType<typeof useLesson>;

function useLesson(
  { doc, title, videoUrl, glbUrls, lessonId, onRemoveFromMyLessons, onReportOrRemove }: LessonViewerProps,
  phone: boolean,
) {
  const [video, setVideo] = useState<HTMLVideoElement | null>(null);
  const endS = useMemo(() => timelineEndS(doc.sample_times_s), [doc]);

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
    if (restored) save(lessonId, { structure, authored });
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

  // ---- the loop: one eight, a range, or null for the whole dance
  const eights = useMemo(() => eightsOf(structure), [structure]);
  const [loop, setLoopState] = useState<LoopSpan | null>(null);
  const [speedPick, setSpeed] = useState(1);
  const [buildUp, setBuildUpState] = useState(false);
  const [passes, setPasses] = useState(0);
  const [holdSlow, setHoldSlow] = useState(false);
  const speed = holdSlow ? 0.5 : buildUp && loop ? buildUpSpeed(passes) : speedPick;
  const [done, setDone] = useState<Set<string>>(new Set());
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
      try {
        window.localStorage.setItem(DANCER_KEY(lessonId), doc.persons[i].person_id);
      } catch {
        /* see above */
      }
    },
    [doc, lessonId],
  );

  // ---- views: the mesh on the video, plus one 3D angle beside it on a desktop
  const [view, setView] = useState<MainView>("overlay");
  const [angle, setAngle] = useState<ViewId>("front");
  const [extras, setExtras] = useState<ViewId[]>(phone ? [] : ["front"]);
  const [mirrored, setMirrored] = useState(false);
  const [follow, setFollow] = useState(true);
  const [showCrops, setShowCrops] = useState(true);
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

  // One pass of the loop: build-up steps up, and an eight played through at full
  // speed gets its tick.
  const speedRef = useRef(speed);
  speedRef.current = speed;
  onWrapRef.current = () => {
    setPasses((p) => p + 1);
    const e = eightOf(eights, loop);
    if (e && speedRef.current === 1 && !done.has(e.id)) {
      const next = new Set(done).add(e.id);
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

  // Count 1 moved while paused: stay on the same eight, now one count over.
  useEffect(() => {
    const lp = loopRef.current;
    if (!video || !video.paused || !lp || video.readyState < 1) return;
    if (video.currentTime < lp[0] - 0.05 || video.currentTime >= lp[1]) video.currentTime = lp[0];
  }, [video, structure]);

  useEffect(() => {
    if (video) video.playbackRate = speed;
  }, [video, speed]);

  const play = useCallback(() => {
    if (!video) return;
    const lp = loopRef.current;
    // Play starts inside the loop, not wherever the playhead drifted.
    if (lp && (video.currentTime < lp[0] - 0.05 || video.currentTime >= lp[1])) video.currentTime = lp[0];
    if (!lp && video.currentTime >= endS - 0.05) video.currentTime = 0;
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

  /** Change the loop: build-up starts over, and the playhead jumps into the new loop. */
  const setLoop = useCallback(
    (next: LoopSpan | null, opts: { play?: boolean } = {}) => {
      setLoopState(next);
      setPasses(0);
      // Sync before seeking: the seek's own clock tick must not wrap back into the old loop.
      loopRef.current = loopTimes(next);
      if (video && next) video.currentTime = loopRef.current![0];
      if (video && opts.play) void video.play().catch(() => {});
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps -- loopTimes is pure over structure/endS
    [video, structure, endS],
  );
  const setBuildUp = useCallback((on: boolean) => {
    setBuildUpState(on);
    setPasses(0);
  }, []);

  /** The eight under the playhead (for the chip it sits in, and swipes from the whole dance). */
  const hereCount = currentCount(structure.grid, displayTime);
  const here: Eight | null = eights.find((e) => hereCount >= e.startCount && hereCount <= e.endCount) ?? null;
  const loopEight = eightOf(eights, loop);
  const stepEight = useCallback(
    (delta: number, opts: { play?: boolean } = {}) => {
      const from = eightOf(eights, loop) ?? here ?? eights[0];
      const target = eights[Math.max(0, Math.min(eights.length - 1, from.n - 1 + delta))];
      setLoop({ startCount: target.startCount, endCount: target.endCount }, opts);
    },
    [eights, loop, here, setLoop],
  );
  const next = passes >= 1 ? nextEight(eights, loop) : null;

  // ---- first open: loop the first eight not yet done at full speed, or the hand-off's
  const opened = useRef(false);
  useEffect(() => {
    if (!restored || opened.current || !video) return;
    opened.current = true;
    // The processing screen's hand-off (lib/flow.ts handoffHref): the learner was
    // already practising a speed and an 8-count, so the lesson opens on the same ones.
    const q = parseHandoff(window.location.search, SPEEDS, structure.grid.countTotal);
    if (q.speed !== null) setSpeed(q.speed);
    const saved = loadDone(lessonId);
    const first = eights.find((e) => !saved.has(e.id)) ?? eights[0];
    setLoop(q.loop ?? { startCount: first.startCount, endCount: first.endCount });
  }, [restored, video, structure, eights, lessonId, setLoop]);

  // ---- count 1: one tap, a nudge, or one of the tracker's other candidates
  const tapOne = useCallback(() => editStructure(tapOnOne(structure, timeRef.current, endS)), [structure, timeRef, endS, editStructure]);
  const nudgeOne = useCallback((d: number) => editStructure(nudgeCountOne(structure, d, endS)), [structure, endS, editStructure]);
  const tryOne = useCallback((s: number) => editStructure(setCountOne(structure, s, endS)), [structure, endS, editStructure]);
  const alternates = doc.proposed_counts?.count_one_alternates ?? [];

  const cycleSpeed = useCallback(() => {
    setBuildUp(false);
    setSpeed((s) => SPEEDS[(SPEEDS.indexOf(s as 1) + 1) % SPEEDS.length] ?? 1);
  }, [setBuildUp]);

  const crop = useVideoCrop(video, doc, focusRef, timeRef, selected, follow && view === "video", mirrored);

  return {
    doc, title, videoUrl, glbUrls, lessonId, endS,
    video, setVideo, timeRef, displayTime, playing, setPlaying, play, pause, togglePlay, seek,
    structure, editStructure, authored, countsFrom, tapOne, nudgeOne, tryOne, alternates,
    eights, loop, setLoop, loopEight, here, stepEight, next, done, sameSpan,
    speed, speedPick, setSpeed, cycleSpeed, buildUp, setBuildUp, passes, setHoldSlow,
    multi, selected, chooseDancer, pickerOpen, setPickerOpen,
    view, setView, angle, setAngle, extras, setExtras, mirrored, setMirrored, follow, setFollow,
    showCrops, setShowCrops, absent, setAbsent, focusRef, crop,
    onRemoveFromMyLessons, onReportOrRemove,
  };
}

export type { LoopSpan };
