"use client";

import Link from "next/link";
import type { Lesson } from "../LessonViewer";
import { lesson as copy } from "../../lib/copy";
import type { ViewId } from "../../lib/motion";
import {
  accentOf,
  AnglePane,
  CloseUps,
  CountBar,
  DancerPicker,
  doneLine,
  EightChips,
  Icon,
  MainStage,
  MoreContent,
  Transport,
  useDancerShots,
  useLessonKeys,
  WhoChip,
} from "./pieces";

/** Up to two 3D angles beside the main stage: three panes is the most that stay readable. */
const MAX_EXTRAS = 2;

/**
 * Desktop and tablet (DESIGN.md §6): the mesh on the video with a 3D angle beside it
 * (add a second or third), close-ups on the right, and under them the one row of
 * chips, the loop length and the transport. Everything else is under More.
 */
export default function DesktopLesson({ l }: { l: Lesson }) {
  useLessonKeys(l);
  const shots = useDancerShots(l);
  const addAngle = () => {
    const used = new Set<ViewId>([l.view === "3d" ? l.angle : "camera", ...l.extras]);
    const next = (["front", "side", "back", "top"] as ViewId[]).find((a) => !used.has(a)) ?? "side";
    l.setExtras([...l.extras, next]);
  };

  return (
    <main className="ls ls-desk" style={{ ["--accent" as string]: accentOf(l) }}>
      <header className="ls-head">
        <Link href="/" className="ls-icon-btn" aria-label={copy.transport.back}>
          <Icon name="left" />
        </Link>
        <h1 className="ls-title">{l.title}</h1>
        <span className="ls-meter">{doneLine(l)}</span>
        <div className="ls-head-end">
          <WhoChip l={l} shots={shots} />
        </div>
      </header>

      <div className="ls-body">
        <div className="ls-views" data-n={1 + l.extras.length}>
          <MainStage l={l}>
            <div className="ls-stage-counts">
              <CountBar l={l} select />
            </div>
          </MainStage>
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
          {l.extras.length < MAX_EXTRAS && (
            <button type="button" className="ls-add-angle" onClick={addAngle} aria-label={copy.views.addAngle} title={copy.views.addAngle}>
              <Icon name="plus" size={22} />
            </button>
          )}
        </div>

        <CloseUps
          l={l}
          className="ls-desk-closeups"
          onRegion={(r) => {
            l.setView("3d");
            l.setAngle(r.includes("hand") ? "hands" : "feet");
          }}
        />

        <EightChips l={l} />
        <Transport
          l={l}
          more={
            <>
              <button type="button" className="ls-more-btn" popoverTarget="ls-more-desk">
                <Icon name="dots" size={22} />
                <span>{copy.transport.more}</span>
              </button>
              <div id="ls-more-desk" popover="auto" className="ls-panel">
                <MoreContent l={l} />
              </div>
            </>
          }
        />
      </div>

      <DancerPicker l={l} shots={shots} />
    </main>
  );
}
