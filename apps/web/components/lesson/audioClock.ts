"use client";

import { useEffect, useRef } from "react";

/**
 * One audio clock for the lesson: the music and the click both play through the
 * page's AudioContext, so whatever the device adds after it (speaker buffering,
 * Bluetooth, Safari's own path) delays both equally and they cannot drift apart.
 * No per-device calibration. Before this, the music came out of the `<video>` and
 * the click out of Web Audio, two paths whose offset depended on the device:
 * +170 ms on a MacBook, −102 ms on an iPhone (/dev/click-probe, 2026-10-22).
 *
 * The music is the lesson video's own audio, decoded once, played through Signalsmith
 * Stretch (MIT, WASM in an AudioWorklet, public/vendor/) so slower speeds keep their pitch. The
 * `<video>` stays the transport every control already drives (play, pause, seek, loop
 * wraps): this follows its events, and the video plays muted, nudged back onto the
 * audio clock whenever it drifts. Routing the `<video>` itself into Web Audio
 * (createMediaElementSource, #64) is NOT an option: on an iPhone it went choppy at any
 * speed but 1× and could not be undone (#66).
 *
 * Anything that fails (no Web Audio, decode refused, context not unlocked yet) leaves
 * the video playing its own sound, exactly as before.
 */

export interface AudioClock {
  ctx: AudioContext;
  /** Music is coming from here right now (else the video's own sound is). */
  engaged: boolean;
  rate: number;
  /** Media seconds the music plays at context time `at`. Valid while engaged. */
  mediaAt(at: number): number;
}

/** Fired on `clockEvents` whenever the time mapping changes (start, stop, seek, rate). */
export const clockEvents = typeof window === "undefined" ? null : new EventTarget();
/** The current lesson's clock, or null. One lesson plays at a time. */
export const clockRef: { current: AudioClock | null } = { current: null };

let shared: AudioContext | null = null;
/** The page's one AudioContext, made on first use; suspended until a tap resumes it. */
export function audioContext(): AudioContext | null {
  if (typeof window === "undefined") return null;
  if (!shared) {
    const Ctx = window.AudioContext ?? (window as any).webkitAudioContext;
    if (!Ctx) return null;
    shared = new Ctx() as AudioContext;
    // iOS: Web Audio is silenced by the ring/silent switch unless the page says it is
    // media playback, which a <video>'s sound always was (Safari 16.4+).
    const session = (navigator as any).audioSession;
    if (session) {
      try { session.type = "playback"; } catch { /* older Safari: no session API */ }
    }
  }
  return shared;
}

/** Decoded once per URL: a layout switch remounts the <video>, not the song. */
const decoded = new Map<string, Promise<Float32Array[]>>();
function decode(ctx: AudioContext, url: string): Promise<Float32Array[]> {
  let p = decoded.get(url);
  if (!p) {
    // ponytail: downloads the whole video a second time for its audio (3-9 MB). An
    // audio-only asset from the pipeline would halve that; add it if bandwidth shows.
    p = fetch(url)
      .then((r) => {
        if (!r.ok) throw new Error(`audio fetch ${r.status}`);
        return r.arrayBuffer();
      })
      .then((bytes) => new Promise<AudioBuffer>((ok, fail) => ctx.decodeAudioData(bytes, ok, fail)))
      .then((buf) => {
        const left = buf.getChannelData(0);
        return [left, buf.numberOfChannels > 1 ? buf.getChannelData(1) : left];
      });
    p.catch(() => decoded.delete(url));
    decoded.set(url, p);
  }
  return p;
}

/**
 * Context time of the sample reaching the speaker at `perfMs` (performance.now()
 * clock), where the browser says. Safari reports no output latency (0), so there
 * this is the context's own time: still one clock for music and click.
 */
function ctxTimeAt(ctx: AudioContext, perfMs: number): number {
  const ts = ctx.getOutputTimestamp?.();
  if (ts && ts.contextTime && ts.performanceTime) return ts.contextTime + (perfMs - ts.performanceTime) / 1000;
  return ctx.currentTime - (ctx.outputLatency || 0) + (perfMs - performance.now()) / 1000;
}

const STRETCH_SRC = "/vendor/signalsmith-stretch-1.3.2.mjs";

/**
 * Picture vs music, kept two ways. Chromium: measured (displayed frame vs the music
 * at that moment, -10..-5 ms in practice) and eased with a muted playbackRate nudge,
 * seeking only past SEEK_S. WebKit: the same measurement reads a steady -90..-150 ms
 * that seeks do not move (iOS 26.5 Simulator), and Safari ignores small rate nudges
 * (eased to 0.525x it played 0.4955x), so correcting on it only stuttered (15 seeks
 * in 20 s). There the music is aligned to the video at every play, seek and loop
 * wrap (`start`), and a seek happens only past WEBKIT_SEEK_S, i.e. after a stall.
 * The muted video runs a touch slow there (0.4937x at 0.5x): ~6 ms/s, reset at the
 * next loop wrap, up to ~0.2 s by the end of a long unlooped 0.5x play.
 * ponytail: WebKit gets no fine correction; revisit with an on-device measurement.
 */
const SEEK_S = 0.06;
const WEBKIT_SEEK_S = 0.4;
/** After a seek, before judging again: it takes a few frames to land. */
const SETTLE_MS = 1500;
/** Easing: at most ±5% speed, closing a gap over ~1 s. Invisible on a muted video. */
const EASE_MAX = 0.05;
const EASE_GAIN = 0.8;
/** Inside this the video simply runs at the learner's speed: below a frame at 60 Hz. */
const DEADBAND_S = 0.015;
/** Changes are booked this far ahead, so the stretcher can land them exactly. */
const AHEAD_S = 0.03;

/**
 * Attach the lesson's music to `video`. `speed` is the learner's speed (the video's
 * own playbackRate is not read: the drift correction must not feed back into it).
 */
export function useAudioClock(video: HTMLVideoElement | null, url: string, speed: number, volume: number) {
  const speedRef = useRef(speed);
  const gainRef = useRef<GainNode | null>(null);
  const restart = useRef<(() => void) | null>(null);

  useEffect(() => {
    const ctx = audioContext();
    if (!video || !ctx || !url) return;
    let cancelled = false;
    let stretch: any = null;
    let map = { output: 0, input: 0, rate: 1 };
    let selfSeek = false;
    let lastFix = 0;
    let raf = 0;
    const gain = ctx.createGain();
    gain.gain.value = volume; // linear, as video.volume was
    gain.connect(ctx.destination);
    gainRef.current = gain;

    const clock: AudioClock = {
      ctx,
      engaged: false,
      rate: speedRef.current,
      mediaAt: (at) => map.input + (at - map.output) * map.rate,
    };
    const changed = () => clockEvents?.dispatchEvent(new Event("change"));

    const start = () => {
      if (!stretch || cancelled) return;
      if (ctx.state !== "running") {
        // Not unlocked by a tap yet: the video's own sound carries this play.
        clock.engaged = false;
        video.muted = false;
        void ctx.resume().then(() => { if (!video.paused && !cancelled) start(); }).catch(() => {});
        changed();
        return;
      }
      const output = ctx.currentTime + AHEAD_S;
      map = { output, input: video.currentTime + AHEAD_S * speedRef.current, rate: speedRef.current };
      stretch.schedule({ active: true, output, input: map.input, rate: map.rate });
      clock.engaged = true;
      clock.rate = map.rate;
      video.muted = true;
      lastFix = performance.now();
      changed();
    };
    const stop = () => {
      if (!stretch) return;
      stretch.schedule({ active: false, output: ctx.currentTime });
      clock.engaged = false;
      changed();
    };
    restart.current = () => {
      if (!clock.engaged) return;
      const output = ctx.currentTime + AHEAD_S;
      map = { output, input: clock.mediaAt(output), rate: speedRef.current };
      stretch.schedule({ output, input: map.input, rate: map.rate });
      clock.rate = map.rate;
      changed();
    };

    const onPlay = () => start();
    const onPause = () => stop();
    const onSeeking = () => {
      if (selfSeek) return;
      if (!video.paused) start();
    };
    const onSeeked = () => {
      selfSeek = false;
    };

    // Keep the picture on the music: the mesh and the counts read the video's frames.
    // The frame on screen and when, from requestVideoFrameCallback: Safari's
    // `currentTime` trails the picture (~66 ms at 0.5x on iOS 26.5), so it is only the
    // fallback where rVFC is missing.
    let frame: { media: number; shown: number } | null = null;
    let vfc = 0;
    const onFrame = (_now: number, meta: { mediaTime: number; expectedDisplayTime: number }) => {
      frame = { media: meta.mediaTime, shown: meta.expectedDisplayTime };
      vfc = (video as any).requestVideoFrameCallback(onFrame);
    };
    const hasVfc = typeof (video as any).requestVideoFrameCallback === "function";
    const webkit = /AppleWebKit/.test(navigator.userAgent) && !/Chrome|Chromium|Edg/.test(navigator.userAgent);
    const follow = () => {
      raf = requestAnimationFrame(follow);
      if (!clock.engaged || video.paused || video.seeking) return;
      const now = performance.now();
      if (now - lastFix < SETTLE_MS) return;
      const fresh = frame && now - frame.shown < 250 ? frame : null;
      const d = fresh
        ? fresh.media - clock.mediaAt(ctxTimeAt(ctx, fresh.shown))
        : video.currentTime - clock.mediaAt(ctxTimeAt(ctx, now));
      if (Math.abs(d) > (webkit ? WEBKIT_SEEK_S : SEEK_S)) {
        selfSeek = true;
        lastFix = now;
        // At the music itself, never `currentTime - d`: Safari's currentTime trails
        // the picture, so that landed every seek short by the same ~90 ms. A little
        // ahead: playback resumes once the seek lands, ~50 ms later.
        video.currentTime = clock.mediaAt(ctxTimeAt(ctx, now)) + 0.05 * map.rate;
        return;
      }
      const ease = webkit || Math.abs(d) < DEADBAND_S ? 0 : Math.min(Math.max(d * EASE_GAIN, -EASE_MAX), EASE_MAX);
      const want = map.rate * (1 - ease);
      if (Math.abs(video.playbackRate - want) > 0.004) video.playbackRate = want;
    };

    void (async () => {
      try {
        const [channels, { default: SignalsmithStretch }] = await Promise.all([
          decode(ctx, url),
          // Served as-is from public/, never bundled: it builds its AudioWorklet from
          // its own source text (`${Module}`), which a bundler's rewrite breaks (the
          // worklet then never answers). MIT, see NOTICE.
          import(/* webpackIgnore: true */ /* turbopackIgnore: true */ STRETCH_SRC),
        ]);
        if (cancelled) return;
        // The stretcher's worklet only answers once the context runs, which needs a
        // tap: until the first play the video's own sound carries the lesson.
        if (ctx.state !== "running") {
          await new Promise<void>((ok) => {
            const on = () => {
              if (ctx.state !== "running") return;
              ctx.removeEventListener("statechange", on);
              ok();
            };
            ctx.addEventListener("statechange", on);
          });
          if (cancelled) return;
        }
        stretch = await SignalsmithStretch(ctx);
        if (cancelled) return stretch.disconnect();
        await stretch.addBuffers(channels.map((c) => c.slice()));
        if (cancelled) return stretch.disconnect();
        stretch.connect(gain);
        clockRef.current = clock;
        video.addEventListener("play", onPlay);
        video.addEventListener("pause", onPause);
        video.addEventListener("ended", onPause);
        video.addEventListener("seeking", onSeeking);
        video.addEventListener("seeked", onSeeked);
        raf = requestAnimationFrame(follow);
        if (hasVfc) vfc = (video as any).requestVideoFrameCallback(onFrame);
        if (!video.paused) start();
      } catch (e) {
        // Any failure: the video keeps its own sound.
        console.warn("[audioClock] music stays on the video:", e);
      }
    })();

    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
      if (hasVfc && vfc) (video as any).cancelVideoFrameCallback(vfc);
      video.removeEventListener("play", onPlay);
      video.removeEventListener("pause", onPause);
      video.removeEventListener("ended", onPause);
      video.removeEventListener("seeking", onSeeking);
      video.removeEventListener("seeked", onSeeked);
      if (stretch) {
        stretch.schedule({ active: false, output: ctx.currentTime });
        stretch.disconnect();
      }
      gain.disconnect();
      video.muted = false;
      video.playbackRate = speedRef.current;
      if (clockRef.current === clock) clockRef.current = null;
      restart.current = null;
      changed();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- speed/volume applied below without a reload
  }, [video, url]);

  useEffect(() => {
    speedRef.current = speed;
    restart.current?.();
  }, [speed]);

  useEffect(() => {
    if (gainRef.current) gainRef.current.gain.value = volume;
  }, [volume]);
}
