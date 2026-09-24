"use client";

import Link from "next/link";
import type { Lesson, MainView } from "../LessonViewer";
import { lesson as copy } from "../../lib/copy";
import { SPEEDS, type ViewId } from "../../lib/motion";
import {
  accentOf,
  AnglePane,
  ANGLES,
  CheckIn,
  CloseUps,
  CountBar,
  CountOneTools,
  DancerPicker,
  Help,
  Icon,
  learnedLine,
  MainStage,
  PathNav,
  PlayButton,
  Steps,
  useDancerShots,
  useLessonKeys,
  WhoChip,
  type IconName,
} from "./pieces";
import { viewLabel } from "../../lib/motion";

/** Up to two extra 3D angles beside the main stage: three panes is the most that stay readable. */
const MAX_EXTRAS = 2;

/**
 * Desktop and tablet (DESIGN.md §6): the lesson path on the left, the main stage with
 * up to two more angles beside it, close-ups on the right, and under them the count
 * strip with count-1 correction and either the lesson ladder or the free-practice bar.
 */
export default function DesktopLesson({ l }: { l: Lesson }) {
  useLessonKeys(l);
  const shots = useDancerShots(l);
  const addAngle = () => {
    const used = new Set<ViewId>([l.view === "3d" ? l.angle : "camera", ...l.extras]);
    const next = (["side", "front", "back", "top"] as ViewId[]).find((a) => !used.has(a)) ?? "side";
    l.setExtras([...l.extras, next]);
  };

  return (
    <main className="ls ls-desk" style={{ ["--accent" as string]: accentOf(l) }}>
      <header className="ls-head">
        <Link href="/" className="ls-icon-btn" aria-label={copy.transport.back}>
          <Icon name="left" />
        </Link>
        <h1 className="ls-title">{l.title}</h1>
        <span className="ls-meter">{learnedLine(l)}</span>
        <div className="ls-head-end">
          <WhoChip l={l} shots={shots} />
          <ModeSwitch l={l} />
          <Help l={l} id="ls-help-desk" />
        </div>
      </header>

      <div className="ls-body">
        <PathNav l={l} />

        <section className="ls-main">
          <div className="ls-viewbar">
            <ViewSwitch l={l} />
            {l.view === "3d" && (
              <label className="ls-select">
                <span className="sr-only">{copy.views.angle}</span>
                <select value={l.angle} onChange={(e) => l.setAngle(e.target.value as ViewId)}>
                  {ANGLES.map((a) => (
                    <option key={a.id} value={a.id}>
                      {viewLabel(a.id, false)}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <div className="ls-seg">
              <button type="button" aria-pressed={l.mirrored} onClick={() => l.setMirrored((v) => !v)}>
                {l.mirrored ? copy.transport.mirrorOn : copy.transport.mirrorOff}
              </button>
            </div>
            <div className="ls-seg">
              <button type="button" aria-pressed={l.showCrops} onClick={() => l.setShowCrops((v) => !v)}>
                {copy.views.closeups}
              </button>
            </div>
            {l.extras.length < MAX_EXTRAS && (
              <div className="ls-seg">
                <button type="button" onClick={addAngle}>
                  <Icon name="plus" size={16} /> {copy.views.addAngle}
                </button>
              </div>
            )}
          </div>
          <div className="ls-views" data-n={1 + l.extras.length}>
            <MainStage l={l} />
            {l.extras.map((a, i) => (
              <AnglePane
                key={i}
                l={l}
                angle={a}
                // The first extra frames the video crop when the main stage has no 3D of its own.
                focus={i === 0 && l.view !== "3d"}
                onAngle={(v) => l.setExtras(l.extras.map((x, k) => (k === i ? v : x)))}
                onRemove={() => l.setExtras(l.extras.filter((_, k) => k !== i))}
              />
            ))}
          </div>

          <CloseUps
            l={l}
            className="ls-desk-closeups"
            onRegion={(r) => {
              l.setView("3d");
              l.setAngle(r.includes("hand") ? "hands" : "feet");
            }}
          />

          <div className="ls-countrow">
            <div className="ls-unit">
              <b>{l.unit.label}</b>
              <small>{l.mode === "lesson" && !l.complete ? `${l.speed}×` : l.mode === "free" ? `${l.speed}×` : copy.path.gotIt}</small>
            </div>
            <CountBar l={l} />
            <CountOneTools l={l} />
          </div>

          {l.mode === "lesson" ? (
            <div className="ls-ladder">
              <PlayButton l={l} label={false} className="ls-play-sq" />
              <Steps l={l} />
              <button type="button" className={`ls-got${l.complete ? " ls-ready" : ""}`} onClick={l.gotIt}>
                <Icon name="check" size={18} /> {copy.path.gotIt}
              </button>
            </div>
          ) : (
            <FreeBar l={l} />
          )}
          <CheckIn l={l} />
        </section>
      </div>

      <DancerPicker l={l} shots={shots} />
    </main>
  );
}

export function ModeSwitch({ l }: { l: Lesson }) {
  return (
    <div className="ls-seg" role="group" aria-label={copy.modes.group}>
      <button type="button" aria-pressed={l.mode === "lesson"} onClick={() => l.setMode("lesson")}>
        {copy.modes.lesson}
      </button>
      <button type="button" aria-pressed={l.mode === "free"} onClick={l.toFree}>
        {copy.modes.practise}
      </button>
    </div>
  );
}

const VIEWS: { id: MainView; label: string; icon: IconName }[] = [
  { id: "overlay", label: copy.views.overlay, icon: "stack" },
  { id: "video", label: copy.views.video, icon: "video" },
  { id: "3d", label: copy.views.threeD, icon: "cube" },
];

export function ViewSwitch({ l }: { l: Lesson }) {
  return (
    <div className="ls-seg" role="group" aria-label={copy.views.group}>
      {VIEWS.map((v) => (
        <button key={v.id} type="button" aria-pressed={l.view === v.id} onClick={() => l.setView(v.id)}>
          {v.label}
        </button>
      ))}
    </div>
  );
}

/**
 * "Just practise": the studio transport. Any 8-count, any speed from 0.25×, loop it
 * or run the whole dance, with the lesson ladder out of the way.
 */
export function FreeBar({ l, className = "" }: { l: Lesson; className?: string }) {
  return (
    <div className={`ls-free ${className}`}>
      <div className="ls-stepper">
        <button type="button" className="ls-icon-btn" onClick={() => l.stepEight(-1)} aria-label={copy.transport.prev}>
          <Icon name="left" />
        </button>
        <span>{l.unit.label}</span>
        <button type="button" className="ls-icon-btn" onClick={() => l.stepEight(1)} aria-label={copy.transport.next}>
          <Icon name="right" />
        </button>
      </div>
      <PlayButton l={l} label={false} className="ls-play-sq" />
      <div className="ls-seg" role="group" aria-label={copy.transport.speedLabel}>
        {SPEEDS.map((s) => (
          <button key={s} type="button" aria-pressed={l.freeSpeed === s} onClick={() => l.setFreeSpeed(s)}>
            {s}×
          </button>
        ))}
      </div>
      <div className="ls-seg" role="group">
        <button type="button" aria-pressed={l.freeLoop === "unit"} onClick={() => l.setFreeLoop("unit")}>
          {copy.transport.loopThis}
        </button>
        <button
          type="button"
          aria-pressed={l.freeLoop === "all"}
          onClick={() => {
            l.setFreeLoop("all");
            l.play();
          }}
        >
          {copy.transport.wholeDance}
        </button>
      </div>
      <div className="ls-seg">
        <button type="button" aria-pressed={l.follow} onClick={() => l.setFollow((v) => !v)}>
          {l.follow ? copy.transport.followOn : copy.transport.followOff}
        </button>
      </div>
    </div>
  );
}
