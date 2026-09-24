"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { Lesson } from "../LessonViewer";
import { lesson as copy } from "../../lib/copy";
import { spanLabel } from "../../lib/lessonEngine";
import {
  BottomBar,
  CountBar,
  DancerPicker,
  Icon,
  MoreContent,
  Panels,
  rootProps,
  useDancerShots,
  ViewBar,
  WhoChip,
} from "./pieces";
import { useMedia, useWakeLock } from "./hooks";

/** Build up reaches 1× on its sixth pass; one more pass at 1× and prop mode moves on. */
const PASSES_TO_FULL_AND_ONCE_MORE = 6;

/**
 * The phone lesson: the page never scrolls. The same three rows as the desktop — the
 * view bar (scrolls sideways), the panels (a main one and at most one inset; side by
 * side when the phone is on its side), the transport and the timeline — and the
 * panels take TikTok's gestures: tap to play, swipe up or down for the next or
 * previous counts, hold for half speed. A drag on the timeline is the timeline's.
 * "Prop it up" drops all chrome for a phone leaning on the wall across the room.
 */
export default function PhoneLesson({ l }: { l: Lesson }) {
  const land = useMedia("(orientation: landscape)");
  const shots = useDancerShots(l);
  const [prop, setProp] = useState(false);
  const [voice, setVoice] = useState(true);
  const [auto, setAuto] = useState(true);
  const [countIn, setCountIn] = useState<number | null>(null);
  const [hint, setHint] = useState(true);
  const { flash, show } = useFlash();
  useWakeLock(prop);

  // ---- the count-in: "5, 6, 7, 8" at the speed about to play.
  const timers = useRef<number[]>([]);
  const cancelCountIn = () => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
    setCountIn(null);
  };
  /**
   * Must be called from inside the tap. iOS only lets a video with sound start from a
   * user gesture, and here the real start is four beats later on a timer — so `play()`
   * runs now (and is paused at once) to unlock it, and the first spoken count is
   * queued now too, for the same reason.
   */
  const countInThen = (go: () => void, speed = l.speed) => {
    cancelCountIn();
    const v = l.video;
    if (!v) return;
    if (!voice) return go();
    v.play().catch(() => {});
    v.pause();
    const beat = (l.structure.grid.secondsPerCount / speed) * 1000;
    const say = (n: number) => {
      setCountIn(n);
      try {
        const u = new SpeechSynthesisUtterance(String(n));
        u.rate = 1.3;
        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(u);
      } catch {
        /* no speech: the number on screen still counts in */
      }
    };
    say(5);
    [6, 7, 8].forEach((n, i) => timers.current.push(window.setTimeout(() => say(n), (i + 1) * beat)));
    timers.current.push(
      window.setTimeout(() => {
        setCountIn(null);
        go();
      }, 4 * beat),
    );
  };
  useEffect(() => () => timers.current.forEach(clearTimeout), []);

  // ---- prop it up: build up runs on its own and moves on to the next counts.
  const enterProp = () => {
    setProp(true);
    document.getElementById("ls-more-ph")?.hidePopover?.();
    document.documentElement.requestFullscreen?.().catch(() => {}); // Android; iOS only from the Home Screen
    if (!l.loop) l.stepLoop(0);
    l.setBuildUp(true);
    countInThen(l.play, 0.5);
  };
  const exitProp = () => {
    cancelCountIn();
    setProp(false);
    l.pause();
    if (document.fullscreenElement) void document.exitFullscreen().catch(() => {});
  };
  const propNext = (d: number) => {
    l.pause();
    l.stepLoop(d);
    countInThen(l.play, 0.5);
  };
  useEffect(() => {
    if (!prop || !auto || !l.buildUp || l.passes < PASSES_TO_FULL_AND_ONCE_MORE) return;
    if (!l.next) return;
    l.pause();
    show(copy.phone.zoneNext);
    const t = window.setTimeout(() => {
      l.stepLoop(1);
      countInThen(l.play, 0.5);
    }, 900);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fires on the pass edge only
  }, [prop, auto, l.passes]);

  // ---- gestures on the stage
  const g = useRef<{ x: number; y: number; held: boolean } | null>(null);
  const holdTimer = useRef(0);
  const onDown = (e: React.PointerEvent) => {
    if (prop || (e.target as HTMLElement).closest("button, a, select, input, .ls-pane")) return;
    g.current = { x: e.clientX, y: e.clientY, held: false };
    holdTimer.current = window.setTimeout(() => {
      if (!g.current || !l.playing) return;
      g.current.held = true;
      l.setHoldSlow(true);
      show(copy.phone.hold);
    }, 450);
  };
  const onUp = (e: React.PointerEvent) => {
    clearTimeout(holdTimer.current);
    const s = g.current;
    g.current = null;
    if (!s) return;
    if (s.held) return l.setHoldSlow(false);
    const dx = e.clientX - s.x, dy = e.clientY - s.y;
    if (Math.abs(dy) > 50 && Math.abs(dy) > Math.abs(dx) * 1.3) {
      l.stepLoop(dy < 0 ? 1 : -1, { play: l.playing });
      setHint(false);
      return;
    }
    if (Math.abs(dx) < 10 && Math.abs(dy) < 10) {
      setHint(false);
      show(l.playing ? copy.phone.paused : copy.transport.play);
      l.togglePlay();
    }
  };
  const onCancel = () => {
    clearTimeout(holdTimer.current);
    if (g.current?.held) l.setHoldSlow(false);
    g.current = null;
  };

  // No loop: nothing to label; the counts alone say where the dance is.
  const loopLabel = l.loop ? (l.loopEight?.label ?? spanLabel(l.loop)) : "";

  return (
    <main {...rootProps(l, `ls-phone${land ? " ls-land" : ""}${prop ? " ls-prop" : ""}`)}>
      <h1 className="sr-only">{l.title}</h1>
      <ViewBar
        l={l}
        start={
          <Link href="/" className="ls-icon-btn" aria-label={copy.transport.back}>
            <Icon name="left" />
          </Link>
        }
        end={l.multi ? <WhoChip l={l} shots={shots} withName={false} /> : undefined}
      />
      <Panels l={l} onPointerDown={onDown} onPointerUp={onUp} onPointerCancel={onCancel}>
        <div className="ls-ph-counts">
          {loopLabel && <span className="ls-ph-unit">{loopLabel}</span>}
          <CountBar l={l} big={prop} />
        </div>
        {hint && !prop && <p className="ls-ph-hint">{copy.phone.hint}</p>}
        <div className={`ls-flash${flash ? " ls-show" : ""}`} aria-live="polite">
          {flash}
        </div>
        {countIn !== null && <div className="ls-countin">{countIn}</div>}
        {prop && (
          <>
            <div className="ls-prop-top">
              <button type="button" className="ls-icon-btn ls-prop-exit" onClick={exitProp} aria-label={copy.phone.exitProp}>
                <Icon name="x" size={28} />
              </button>
              <span className="ls-prop-speed">
                {l.speed}×<small>{loopLabel}</small>
              </span>
            </div>
            <div className="ls-prop-opts">
              <button type="button" aria-pressed={voice} onClick={() => setVoice((v) => !v)}>
                {voice ? copy.phone.countInOn : copy.phone.countInOff}
              </button>
              <button type="button" aria-pressed={auto} onClick={() => setAuto((v) => !v)}>
                {auto ? copy.phone.autoOn : copy.phone.autoOff}
              </button>
            </div>
            <div className="ls-zones">
              <button type="button" aria-label={copy.phone.zoneBack} onClick={() => propNext(-1)} />
              <button
                type="button"
                aria-label={l.playing ? copy.transport.pause : copy.transport.play}
                onClick={() => (l.playing || countIn !== null ? (cancelCountIn(), l.pause()) : countInThen(l.play))}
              />
              <button type="button" aria-label={copy.phone.zoneNext} onClick={() => propNext(1)} />
            </div>
          </>
        )}
      </Panels>
      <BottomBar
        l={l}
        more={
          <>
            <button type="button" className="ls-pill ls-more-btn" popoverTarget="ls-more-ph" aria-label={copy.transport.more}>
              <Icon name="dots" size={18} />
            </button>
            <div id="ls-more-ph" popover="auto" className="ls-panel">
              <MoreContent
                l={l}
                extra={
                  <div className="ls-group-row">
                    <button type="button" className="ls-chip ls-strong ls-accent" onClick={enterProp}>
                      {copy.phone.prop}
                    </button>
                  </div>
                }
              />
            </div>
          </>
        }
      />
      <InstallHint done={l.done.size} />
      <DancerPicker l={l} shots={shots} />
    </main>
  );
}

function useFlash() {
  const [flash, setFlash] = useState("");
  const t = useRef(0);
  const show = (s: string) => {
    setFlash(s);
    clearTimeout(t.current);
    t.current = window.setTimeout(() => setFlash(""), 800);
  };
  return { flash, show };
}

/**
 * Add to Home Screen, offered once the learner has looped some counts at full speed
 * here — not on the landing page, where nobody knows yet whether they want it. iOS
 * has no install prompt, so it gets the one-line how-to; Chromium gets its own prompt.
 */
function InstallHint({ done }: { done: number }) {
  const KEY = "stepwise.install-dismissed.v1";
  const [prompt, setPrompt] = useState<any>(null);
  const [ios, setIos] = useState(false);
  const [dismissed, setDismissed] = useState(true);
  useEffect(() => {
    let d = false;
    try {
      d = window.localStorage.getItem(KEY) === "1";
    } catch {
      /* private mode: offer it; dismissing still hides it for now */
    }
    const standalone = window.matchMedia("(display-mode: standalone)").matches || (navigator as any).standalone === true;
    setDismissed(d || standalone);
    setIos(/iPhone|iPad|iPod/.test(navigator.userAgent));
    const onPrompt = (e: Event) => {
      e.preventDefault();
      setPrompt(e);
    };
    window.addEventListener("beforeinstallprompt", onPrompt);
    return () => window.removeEventListener("beforeinstallprompt", onPrompt);
  }, []);
  if (dismissed || done < 1 || (!ios && !prompt)) return null;
  const close = () => {
    setDismissed(true);
    try {
      window.localStorage.setItem(KEY, "1");
    } catch {
      /* see above */
    }
  };
  return (
    <div className="ls-install" role="status">
      <p>
        {copy.install.lead} {ios && copy.install.ios}
      </p>
      {prompt && (
        <button type="button" className="ls-btn ls-accent" onClick={() => (prompt.prompt(), close())}>
          {copy.install.android}
        </button>
      )}
      <button type="button" className="ls-btn ls-ghost" onClick={close}>
        {copy.install.dismiss}
      </button>
    </div>
  );
}
