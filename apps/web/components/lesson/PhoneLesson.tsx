"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
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
  DancerPicker,
  Help,
  Icon,
  learnedLine,
  MainStage,
  PlayButton,
  Steps,
  useDancerShots,
  WhoChip,
  type IconName,
} from "./pieces";
import { useMedia, useWakeLock } from "./hooks";

const NEXT_VIEW: Record<MainView, MainView> = { video: "3d", "3d": "overlay", overlay: "video" };
const VIEW_ICON: Record<MainView, IconName> = { video: "video", "3d": "cube", overlay: "stack" };
const VIEW_NAME: Record<MainView, string> = { video: copy.views.video, "3d": copy.views.threeD, overlay: copy.views.overlay };

/**
 * The phone lesson (docs/DESIGN.md §6, mockups/phone): the page never scrolls. The clip
 * is full-bleed, everything you press sits in a bottom sheet in the thumb zone, and the
 * stage itself takes TikTok's gestures — tap to play, swipe up or down for the next or
 * previous 8-count, hold for half speed. On its side it is video and 3D side by side.
 * "Prop it up" drops all chrome for a phone leaning on the wall across the room.
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
  const countInThen = (go: () => void) => {
    cancelCountIn();
    const v = l.video;
    if (!v) return;
    if (!voice) return go();
    v.play().catch(() => {});
    v.pause();
    const beat = (l.structure.grid.secondsPerCount / l.speed) * 1000;
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

  // ---- prop it up: build-up runs on its own and moves on to the next 8.
  const enterProp = () => {
    setProp(true);
    setOpen(false);
    document.documentElement.requestFullscreen?.().catch(() => {}); // Android; iOS only as a home-screen app
    l.setMode("lesson");
    l.goUnit(l.unitIndex, { play: false, step: "build" });
    countInThen(l.play);
  };
  const exitProp = () => {
    cancelCountIn();
    setProp(false);
    l.pause();
    if (document.fullscreenElement) void document.exitFullscreen().catch(() => {});
  };
  useEffect(() => {
    if (!prop || !auto || !l.checkIn) return;
    const last = l.eights[l.eights.length - 1];
    if (l.unit.id === last?.id) return;
    const t = window.setTimeout(() => {
      l.stepEight(1, { play: false, step: "build" });
      show(copy.phone.zoneNext);
    }, 900);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fires on the check-in edge only
  }, [prop, auto, l.checkIn]);
  // ...and once the next 8 is open, count it in.
  const lastUnit = useRef(l.unitIndex);
  useEffect(() => {
    if (prop && lastUnit.current !== l.unitIndex && l.video?.paused) countInThen(l.play);
    lastUnit.current = l.unitIndex;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- unit change edge
  }, [l.unitIndex]);

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
      l.stepEight(dy < 0 ? 1 : -1);
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

  const eightIndex = l.eights.findIndex((u) => u.startCount <= l.unit.startCount && l.unit.startCount <= u.endCount);
  const learnedN = l.eights.filter((u) => l.learned.has(u.id)).length;
  const building = l.mode === "lesson" && l.current.step === "build" && !l.complete;

  return (
    <main
      className={`ls ls-phone${land ? " ls-land" : ""}${prop ? " ls-prop" : ""}${open ? " ls-open" : ""}`}
      style={{ ["--accent" as string]: accentOf(l) }}
    >
      <div className="ls-ph-stages" onPointerDown={onDown} onPointerUp={onUp} onPointerCancel={onCancel}>
        <MainStage l={l} className="ls-ph-stage" view={land && l.view === "3d" ? "overlay" : l.view}>
          <div className="ls-bars" role="group" aria-label={copy.path.label}>
            {l.eights.map((u, i) => (
              <button
                key={u.id}
                type="button"
                className={l.learned.has(u.id) ? "ls-done" : i === eightIndex ? "ls-here" : ""}
                aria-label={u.label}
                aria-current={i === eightIndex ? "step" : undefined}
                onClick={() => l.goUnit(l.units.indexOf(u), { play: false })}
              />
            ))}
          </div>
          <header className="ls-ph-head">
            <Link href="/" className="ls-icon-btn" aria-label={copy.transport.back}>
              <Icon name="left" />
            </Link>
            <h1 className="ls-title">{l.title}</h1>
            <span className="ls-meter">{learnedLine(l)}</span>
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
            <span className="ls-ph-unit">{l.unit.label}</span>
            <CountBar l={l} big={prop} />
          </div>
          {inset && !land && (
            <div className="ls-inset">
              <AnglePane l={l} angle={inset} compact onRemove={() => setInset(null)} />
            </div>
          )}
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
                  {l.speed}×<small>{building ? copy.transport.building : l.unit.label}</small>
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
                <button
                  type="button"
                  aria-label={copy.phone.zoneBack}
                  onClick={() => l.stepEight(-1, { play: false, step: "build" })}
                />
                <button
                  type="button"
                  aria-label={l.playing ? copy.transport.pause : copy.transport.play}
                  onClick={() => (l.playing || countIn !== null ? (cancelCountIn(), l.pause()) : countInThen(l.play))}
                />
                <button type="button" aria-label={copy.phone.zoneNext} onClick={() => l.stepEight(1, { play: false, step: "build" })} />
              </div>
            </>
          )}
        </MainStage>
        {land && (
          <AnglePane l={l} angle={l.view === "3d" ? l.angle : l.angle === "camera" ? "front" : l.angle} onAngle={l.setAngle} focus />
        )}
      </div>

      <section className="ls-sheet" aria-label={copy.path.stepGroup}>
        <button type="button" className="ls-grab" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
          <span className="sr-only">{open ? copy.phone.less : copy.phone.more}</span>
        </button>
        <Steps l={l} compact />
        <div className="ls-ph-transport">
          <button type="button" className="ls-big-btn" onClick={() => l.stepEight(-1)} aria-label={copy.transport.prev}>
            <Icon name="up" size={28} />
          </button>
          <PlayButton l={l} className="ls-ph-play" short />
          <button type="button" className="ls-big-btn" onClick={() => l.stepEight(1)} aria-label={copy.transport.next}>
            <Icon name="down" size={28} />
          </button>
        </div>
        <div className="ls-ph-row">
          <button type="button" className="ls-tile" onClick={l.cycleFreeSpeed}>
            {l.speed}×<small>{building ? copy.transport.building : copy.transport.speed}</small>
          </button>
          <button type="button" className="ls-tile" onClick={l.tapOne} title={copy.countOne.tapHint}>
            {copy.countOne.tap}
            <small>{l.countsFrom !== "hand" ? copy.countOne.guess.toLowerCase() : copy.countOne.heading.toLowerCase()}</small>
          </button>
          <button type="button" className="ls-tile ls-accent" onClick={enterProp}>
            {copy.phone.prop}
            <small>{copy.phone.propSub}</small>
          </button>
        </div>

        <div className="ls-more" hidden={!open && !land}>
          <SheetGroup label={copy.countOne.heading}>
            <button type="button" className="ls-chip" onClick={() => l.nudgeOne(-1)} aria-label={copy.countOne.earlierLabel}>
              {copy.countOne.earlier}
            </button>
            <button type="button" className="ls-chip" onClick={l.tapOne}>
              {copy.countOne.tap}
            </button>
            <button type="button" className="ls-chip" onClick={() => l.nudgeOne(1)} aria-label={copy.countOne.laterLabel}>
              {copy.countOne.later}
            </button>
          </SheetGroup>
          <SheetGroup label={copy.modes.group}>
            <button type="button" className="ls-chip" aria-pressed={l.mode === "lesson"} onClick={() => l.setMode("lesson")}>
              {copy.modes.lesson}
            </button>
            <button type="button" className="ls-chip" aria-pressed={l.mode === "free"} onClick={l.toFree}>
              {copy.modes.practise}
            </button>
          </SheetGroup>
          {l.mode === "free" && (
            <>
              <SheetGroup label={copy.transport.speedLabel}>
                {SPEEDS.map((s) => (
                  <button key={s} type="button" className="ls-chip" aria-pressed={l.freeSpeed === s} onClick={() => l.setFreeSpeed(s)}>
                    {s}×
                  </button>
                ))}
              </SheetGroup>
              <SheetGroup label={copy.transport.loopOn}>
                <button type="button" className="ls-chip" aria-pressed={l.freeLoop === "unit"} onClick={() => l.setFreeLoop("unit")}>
                  {copy.transport.loopThis}
                </button>
                <button type="button" className="ls-chip" aria-pressed={l.freeLoop === "all"} onClick={() => l.setFreeLoop("all")}>
                  {copy.transport.wholeDance}
                </button>
              </SheetGroup>
            </>
          )}
          <SheetGroup label={copy.views.angle}>
            {ANGLES.map((a) => (
              <button
                key={a.id}
                type="button"
                className="ls-chip"
                aria-pressed={l.view === "3d" && l.angle === a.id}
                onClick={() => {
                  l.setAngle(a.id);
                  if (!land) l.setView("3d");
                }}
              >
                {cap(a.label)}
                {a.id !== "camera" && <small>est.</small>}
              </button>
            ))}
          </SheetGroup>
          {!land && (
            <SheetGroup label={copy.views.inset}>
              <button type="button" className="ls-chip" aria-pressed={!inset} onClick={() => setInset(null)}>
                {copy.views.insetOff}
              </button>
              {(["side", "front", "back", "top"] as ViewId[]).map((a) => (
                <button key={a} type="button" className="ls-chip" aria-pressed={inset === a} onClick={() => setInset(a)}>
                  {cap(a)}
                  <small>est.</small>
                </button>
              ))}
            </SheetGroup>
          )}
          <SheetGroup label={copy.views.group}>
            <button type="button" className="ls-chip" aria-pressed={l.follow} onClick={() => l.setFollow((v) => !v)}>
              {l.follow ? copy.transport.followOn : copy.transport.followOff}
            </button>
            <Help l={l} id="ls-help-phone" />
          </SheetGroup>
        </div>
      </section>

      <CheckIn l={l} className="ls-ph-check" />
      <InstallHint learned={learnedN} />
      <DancerPicker l={l} shots={shots} />
    </main>
  );
}

const cap = (s: string) => s[0].toUpperCase() + s.slice(1);

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

function SheetGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="ls-group" role="group" aria-label={label}>
      <span className="ls-group-label">{label}</span>
      <div className="ls-group-row">{children}</div>
    </div>
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
 * Add to Home Screen, offered once the learner has learned one 8-count here — not on
 * the landing page, where nobody knows yet whether they want it. iOS has no install
 * prompt, so it gets the one-line how-to; Chromium gets its own prompt.
 */
function InstallHint({ learned }: { learned: number }) {
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
  if (dismissed || learned < 1 || (!ios && !prompt)) return null;
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
