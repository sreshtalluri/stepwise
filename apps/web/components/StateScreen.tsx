"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";
import { Lockup } from "./brand/Mark";
import { lesson as lessonCopy, marketing } from "../lib/copy";
import { drawPose, statePoseAt, type StatePose } from "../lib/countoff";
import { prefersReducedMotion } from "../lib/reveal";
import type { Failure } from "../lib/submit";

/**
 * Every non-happy state, "Quiet dancer" style (the lesson loading screen's
 * look): a small thin figure in one pose with a gentle idle motion (still
 * under reduced motion), one headline, one line, one primary action.
 *
 * Pose vocabulary, one meaning each (lib/countoff.ts STATE_POSES):
 *   shrug nothing here · sit not yet · wave gone · breathe a limit ·
 *   look cannot reach or load · sitback did not make it through · ready nothing yet
 *
 * <StateScreen> is a whole page; <StateBlock> is its middle, for a state
 * inside a page; <StateNote> is the compact form-error line with a tiny figure.
 */

/** The figure beside each front-door failure (lib/submit.ts). */
export const FAILURE_POSE: Record<Failure, StatePose> = {
  limit: "breathe",
  invite: "shrug",
  refused: "look",
  file: "shrug",
  unreachable: "look",
};

export type StateAction =
  | { label: string; href: string }
  | { label: string; onClick: () => void; disabled?: boolean };

const SIZES = { mini: [36, 52], mid: [72, 96], full: [120, 160] } as const;

export function StateFigure({ pose, size = "full" }: { pose: StatePose; size?: keyof typeof SIZES }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const [w, h] = SIZES[size];

  useEffect(() => {
    const cv = ref.current;
    const ctx = cv?.getContext("2d");
    if (!cv || !ctx) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    cv.width = w * dpr;
    cv.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const ink = getComputedStyle(cv).getPropertyValue("--ink").trim() || "#221e1c";
    const still = prefersReducedMotion();
    const start = performance.now();
    let raf = 0;
    const frame = (now: number) => {
      ctx.clearRect(0, 0, w, h);
      drawPose(ctx, w / 2, h - 4, h - 8, statePoseAt(pose, still ? 0 : (now - start) / 1000), {
        color: ink,
        flip: false,
      });
      if (!still) raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, [pose, w, h]);

  return <canvas ref={ref} style={{ width: w, height: h }} aria-hidden="true" />;
}

function Action({ action, className }: { action: StateAction; className: string }) {
  return "href" in action ? (
    <Link href={action.href} className={className}>{action.label}</Link>
  ) : (
    <button type="button" className={className} onClick={action.onClick} disabled={action.disabled}>
      {action.label}
    </button>
  );
}

export function StateBlock({
  pose,
  title,
  body,
  action,
  secondary,
  dots = false,
  heading: H = "h1",
  alert = false,
}: {
  pose: StatePose;
  title: string;
  body: string;
  action: StateAction;
  secondary?: StateAction;
  /** Eight unlit count dots: nothing counted yet. */
  dots?: boolean;
  heading?: "h1" | "h2";
  /** The body is news (a failure the service just reported): announce it. */
  alert?: boolean;
}) {
  return (
    <div className="fd ss-quiet">
      <StateFigure pose={pose} />
      {dots && (
        <div className="ll-dots" aria-hidden="true">
          {[1, 2, 3, 4, 5, 6, 7, 8].map((n) => <i key={n} />)}
        </div>
      )}
      <H className="ss-title">{title}</H>
      <p className="ss-text" role={alert ? "alert" : undefined}>{body}</p>
      <Action action={action} className="fd-btn" />
      {secondary && <Action action={secondary} className="ss-link" />}
    </div>
  );
}

/** The site's top bar: the logo home, and one link. Every page but the lesson has it. */
export function SiteNav({ to = "lessons" }: { to?: "lessons" | "add" }) {
  return (
    <nav className="fd-nav">
      <Lockup />
      <div className="fd-nav-r">
        {to === "add" ? (
          <Link href="/upload" className="fd-btn fd-btn-sm">{marketing.nav.add}</Link>
        ) : (
          <Link href="/lessons">{marketing.nav.myLessons}</Link>
        )}
      </div>
    </nav>
  );
}

export default function StateScreen(props: Parameters<typeof StateBlock>[0]) {
  return (
    <main className="fd ss">
      <SiteNav />
      <div className="ss-body">
        <StateBlock {...props} />
      </div>
    </main>
  );
}

/** The compact, in-page variant: the form-error box with a tiny figure and at most one action. */
export function StateNote({ pose, message, action }: { pose: StatePose; message: string; action?: StateAction }) {
  return (
    <div className="form-error ss-note" role="alert">
      <StateFigure pose={pose} size="mini" />
      <div>
        <p>{message}</p>
        {action && <Action action={action} className="ss-link" />}
      </div>
    </div>
  );
}

/** A lesson or job link that did not resolve, by the service's status. Shared by the lesson and processing pages. */
export function LoadFailed({ status, lessonId }: { status: number; lessonId: string }) {
  const copy = lessonCopy.load;
  if (status === 409) {
    return (
      <StateScreen pose="sit" title={copy.notReady} body={copy.notReadyBody}
        action={{ label: copy.notReadyLink, href: `/job/${encodeURIComponent(lessonId)}` }} />
    );
  }
  if (status === 410) {
    return <StateScreen pose="wave" title={copy.removed} body={copy.removedBody} action={{ label: copy.removedLink, href: "/" }} />;
  }
  if (status === 404) {
    return <StateScreen pose="shrug" title={copy.notFound} body={copy.notFoundBody} action={{ label: copy.notFoundLink, href: "/upload" }} />;
  }
  return (
    <StateScreen pose="look" title={copy.failed} body={copy.failedBody} alert
      action={{ label: copy.failedLink, onClick: () => window.location.reload() }} />
  );
}
