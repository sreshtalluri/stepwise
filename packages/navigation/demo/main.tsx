/**
 * Demo harness for the navigation surface. Both compositions on one page, because
 * DESIGN.md §6 is explicit that the desktop layout is not the phone layout
 * widened and the two have to be judged against each other.
 *
 * Everything here that is not the navigation surface — the stages, the views rail,
 * the video — is a grey placeholder. The 3D viewer is W5's, on `w5-viewer`.
 */

import { StrictMode, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import type { MotionResult } from "../../motion-contract/src/ts/generated/motion-result.js";
import { LessonNavigator, PartsRail } from "../src/LessonNavigator.js";
import {
  advance,
  currentCount,
  loopSpanForPart,
  partRangeAtCount,
  startingStructure,
  timelineEndS,
} from "../src/core.js";
import type { LessonStructure, LoopSpan, PlaybackMode } from "../src/core.js";
import "../src/navigation.css";
import "./demo.css";

import good from "../../motion-contract/fixtures/good-lesson.json";

const result = good as unknown as MotionResult;

/**
 * The fixtures are single-dancer, but `persons` is an unbounded array and
 * multi-dancer is in MVP scope (PRD §5, revised 2026-09-18). A second person is
 * synthesised here so the picker can actually be looked at.
 */
const twoDancers: MotionResult = {
  ...result,
  accent_color: { hex: "#E8952F", source: "fallback" },
  persons: [result.persons[0], { ...result.persons[0], person_id: "person_2", track_id: 2 }],
};

const endS = timelineEndS(result.sample_times_s);

function useLesson() {
  const [structure, setStructure] = useState<LessonStructure>(() => startingStructure(endS, 14 / 30));
  const [timeS, setTimeS] = useState(4.2);
  const [playing, setPlaying] = useState(false);
  const [mode, setMode] = useState<PlaybackMode>("loop");
  const [loop, setLoop] = useState<LoopSpan>({ startCount: 9, endCount: 16 });
  const [personId, setPersonId] = useState("person_1");

  const clock = useRef({ timeS, playing, mode, loop, structure });
  clock.current = { timeS, playing, mode, loop, structure };

  useEffect(() => {
    if (!playing) return;
    let last = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      const dt = (now - last) / 1000;
      last = now;
      const c = clock.current;
      const next = advance(c.timeS, dt, { mode: c.mode, grid: c.structure.grid, loop: c.loop, endS });
      setTimeS(next.timeS);
      if (!next.playing) setPlaying(false);
      else raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing]);

  const here = partRangeAtCount(structure, currentCount(structure.grid, timeS));

  return {
    props: {
      result,
      structure,
      onStructureChange: (s: LessonStructure) => {
        setStructure(s);
        // Keep the loop on the part the learner is standing in after an edit.
        setLoop(loopSpanForPart(partRangeAtCount(s, currentCount(s.grid, timeS))));
      },
      timeS,
      onSeek: setTimeS,
      playing,
      onPlayingChange: setPlaying,
      mode,
      onModeChange: setMode,
      loop,
      onLoopChange: setLoop,
      selectedPersonId: personId,
      onSelectPerson: setPersonId,
    },
    here,
  };
}

/** Stand-in for a stage. The renderer is W5's; this is just a hole of the right shape. */
const Stage = ({ label, className }: { label: string; className?: string }) => (
  <div className={`d-stage ${className ?? ""}`}>
    <span className="d-viewlabel">{label}</span>
    <span className="d-placeholder">{label.includes("clip") ? "original video" : "3D body"}</span>
  </div>
);

const Legend = () => (
  <p className="d-legend">Solid means the app saw it. Sketchy means it is unsure. Dotted means it left the frame.</p>
);

function Phone() {
  const { props } = useLesson();
  return (
    <figure className="d-frame d-phone">
      <div className="d-head">
        <div className="d-title">Say So · chorus</div>
        <div className="d-sub">Learning from your clip · 0:14</div>
      </div>
      <Stage label="side · estimated view" className="d-tall" />
      <Stage label="your clip · camera view" className="d-short" />
      <Legend />
      <LessonNavigator {...props} />
      <figcaption>Phone portrait — 390px</figcaption>
    </figure>
  );
}

function Desktop() {
  const { props } = useLesson();
  return (
    <figure className="d-frame d-desktop">
      <div className="d-top">
        <div>
          <div className="d-title">Say So · chorus</div>
          <div className="d-sub">Learning from your clip · 0:14 · one dancer</div>
        </div>
        <span className="d-share">Share lesson</span>
      </div>
      <div className="d-body">
        <PartsRail {...props} />
        <div className="d-stages">
          <Stage label="your clip · camera view" />
          <Stage label="side · estimated view" />
          <Legend />
        </div>
        <div className="d-views">
          <div className="d-rail-label">Views</div>
          {["Camera", "Mirror", "Side est.", "Back est.", "Top est.", "Hands", "Feet"].map((v) => (
            <div key={v} className="d-view">
              {v}
            </div>
          ))}
        </div>
      </div>
      <div className="d-foot">
        <LessonNavigator {...props} />
      </div>
      <figcaption>Desktop — 1180px. Parts rail left, both stages large, navigation across the foot.</figcaption>
    </figure>
  );
}

function TwoDancers() {
  const { props } = useLesson();
  return (
    <figure className="d-frame d-phone">
      <div className="d-head">
        <div className="d-title">Say So · chorus</div>
        <div className="d-sub">Learning from your clip · 0:14 · two dancers</div>
      </div>
      <Stage label="side · estimated view" className="d-tall" />
      <LessonNavigator {...props} result={twoDancers} />
      <figcaption>Phone — two dancers. One tap to switch; only the chosen one is saturated.</figcaption>
    </figure>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <main className="d-page">
      <Phone />
      <TwoDancers />
      <Desktop />
    </main>
  </StrictMode>,
);
