"use client";

import Link from "next/link";
import type { Lesson } from "../LessonViewer";
import { lesson as copy } from "../../lib/copy";
import {
  accentOf,
  BottomBar,
  CountBar,
  DancerPicker,
  doneLine,
  Icon,
  MoreContent,
  Panels,
  useDancerShots,
  useLessonKeys,
  ViewBar,
  WhoChip,
} from "./pieces";

/**
 * Desktop and tablet, in the original viewer's restraint: one bar of view toggles
 * on top, every view that is on tiled below it, one thin transport and the full-width
 * timeline under them. Everything else is under More.
 */
export default function DesktopLesson({ l }: { l: Lesson }) {
  useLessonKeys(l);
  const shots = useDancerShots(l);

  return (
    <main className="ls ls-desk" style={{ ["--accent" as string]: accentOf(l) }}>
      <h1 className="sr-only">{l.title}</h1>
      <ViewBar
        l={l}
        start={
          <Link href="/" className="ls-icon-btn" aria-label={copy.transport.back}>
            <Icon name="left" />
          </Link>
        }
        end={
          <div className="ls-bar-end">
            <span className="ls-meter">{doneLine(l)}</span>
            <WhoChip l={l} shots={shots} />
          </div>
        }
      />
      <Panels l={l}>
        <div className="ls-stage-counts">
          <CountBar l={l} select />
        </div>
      </Panels>
      <BottomBar
        l={l}
        more={
          <>
            <button type="button" className="ls-pill ls-more-btn" popoverTarget="ls-more-desk">
              <Icon name="dots" size={18} />
              <span>{copy.transport.more}</span>
            </button>
            <div id="ls-more-desk" popover="auto" className="ls-panel">
              <MoreContent l={l} />
            </div>
          </>
        }
      />
      <DancerPicker l={l} shots={shots} />
    </main>
  );
}
