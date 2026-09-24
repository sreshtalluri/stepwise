"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { Lesson, MainView } from "../LessonViewer";
import { lesson as copy } from "../../lib/copy";
import type { ViewId } from "../../lib/motion";
import { spanLabel } from "../../lib/lessonEngine";
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
  WhoChip,
  type IconName,
} from "./pieces";
import { useMedia, useWakeLock } from "./hooks";

const NEXT_VIEW: Record<MainView, MainView> = { overlay: "video", video: "3d", "3d": "overlay" };
const VIEW_ICON: Record<MainView, IconName> = { video: "video", "3d": "cube", overlay: "stack" };
const VIEW_NAME: Record<MainView, string> = { video: copy.views.video, "3d": copy.views.threeD, overlay: copy.views.overlay };
/** Build up reaches 1× on its sixth pass; one more pass at 1× and prop mode moves on. */
const PASSES_TO_FULL_AND_ONCE_MORE = 6;

/**
 * The phone lesson (docs/DESIGN.md §6, mockups/phone): the page never scrolls. The clip
 * is full-bleed and the stage takes TikTok's gestures — tap to play, swipe up or down
 * for the next or previous counts (by the loop length), hold for half speed. The
 * bottom sheet holds the chips, the loop length and the transport; More opens it the rest of the way. On its side it
 * is video and 3D side by side. "Prop it up" drops all chrome for a phone leaning on
 * the wall across the room.
 */
export default function PhoneLesson({ l }: { l: Lesson }) {
  const land = useMedia("(orientation: landscape)");
  const shots = useDancerShots(l);
  const [open, setOpen] = useState(false);
  const [prop, setProp] = useState(false);
  const [voice, setVoice] = useState(true);
  const [auto, setAuto] = useState(true);
  const [inset, setInset] = useState<ViewId | null>(null);
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
    setOpen(false);
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

  const loopLabel = l.loop ? (l.loopEight?.label ?? spanLabel(l.loop)) : copy.chips.all;

  return (
    <main
      className={`ls ls-phone${land ? " ls-land" : ""}${prop ? " ls-prop" : ""}${open ? " ls-open" : ""}`}
      style={{ ["--accent" as string]: accentOf(l) }}
    >
      <div className="ls-ph-stages" onPointerDown={onDown} onPointerUp={onUp} onPointerCancel={onCancel}>
        <MainStage l={l} className="ls-ph-stage" view={land && l.view === "3d" ? "overlay" : l.view}>
          <header className="ls-ph-head">
            <Link href="/" className="ls-icon-btn" aria-label={copy.transport.back}>
              <Icon name="left" />
            </Link>
            <h1 className="ls-title">{l.title}</h1>
            <span className="ls-meter">{doneLine(l)}</span>
          </header>
          <CloseUps l={l} className="ls-ph-closeups" />
          <nav className="ls-rail" aria-label={copy.views.group}>
            <RailButton icon={VIEW_ICON[l.view]} label={VIEW_NAME[l.view]} onClick={() => l.setView(NEXT_VIEW[l.view])} />
            <RailButton
              icon="mirror"
              label={l.mirrored ? copy.transport.mirrorOn : copy.transport.mirrorOff}
              on={l.mirrored}
              onClick={() => l.setMirrored((v) => !v)}
            />
            <RailButton icon="hand" label={copy.views.closeups} on={l.showCrops} onClick={() => l.setShowCrops((v) => !v)} />
            {l.multi && (
              <div className="ls-rail-item">
                <WhoChip l={l} shots={shots} withName={false} />
                <span>{copy.dancers.name(l.selected + 1)}</span>
              </div>
            )}
          </nav>
          <div className="ls-ph-counts">
            <span className="ls-ph-unit">{loopLabel}</span>
            <CountBar l={l} big={prop} />
          </div>
          {inset && !land && (
            <div className="ls-inset">
              <AnglePane l={l} angle={inset} compact onRemove={() => setInset(null)} />
            </div>
          )}
          {hint && !prop && <p className="ls-ph-hint">{copy.phone.hint}</p>}
          {l.next && !prop && (
            <button type="button" className="ls-next ls-ph-next" onClick={() => l.setLoop(l.next, { play: l.playing })}>
              {copy.chips.next(spanLabel(l.next))}
              <Icon name="right" size={16} />
            </button>
          )}
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
        </MainStage>
        {land && <AnglePane l={l} angle={l.view === "3d" ? l.angle : "front"} onAngle={l.setAngle} focus />}
      </div>

      <section className="ls-sheet" aria-label={copy.chips.group}>
        <EightChips l={l} />
        <Transport
          l={l}
          className="ls-ph-transport"
          more={
            <button type="button" className="ls-more-btn" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
              <Icon name={open ? "x" : "dots"} size={22} />
              <span>{open ? copy.phone.less : copy.transport.more}</span>
            </button>
          }
        />
        {(open || land) && (
          <MoreContent
            l={l}
            extra={
              <div className="ls-group">
                <div className="ls-group-row">
                  <button type="button" className="ls-chip ls-strong ls-accent" onClick={enterProp}>
                    {copy.phone.prop}
                  </button>
                </div>
                {!land && (
                  <>
                    <span className="ls-group-label">{copy.views.inset}</span>
                    <div className="ls-group-row">
                      <button type="button" className="ls-chip" aria-pressed={!inset} onClick={() => setInset(null)}>
                        {copy.views.insetOff}
                      </button>
                      {(["front", "side", "back", "top"] as ViewId[]).map((a) => (
                        <button key={a} type="button" className="ls-chip" aria-pressed={inset === a} onClick={() => setInset(a)}>
                          {a[0].toUpperCase() + a.slice(1)}
                          <small>{copy.views.est}</small>
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </div>
            }
          />
        )}
      </section>

      <InstallHint done={l.done.size} />
      <DancerPicker l={l} shots={shots} />
    </main>
  );
}

function RailButton({ icon, label, on, onClick }: { icon: IconName; label: string; on?: boolean; onClick: () => void }) {
  return (
    <button type="button" className={`ls-rail-item${on ? " ls-on" : ""}`} onClick={onClick} aria-pressed={on}>
      <span className="ls-rail-dot">
        <Icon name={icon} size={24} />
      </span>
      <span>{label}</span>
    </button>
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
