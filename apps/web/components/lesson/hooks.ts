"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import type { Focus } from "../Stage3D";
import {
  projectBoxToFrame,
  containFit,
  cropTransform,
  sourceAspect,
  followStep,
  damp,
  sampleIndexAt,
  FOLLOW,
  type MotionResult,
  type Rect,
  type Vec3,
} from "../../lib/motion";
import { dancerBox, stillCrop } from "../../lib/dancers";
import { countAtTime, type CountGrid } from "../../../../packages/navigation/src/core";
import { clicksAhead, type ClickMode } from "../../lib/metronome";
import { audioContext, clockEvents, clockRef } from "./audioClock";

/**
 * The video is the clock. `requestVideoFrameCallback` hands back the exact
 * `mediaTime` of the frame the compositor is about to show, which is the only value
 * that stays locked to the picture through playbackRate changes, seeks and dropped
 * frames — a wall-clock timer drifts within seconds. 95%+ of browsers, Safari 15.4+.
 *
 * A rAF watchdog covers the rest: browsers without rVFC, and a video that is playing
 * but not being composited (the 3D view hides it), where rVFC stops firing. It
 * publishes `currentTime` only when rVFC has been silent for a while, so the two
 * never fight over the same frame.
 *
 * The loop is applied HERE, inside the one clock, not on `timeupdate` (~4 Hz, so a
 * loop could overshoot by a quarter second — audible on an 8-count). `onWrap` fires
 * once per wrap, and is what advances the lesson's rounds: the build-up ramp and the
 * "your turn" gap live on this clock, not on a timer of their own.
 */
/**
 * `?meshLead=<ms>`: draw the mesh at the video time this many ms after the frame
 * renders, to line it up with the video on a device that shows the WebGL canvas
 * later than the `<video>`. Off by default (the exact rVFC `mediaTime`), because
 * the one place it was measured needs none: iOS 26.5 Simulator Safari, a frame code
 * burned into the video and a time code drawn into the canvas, ~970 frames per run
 * (2026-10-21): no lead +4 ms (mesh behind), 33 ms lead -33 ms, 66 ms lead -62 ms.
 * The learner's iPhone still showed the mesh a tick behind, which the Simulator
 * (Mac GPU, no hardware video plane) cannot reproduce: tune it there, then bake it in.
 */
function meshLatencyMs(): number | null {
  if (typeof window === "undefined") return null;
  const knob = new URLSearchParams(window.location.search).get("meshLead");
  return knob !== null && Number.isFinite(Number(knob)) ? Number(knob) : null;
}

/** The video time on screen at `displayAt` (ms, performance.now() clock), carried
 * forward from the last rVFC frame. Clamped to 0.1 s: a stalled video must not run
 * the mesh off on its own. */
export function meshTimeAt(anchor: { media: number; at: number }, displayAt: number, rate: number): number {
  const ahead = ((displayAt - anchor.at) / 1000) * rate;
  return anchor.media + Math.min(Math.max(ahead, 0), 0.1);
}

export function useVideoClock(
  video: HTMLVideoElement | null,
  loopRef: React.RefObject<[number, number] | null>,
  onWrapRef: React.RefObject<(() => void) | null>,
) {
  const timeRef = useRef(0);
  const [displayTime, setDisplayTime] = useState(0);
  // The video time on screen when the mesh drawn now gets there: the last rVFC
  // frame, carried forward at the playback rate. Only the 3D view reads it; counts,
  // loops and crops stay on `timeRef`. Paused, seeking or without rVFC: `timeRef`.
  const anchor = useRef<{ media: number; at: number; video: HTMLVideoElement } | null>(null);
  const [meshTimeRef] = useState(() => {
    const lead = meshLatencyMs();
    return {
      get current() {
        const a = anchor.current;
        if (lead === null || !a || a.video.paused || a.video.seeking) return timeRef.current;
        return meshTimeAt(a, performance.now() + lead, a.video.playbackRate);
      },
    };
  });

  useEffect(() => {
    if (!video) return;
    let cancelled = false;
    let rvfcHandle = 0;
    let rafHandle = 0;
    let lastPublished = -1;
    let lastFrameAt = 0;

    const publish = (t: number) => {
      const loop = loopRef.current;
      // Only the trailing edge: running into the loop from before it is harmless,
      // and snapping a deliberate seek outside it would look broken.
      if (loop && t >= loop[1] && !video.paused) {
        // Set, not stepped, so no arithmetic accumulates over forty minutes of loops.
        video.currentTime = loop[0];
        anchor.current = null;
        t = loop[0];
        timeRef.current = t;
        onWrapRef.current?.();
      }
      timeRef.current = t;
      if (Math.abs(t - lastPublished) > 0.1) {
        lastPublished = t;
        setDisplayTime(t);
      }
    };

    const hasRvfc = typeof (video as any).requestVideoFrameCallback === "function";
    const step = (now: number, meta: { mediaTime: number; expectedDisplayTime?: number }) => {
      if (cancelled) return;
      lastFrameAt = performance.now();
      anchor.current = { media: meta.mediaTime, at: meta.expectedDisplayTime ?? now, video };
      publish(meta.mediaTime);
      rvfcHandle = (video as any).requestVideoFrameCallback(step);
    };
    if (hasRvfc) rvfcHandle = (video as any).requestVideoFrameCallback(step);
    const tick = () => {
      if (cancelled) return;
      rafHandle = requestAnimationFrame(tick);
      if (!video.paused && performance.now() - lastFrameAt > 150) publish(video.currentTime);
    };
    rafHandle = requestAnimationFrame(tick);

    // rVFC does not fire while paused, so a scrub with the video stopped would leave
    // the body on the old pose without this.
    const onSeek = () => {
      anchor.current = null;
      publish(video.currentTime);
    };
    video.addEventListener("seeked", onSeek);
    video.addEventListener("loadedmetadata", onSeek);

    return () => {
      cancelled = true;
      anchor.current = null;
      if (hasRvfc && rvfcHandle) (video as any).cancelVideoFrameCallback(rvfcHandle);
      cancelAnimationFrame(rafHandle);
      video.removeEventListener("seeked", onSeek);
      video.removeEventListener("loadedmetadata", onSeek);
    };
  }, [video, loopRef, onWrapRef]);

  return { timeRef, meshTimeRef, displayTime };
}

/**
 * The count under the playhead, re-rendering only when it changes — the count
 * numerals must turn over on the beat, not on a 10 Hz display tick. +40 ms because a
 * seek to a count boundary lands a hair early on some decoders.
 */
export function useCount(timeRef: React.RefObject<number>, grid: CountGrid, step = 1): number {
  const at = () => Math.floor(countAtTime(grid, timeRef.current + 0.04) / step) * step;
  const [count, setCount] = useState(at);
  useEffect(() => {
    let h = 0;
    const tick = () => {
      h = requestAnimationFrame(tick);
      const c = at();
      setCount((prev) => (prev === c ? prev : c));
    };
    h = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(h);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `at` is over these
  }, [timeRef, grid, step]);
  return count;
}

// ------------------------------------------------------------------ the click

let audio: { ctx: AudioContext; out: GainNode } | null = null;

/**
 * The page's one AudioContext, made or resumed — call it from inside a tap: iOS (and
 * Chrome's autoplay policy) only let audio start from a user gesture.
 */
export function unlockAudio() {
  const ctx = audioContext();
  if (!ctx) return null;
  if (!audio) {
    const out = ctx.createGain();
    out.connect(ctx.destination);
    audio = { ctx, out };
  }
  if (ctx.state !== "running") void ctx.resume().catch(() => {});
  return audio;
}

/**
 * How early to book a click so it sounds with the music. The click plays on Web Audio
 * and the music from the `<video>`: two output paths with different delays, and
 * Safari reports Web Audio's as 0, so it can't be read, only measured: by ear-free
 * microphone timing on /dev/click-probe (the music's blips vs a click booked with no
 * lead). The video is NOT routed through Web Audio to share one path: on a real
 * iPhone a routed video went choppy at any speed but 1×, and stayed routed (and
 * choppy) after the click was turned off (PR #64, reverted 2026-10-21).
 * `?clickLead=<ms>` overrides.
 * ponytail: per-engine constants from the probe; re-measure on a device that disagrees.
 */
function clickLeadS(): number {
  const knob = new URLSearchParams(window.location.search).get("clickLead");
  if (knob !== null && Number.isFinite(Number(knob))) return Number(knob) / 1000;
  const ua = navigator.userAgent;
  // iPhone Safari, measured 2026-10-22: the click already sounds 102 ms BEFORE the
  // music with no lead, so it is booked later, not earlier. Other WebKit keeps the
  // 115 ms interim. Per-platform guesses; the real fix is one audio clock, see the PR description of this change.
  if (/iPhone|iPad/.test(ua)) return -0.1;
  return /AppleWebKit/.test(ua) && !/Chrome|Chromium|Edg/.test(ua) ? 0.115 : 0;
}

/** How far ahead clicks are booked, in wall seconds. Short, so a pause or seek cuts in fast. */
const LOOKAHEAD_S = 0.12;
const TICK_MS = 25;

/**
 * A click on the lesson's counts, locked to the video clock. Every 25 ms it reads the
 * video's own time and rate and books the clicks of the next ~120 ms on the
 * AudioContext's clock (`clicksAhead`), so speed, pauses, seeks and loop wraps are
 * followed within one tick and nothing accumulates: each booking is re-derived from
 * `video.currentTime`, never from the last click. A seek, pause or rate change drops
 * the clicks not yet sounded; the loop wrap is a seek, so the loop's first click is
 * booked from where the video really restarted.
 *
 * `window.__metronomeLog`, when a test sets it to an array, gets every booked click.
 */
export function useMetronome(
  video: HTMLVideoElement | null,
  loopRef: React.RefObject<[number, number] | null>,
  grid: CountGrid,
  on: boolean,
  mode: ClickMode,
  volume: number,
) {
  useEffect(() => {
    // Squared: the slider feels even to the ear.
    if (audio) audio.out.gain.value = volume * volume;
  }, [volume, on]);

  useEffect(() => {
    if (!video || !on) return;
    const a = unlockAudio();
    if (!a) return;
    const { ctx, out } = a;
    out.gain.value = volume * volume;
    const videoLead = clickLeadS();
    let booked: { when: number; node: GainNode }[] = [];
    let last = -Infinity;

    const blip = (when: number, label: number) => {
      const osc = ctx.createOscillator();
      const env = ctx.createGain();
      // The 1 highest, the "and" lowest and softer: heard apart without looking.
      osc.frequency.value = label === 1 ? 1760 : label === 0 ? 880 : 1320;
      const peak = label === 0 ? 0.45 : 1;
      env.gain.setValueAtTime(0, when);
      env.gain.linearRampToValueAtTime(peak, when + 0.002);
      env.gain.exponentialRampToValueAtTime(0.001, when + 0.045);
      osc.connect(env).connect(out);
      osc.start(when);
      osc.stop(when + 0.05);
      booked.push({ when, node: env });
    };

    /** Drop what has not sounded yet; what already started stays, so it is not doubled. */
    const drop = () => {
      const now = ctx.currentTime;
      booked = booked.filter((b) => {
        if (b.when > now + 0.003) {
          b.node.disconnect();
          return false;
        }
        return true;
      });
      last = booked.reduce((m, b) => Math.max(m, b.when), -Infinity);
    };

    const tick = () => {
      if (ctx.state !== "running") return;
      const now = ctx.currentTime;
      // With the music on the audio clock, clicks are booked on the same mapping:
      // exact by construction, no lead. Otherwise from the video, with the lead.
      const clock = clockRef.current?.engaged ? clockRef.current : null;
      if (!clock && (video.paused || video.seeking)) return;
      const rate = clock ? clock.rate : video.playbackRate;
      const t = clock ? clock.mediaAt(now) : video.currentTime;
      const lead = clock ? 0 : videoLead;
      const gap = (0.4 * (mode === "ands" ? 0.5 : 1) * grid.secondsPerCount) / rate;
      for (const c of clicksAhead({ grid, loop: loopRef.current, t, rate, lookahead: LOOKAHEAD_S + Math.max(lead, 0), mode })) {
        const when = now + c.in - lead;
        if (when < now) continue; // too late to sound on time
        if (when < last + gap) continue; // already booked on an earlier tick
        blip(when, c.label);
        last = when;
        // `perf`: when it sounds on the page's performance.now() clock, to check against the video.
        (window as any).__metronomeLog?.push({ when, at: c.at, label: c.label, rate, perf: performance.now() + c.in * 1000 });
      }
      booked = booked.filter((b) => b.when > now - 1);
    };

    const id = window.setInterval(tick, TICK_MS);
    const onSeeked = () => (drop(), tick());
    // With the music on the audio clock, only the clock's own changes move the clicks:
    // the video's events include the clock's easing (playbackRate) and catch-up seeks.
    const fromVideo = (f: () => void) => () => { if (!clockRef.current?.engaged) f(); };
    const videoDrop = fromVideo(drop);
    const videoSeeked = fromVideo(onSeeked);
    const events = ["seeking", "pause", "ratechange"] as const;
    events.forEach((e) => video.addEventListener(e, videoDrop));
    video.addEventListener("seeked", videoSeeked);
    video.addEventListener("playing", tick);
    clockEvents?.addEventListener("change", onSeeked);
    return () => {
      clockEvents?.removeEventListener("change", onSeeked);
      clearInterval(id);
      events.forEach((e) => video.removeEventListener(e, videoDrop));
      video.removeEventListener("seeked", videoSeeked);
      video.removeEventListener("playing", tick);
      last = -Infinity;
      drop();
    };
    // `volume` is applied by the effect above without rebooking.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [video, loopRef, grid, on, mode]);
}

export function useMedia(query: string): boolean {
  return useSyncExternalStore(
    (cb) => {
      const m = window.matchMedia(query);
      m.addEventListener("change", cb);
      return () => m.removeEventListener("change", cb);
    },
    () => window.matchMedia(query).matches,
    () => false,
  );
}

/** Phone layout: narrow, or a phone on its side. Same URL, different composition. */
export const PHONE_QUERY = "(max-width: 767px), (max-height: 520px)";

/**
 * Crop-follow for the video pane, so a dancer who travels stays framed.
 *
 * Framed from the SAME number the 3D frames when a 3D pane is mounted
 * (`focusRef.body`, projected through the clip's camera), else from the contract's
 * own joints through that camera (`dancerBox`) — never a second tracker. Damped in
 * frame space with the 3D rig's tuning, so the two panes lag identically.
 *
 * Runs on its own rAF loop, writes `style.transform` directly, and only touches React
 * state when a boolean flips.
 */
export function useVideoCrop(
  video: HTMLVideoElement | null,
  doc: MotionResult,
  focusRef: React.RefObject<Focus | null>,
  timeRef: React.RefObject<number>,
  personIndex: number,
  follow: boolean,
  mirrored: boolean,
) {
  const [status, setStatus] = useState({ cropped: false, clipped: false });

  useEffect(() => {
    if (!video) return;
    const mirror = mirrored ? "scaleX(-1) " : "";
    if (!follow) {
      video.style.transform = mirrored ? "scaleX(-1)" : "";
      setStatus({ cropped: false, clipped: false });
      return;
    }

    let handle = 0;
    let last = performance.now();
    let centre: Vec3 | null = null;
    let height = 0;
    let reported = { cropped: false, clipped: false };

    const tick = (now: number) => {
      handle = requestAnimationFrame(tick);
      const dt = Math.min((now - last) / 1000, 0.1);
      last = now;
      const focus = focusRef.current;
      const raw: Rect | null = focus
        ? projectBoxToFrame(
            doc,
            [focus.body.min.x, focus.body.min.y, focus.body.min.z],
            [focus.body.max.x, focus.body.max.y, focus.body.max.z],
          )
        : dancerBox(doc, personIndex, sampleIndexAt(doc.sample_times_s, timeRef.current));
      // Behind the camera plane, or no bounds yet: hold the last good crop rather
      // than snap to centre. A jump is a worse lie than a stale frame.
      if (!raw || raw.height <= 0) return;

      const target: Vec3 = [raw.x + raw.width / 2, raw.y + raw.height / 2, 0];
      if (!centre) {
        centre = target;
        height = raw.height;
      } else {
        centre = followStep(centre, target, FOLLOW.deadzoneFraction * raw.height, dt);
        height = damp(height, raw.height, FOLLOW.tauDistance, dt);
      }

      // `object-fit: contain` letterboxes the frame inside the element, and
      // cropTransform works in element fractions with that letterbox in it.
      const fit = containFit(sourceAspect(doc), video.clientWidth, video.clientHeight);
      const win = cropTransform({ x: centre[0] - raw.width / 2, y: centre[1] - height / 2, width: raw.width, height }, fit);
      video.style.transform = `${mirror}translate(${(win.tx * 100).toFixed(3)}%, ${(win.ty * 100).toFixed(3)}%) scale(${win.zoom.toFixed(4)})`;

      const next = {
        cropped: win.zoom > 1.05,
        clipped: raw.x < 0 || raw.y < 0 || raw.x + raw.width > 1 || raw.y + raw.height > 1,
      };
      if (next.cropped !== reported.cropped || next.clipped !== reported.clipped) {
        reported = next;
        setStatus(next);
      }
    };
    handle = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(handle);
      video.style.transform = mirrored ? "scaleX(-1)" : "";
    };
  }, [video, doc, focusRef, timeRef, personIndex, follow, mirrored]);

  return status;
}

/**
 * Screen Wake Lock while `on`, re-taken when the tab comes back (the OS drops it on
 * hide). Silently does nothing where unsupported — the lesson still works.
 */
export function useWakeLock(on: boolean) {
  useEffect(() => {
    if (!on) return;
    let lock: { release: () => Promise<void> } | null = null;
    let live = true;
    const take = async () => {
      try {
        lock = await (navigator as any).wakeLock?.request("screen");
        if (!live) await lock?.release();
      } catch {
        /* low battery, unsupported, not visible: carry on without it */
      }
    };
    const onVis = () => document.visibilityState === "visible" && take();
    void take();
    document.addEventListener("visibilitychange", onVis);
    return () => {
      live = false;
      document.removeEventListener("visibilitychange", onVis);
      void lock?.release().catch(() => {});
    };
  }, [on]);
}

/**
 * Stills from THIS clip, for the dancer picker: one frame per request, cropped to
 * `stillCrop(box)`, as a JPEG data URL. A second, muted, never-shown `<video>` on the
 * same URL does the seeking, so the lesson's own clock is never touched. Requests run
 * one at a time.
 *
 * `crossOrigin = "anonymous"` is set BEFORE `src`, and it is load-bearing: a job's
 * video URL redirects to a presigned R2 URL on another origin, and without a CORS
 * request that frame taints the canvas, so `toDataURL` throws and every still came
 * back empty — a black card in production (job_b0d0bb64…). With it, R2's ACAO:*
 * keeps the canvas readable.
 *
 * Each entry is `undefined` while pending, a data URL once captured, and `null` when
 * it cannot be (load error, CORS refused, a seek that never lands, a tainted
 * canvas) — the picker then shows the live video paused there instead.
 */
export function useFrameGrabs(
  videoUrl: string,
  requests: { t: number; box: Rect | null }[],
  enabled: boolean,
): (string | null | undefined)[] {
  const [urls, setUrls] = useState<(string | null | undefined)[]>(() => requests.map(() => undefined));
  const key = JSON.stringify(requests);
  useEffect(() => {
    if (!enabled || !requests.length) return;
    let cancelled = false;
    const v = document.createElement("video");
    v.crossOrigin = "anonymous";
    v.muted = true;
    v.playsInline = true;
    v.preload = "auto";
    v.src = videoUrl;
    const set = (i: number, url: string | null) => setUrls((prev) => prev.map((u, k) => (k === i ? url : u)));
    const failAll = () => setUrls((prev) => prev.map((u) => (u === undefined ? null : u)));
    const waitFor = (ev: string, ms: number) =>
      new Promise<boolean>((resolve) => {
        const t = window.setTimeout(() => resolve(false), ms);
        v.addEventListener(ev, () => (clearTimeout(t), resolve(true)), { once: true });
        v.addEventListener("error", () => (clearTimeout(t), resolve(false)), { once: true });
      });
    (async () => {
      if (v.readyState < 2 && !(await waitFor("loadeddata", 15000))) return void (cancelled || failAll());
      for (let i = 0; i < requests.length && !cancelled; i++) {
        const { t, box } = requests[i];
        const seeked = waitFor("seeked", 6000);
        v.currentTime = Math.max(0.001, t);
        if (!(await seeked) || cancelled || v.readyState < 2) {
          if (!cancelled) set(i, null);
          continue;
        }
        const vw = v.videoWidth, vh = v.videoHeight;
        if (!vw || !vh) {
          set(i, null);
          continue;
        }
        const r = stillCrop(box, vw, vh);
        const c = document.createElement("canvas");
        c.width = 240;
        c.height = 320;
        let url: string | null = null;
        try {
          c.getContext("2d")?.drawImage(v, r.x * vw, r.y * vh, r.width * vw, r.height * vh, 0, 0, 240, 320);
          url = c.toDataURL("image/jpeg", 0.8);
        } catch {
          url = null; // tainted after all: fall back to the live video
        }
        set(i, url);
      }
      v.removeAttribute("src");
      v.load();
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `key` is `requests`
  }, [videoUrl, key, enabled]);
  return urls;
}
