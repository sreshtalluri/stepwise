"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Focus } from "./Stage3D";
import { defaultPersonIndex, SPEEDS, type MotionResult, type ViewId } from "../lib/motion";
import { load, openingStructure, save } from "../lib/structure";
import { parseHandoff } from "../lib/flow";
import {
  isComplete,
  lessonUnits,
  loadLearned,
  nextRound,
  roundAt,
  saveLearned,
  schedule,
  stepStart,
  type Step,
  type Unit,
} from "../lib/lessonEngine";
import {
  currentCount,
  loopTimesS,
  nudgeCountOne,
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
 * There is exactly one clock — the `<video>` — and one loop, applied inside it
 * (`useVideoClock`). The lesson path's rounds advance on that clock's wrap.
 */
export interface LessonViewerProps {
  doc: MotionResult;
  title: string;
  videoUrl: string;
  /** One GLB URL per entry in `doc.persons`. */
  glbUrls: string[];
  /** Scope for the learner's counts, parts, learned 8-counts and dancer. */
  lessonId: string;
}

export type MainView = "video" | "overlay" | "3d";
export type Mode = "lesson" | "free";

const DANCER_KEY = (id: string) => `stepwise.lesson-dancer.v1.${id}`;

export default function LessonViewer(props: LessonViewerProps) {
  const l = useLesson(props);
  const phone = useMedia(PHONE_QUERY);
  return phone ? <PhoneLesson l={l} /> : <DesktopLesson l={l} />;
}

export type Lesson = ReturnType<typeof useLesson>;

function useLesson({ doc, title, videoUrl, glbUrls, lessonId }: LessonViewerProps) {
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

  // ---- the path
  const units = useMemo(() => lessonUnits(structure), [structure]);
  const eights = useMemo(() => units.filter((u) => u.kind === "eight"), [units]);
  const [learned, setLearned] = useState<Set<string>>(new Set());
  useEffect(() => setLearned(loadLearned(lessonId)), [lessonId]);
  const [unitIndex, setUnitIndex] = useState(0);
  const unit: Unit = units[Math.min(unitIndex, units.length - 1)];
  const rounds = useMemo(() => schedule(unit.kind), [unit.kind]);
  const [round, setRound] = useState(0);
  const [mode, setMode] = useState<Mode>("lesson");
  const [freeSpeed, setFreeSpeed] = useState(1);
  const [freeLoop, setFreeLoop] = useState<"unit" | "all">("unit");
  const [holdSlow, setHoldSlow] = useState(false);
  const complete = mode === "lesson" && isComplete(rounds, round);
  const current = roundAt(rounds, round);
  const speed = holdSlow ? 0.5 : mode === "lesson" ? current.speed : freeSpeed;
  const yourTurn = mode === "lesson" && !complete && !!current.yourTurn;

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

  // ---- views
  const [view, setView] = useState<MainView>("overlay"); // mesh on video is the default for Watch
  const [angle, setAngle] = useState<ViewId>("front");
  const [extras, setExtras] = useState<ViewId[]>([]);
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
  const loopFor = (u: Unit, s: LessonStructure): [number, number] => {
    const [a, b] = loopTimesS(s.grid, u);
    return [Math.max(0, a), Math.min(b, endS)];
  };
  const loopRef = useRef<[number, number] | null>(null);
  loopRef.current = mode === "free" && freeLoop === "all" ? null : loopFor(unit, structure);
  const onWrapRef = useRef<(() => void) | null>(null);
  const { timeRef, displayTime } = useVideoClock(video, loopRef, onWrapRef);
  const [playing, setPlaying] = useState(false);

  // A layout switch (rotating the phone) mounts a new <video>; carry the time over.
  const resumeAt = useRef<number | null>(null);
  useEffect(() => {
    if (!video) return;
    const seekIn = () => {
      video.currentTime = resumeAt.current ?? loopRef.current?.[0] ?? 0;
    };
    if (video.readyState >= 1) seekIn();
    else video.addEventListener("loadedmetadata", seekIn, { once: true });
    return () => {
      resumeAt.current = timeRef.current;
    };
  }, [video, timeRef]);

  // Paused and outside the window being learned (a new unit, count 1 moved): go to its start.
  useEffect(() => {
    const lp = loopRef.current;
    if (!video || !video.paused || !lp || video.readyState < 1) return;
    if (video.currentTime < lp[0] - 0.05 || video.currentTime >= lp[1]) video.currentTime = lp[0];
  }, [video, unitIndex, structure]);

  useEffect(() => {
    if (video) video.playbackRate = speed;
  }, [video, speed]);

  const play = useCallback(() => {
    if (!video) return;
    const loop = loopRef.current;
    // Play starts inside the window being learned, not wherever the playhead drifted.
    if (loop && (video.currentTime < loop[0] - 0.05 || video.currentTime >= loop[1])) video.currentTime = loop[0];
    void video.play().catch(() => {});
  }, [video]);
  const pause = useCallback(() => video?.pause(), [video]);
  const togglePlay = useCallback(() => (video?.paused ? play() : pause()), [video, play, pause]);
  const seek = useCallback(
    (t: number) => {
      if (video) video.currentTime = Math.min(Math.max(t, 0), endS);
    },
    [video, endS],
  );

  /** Open a unit: its loop window, the first round of its ladder, paused unless asked. */
  const goUnit = useCallback(
    (i: number, opts: { play?: boolean; step?: Step } = {}) => {
      const k = Math.max(0, Math.min(units.length - 1, i));
      const u = units[k];
      setUnitIndex(k);
      setRound(opts.step ? stepStart(schedule(u.kind), opts.step) : 0);
      // Sync the loop before seeking: the seek's own clock tick must not wrap back
      // into the unit being left.
      loopRef.current = mode === "free" && freeLoop === "all" ? null : loopFor(u, structure);
      if (video) {
        video.currentTime = loopFor(u, structure)[0];
        if (opts.play ?? !video.paused) void video.play().catch(() => {});
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps -- loopFor is pure over its args
    [units, video, mode, freeLoop, structure],
  );
  /** Step between 8-counts only; joins are reached from the path. */
  const stepEight = useCallback(
    (delta: number, opts: { play?: boolean; step?: Step } = {}) => {
      const here = units[unitIndex];
      const pos = eights.findIndex((e) => e.id === here.id);
      const from = pos >= 0 ? pos : eights.findIndex((e) => e.endCount >= here.endCount);
      const target = eights[Math.max(0, Math.min(eights.length - 1, from + delta))];
      goUnit(units.indexOf(target), opts);
    },
    [units, eights, unitIndex, goUnit],
  );

  const setStep = useCallback(
    (step: Step) => {
      setMode("lesson");
      setRound(stepStart(rounds, step));
      if (video && loopRef.current) video.currentTime = loopRef.current[0];
      play();
    },
    [rounds, video, play],
  );

  const [checkIn, setCheckIn] = useState(false);
  const roundRef = useRef(round);
  roundRef.current = round;
  onWrapRef.current = () => {
    if (mode !== "lesson") return;
    const r = roundRef.current;
    const n = nextRound(rounds, r);
    roundRef.current = n;
    if (n !== r) setRound(n);
    if (isComplete(rounds, n) && !isComplete(rounds, r)) {
      // Done with the ladder: stop on count 1 and ask, rather than loop on forever.
      video?.pause();
      setCheckIn(true);
    }
  };
  useEffect(() => setCheckIn(false), [unitIndex, mode]);

  const gotIt = useCallback(() => {
    const next = new Set(learned).add(unit.id);
    setLearned(next);
    saveLearned(lessonId, next);
    setCheckIn(false);
    const after = units.findIndex((u, i) => i > unitIndex && !next.has(u.id));
    if (after >= 0) goUnit(after, { play: false });
  }, [learned, unit, lessonId, units, unitIndex, goUnit]);
  const again = useCallback(() => {
    setCheckIn(false);
    setRound(stepStart(rounds, "slow"));
    play();
  }, [rounds, play]);

  // ---- free practice follows the playhead when it is not looping
  useEffect(() => {
    if (mode !== "free" || freeLoop !== "all") return;
    const c = currentCount(structure.grid, displayTime);
    const i = units.findIndex((u) => u.kind === "eight" && c >= u.startCount && c <= u.endCount);
    if (i >= 0 && i !== unitIndex) setUnitIndex(i);
  }, [mode, freeLoop, displayTime, structure, units, unitIndex]);

  // ---- first open: the first unit not yet learned, or the hand-off's loop and speed
  const opened = useRef(false);
  useEffect(() => {
    if (!restored || opened.current) return;
    opened.current = true;
    // The processing screen's hand-off (lib/flow.ts handoffHref): the learner was
    // already practising a speed and an 8-count, so open "Just practise" on them.
    const q = parseHandoff(window.location.search, SPEEDS, structure.grid.countTotal);
    if (q.speed !== null || q.loop) {
      setMode("free");
      if (q.speed !== null) setFreeSpeed(q.speed);
      if (q.loop) {
        const i = units.findIndex((u) => u.kind === "eight" && u.startCount <= q.loop!.startCount && q.loop!.startCount <= u.endCount);
        setUnitIndex(Math.max(0, i));
      }
      return;
    }
    const saved = loadLearned(lessonId);
    const first = units.findIndex((u) => !saved.has(u.id));
    setUnitIndex(first >= 0 ? first : 0);
  }, [restored, structure, units, lessonId]);

  // ---- count 1: the correction that has to be one tap
  const tapOne = useCallback(() => {
    editStructure(tapOnOne(structure, timeRef.current, endS));
  }, [structure, timeRef, endS, editStructure]);
  const nudgeOne = useCallback(
    (d: number) => {
      const next = nudgeCountOne(structure, d, endS);
      editStructure(next);
    },
    [structure, endS, editStructure],
  );

  const cycleFreeSpeed = useCallback(() => {
    setMode("free");
    setFreeSpeed((s) => SPEEDS[(SPEEDS.indexOf(s as 1) + 1) % SPEEDS.length] ?? 1);
  }, []);
  const toFree = useCallback(() => {
    setFreeSpeed(roundAt(rounds, round).speed);
    setMode("free");
  }, [rounds, round]);

  const crop = useVideoCrop(video, doc, focusRef, timeRef, selected, follow && view === "video", mirrored);

  return {
    doc, title, videoUrl, glbUrls, lessonId, endS,
    video, setVideo, timeRef, displayTime, playing, setPlaying, play, pause, togglePlay, seek,
    structure, editStructure, authored, countsFrom, tapOne, nudgeOne,
    units, eights, unit, unitIndex, goUnit, stepEight, learned,
    mode, setMode, toFree, rounds, round, current, complete, yourTurn, setStep, checkIn, gotIt, again,
    speed, freeSpeed, setFreeSpeed, cycleFreeSpeed, freeLoop, setFreeLoop, setHoldSlow,
    multi, selected, chooseDancer, pickerOpen, setPickerOpen,
    view, setView, angle, setAngle, extras, setExtras, mirrored, setMirrored, follow, setFollow,
    showCrops, setShowCrops, absent, setAbsent, focusRef, crop,
  };
}

export type { LoopSpan };
