"use client";

import { useEffect, useRef } from "react";
import {
  aroundLoop, loopFor, mediaAt, nextSeekLatency, SEEK_LATENCY_START_S, steadyOffset, untilWrap, wrapsAt,
  type Loop, type TimeMap,
} from "../../lib/clockMap";

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
 * The loop is the music's too. The stretcher folds the loop's end onto its start
 * with no gap, on the count, at any speed, so a looped eight keeps time pass after
 * pass; before, each wrap waited for a video frame past the end and then for a video
 * seek, which is a different length on every phone. The clock knows when each wrap
 * comes, so the click is booked across it and the picture is sent to the loop's start
 * one seek early (how long a seek takes is measured as they happen), to land with it.
 *
 * `offsetMs` is the learner's own nudge for sound that reaches them late: wireless
 * headphones and speakers add a delay that Safari does not report at all. It moves
 * the picture and the mesh against the sound; the click needs none (same path).
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
  /** Media seconds the learner hears at `perfMs` (performance.now() clock). */
  heardAt(perfMs: number): number;
  /** The loop the music is running, [start, end) in media seconds. */
  loop: Loop | null;
}

/** What the clock last measured, for the `?sync=1` readout (SyncReadout.tsx). */
export const syncStats = {
  engaged: false,
  webkit: false,
  rate: 1,
  /** Picture minus music, ms: + is the picture ahead of the sound. */
  pictureMs: NaN,
  /** How long a video seek takes here, ms (learned). */
  seekMs: SEEK_LATENCY_START_S * 1000,
  wraps: 0,
  /** Picture minus music on the first frame after the last loop wrap, ms. */
  landedMs: NaN,
  offsetMs: 0,
  outputLatencyMs: NaN,
  baseLatencyMs: NaN,
  /** The browser reports when a sample reaches the speaker (else the context's own time). */
  outputTimestamp: false,
};

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
const offsets: number[] = [];
function ctxTimeAt(ctx: AudioContext, perfMs: number): number {
  const ts = ctx.getOutputTimestamp?.();
  const reported = !!(ts && ts.contextTime && ts.performanceTime);
  syncStats.outputTimestamp = reported;
  // Either reading only moves once per audio callback: `steadyOffset` reads it steady,
  // so a mesh drawn from it every frame does not judder.
  const sample = reported
    ? ts!.contextTime! - ts!.performanceTime! / 1000
    : ctx.currentTime - (ctx.outputLatency || 0) - performance.now() / 1000;
  return steadyOffset(offsets, sample) + perfMs / 1000;
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
 * `loopKey` changes whenever `loopRef` does, so a loop edge dragged mid-play reaches
 * the music without a seek. `onWrapRef` fires once per pass of the loop.
 */
export function useAudioClock(
  video: HTMLVideoElement | null,
  url: string,
  speed: number,
  volume: number,
  loopRef: React.RefObject<Loop | null>,
  onWrapRef: React.RefObject<(() => void) | null>,
  loopKey: string,
  offsetMs: number,
) {
  const speedRef = useRef(speed);
  const offsetRef = useRef(offsetMs);
  const gainRef = useRef<GainNode | null>(null);
  const restart = useRef<(() => void) | null>(null);
  const realign = useRef<(() => void) | null>(null);

  useEffect(() => {
    const ctx = audioContext();
    if (!video || !ctx || !url) return;
    let cancelled = false;
    let stretch: any = null;
    let map: TimeMap = { output: 0, input: 0, rate: 1, loop: null };
    let wrapsSeen = 0;
    /** The picture has been sent to the loop's start for the wrap that is coming. */
    let preSeeked = false;
    /** A seek of ours still to land: when it was sent, and where to. */
    let sent: { at: number; to: number } | null = null;
    let seekLatency = SEEK_LATENCY_START_S;
    let selfSeek = false;
    let lastFix = 0;
    let raf = 0;
    const gain = ctx.createGain();
    gain.gain.value = volume; // linear, as video.volume was
    gain.connect(ctx.destination);
    gainRef.current = gain;

    /** Context time of the sound the learner hears at `perfMs`, their nudge included. */
    const heard = (perfMs: number) => ctxTimeAt(ctx, perfMs) - offsetRef.current / 1000;
    const clock: AudioClock = {
      ctx,
      engaged: false,
      rate: speedRef.current,
      mediaAt: (at) => mediaAt(map, at),
      heardAt: (perfMs) => mediaAt(map, heard(perfMs)),
      get loop() {
        return map.loop;
      },
    };
    const changed = () => {
      syncStats.engaged = clock.engaged;
      syncStats.rate = clock.rate;
      clockEvents?.dispatchEvent(new Event("change"));
    };

    /** The music plays media `input` from 30 ms on, looping if a loop is set. */
    const book = (input: number) => {
      const output = ctx.currentTime + AHEAD_S;
      const rate = speedRef.current;
      map = { output, input, rate, loop: loopFor(loopRef.current, input) };
      wrapsSeen = 0;
      preSeeked = false;
      // Always both loop edges: a new segment inherits the last one's.
      stretch.schedule({ active: true, output, input, rate, loopStart: map.loop?.[0] ?? 0, loopEnd: map.loop?.[1] ?? 0 });
      clock.engaged = true;
      clock.rate = rate;
      changed();
    };
    const seekPicture = (to: number, now: number) => {
      selfSeek = true;
      lastFix = now;
      sent = { at: now, to };
      video.currentTime = to;
    };

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
      const now = performance.now();
      const lp = loopRef.current;
      let from = video.currentTime;
      // Playing on past the loop's end goes back to its start, as it always has.
      if (lp && from >= lp[1]) seekPicture((from = lp[0]), now);
      // The sound booked now is heard a moment later (and the learner's nudge later
      // still): by then the picture is this far on. Folded if that crosses the loop's end.
      const lead = AHEAD_S + offsetRef.current / 1000;
      book(Math.max(0, mediaAt({ output: 0, input: from, rate: speedRef.current, loop: loopFor(lp, from) }, lead)));
      video.muted = true;
      lastFix = now;
    };
    const stop = () => {
      if (!stretch) return;
      stretch.schedule({ active: false, output: ctx.currentTime });
      clock.engaged = false;
      changed();
    };
    // A new speed or loop: the music carries on from where it is.
    restart.current = () => {
      if (clock.engaged) book(clock.mediaAt(ctx.currentTime + AHEAD_S));
    };
    // A new nudge: the music moves against the picture, so line them up afresh.
    realign.current = () => {
      if (clock.engaged) start();
    };

    const onPlay = () => start();
    const onPause = () => stop();
    const onEnded = () => {
      // The video ran out before the wrap reached it (a loop up to the last frame).
      if (!clock.engaged || !map.loop) return stop();
      seekPicture(clock.heardAt(performance.now()), performance.now());
      void video.play().catch(() => {});
    };
    const onSeeking = () => {
      if (selfSeek) return;
      if (!video.paused) start();
    };
    const landed = (resumedMs: number, shownMs: number, media: number) => {
      if (!sent) return;
      seekLatency = nextSeekLatency(seekLatency, (resumedMs - sent.at) / 1000);
      syncStats.seekMs = Math.round(seekLatency * 1000);
      if (clock.engaged) syncStats.landedMs = Math.round(aroundLoop(media - clock.heardAt(shownMs), map.loop) * 1000);
      sent = null;
    };
    const onSeeked = () => {
      selfSeek = false;
      if (!hasVfc) landed(performance.now(), performance.now(), video.currentTime);
    };

    // Keep the picture on the music: the counts and the mesh over the video read the
    // video's frames. The frame on screen and when, from requestVideoFrameCallback:
    // Safari's `currentTime` trails the picture (~66 ms at 0.5x on iOS 26.5), so it is
    // only the fallback where rVFC is missing.
    let frame: { media: number; shown: number } | null = null;
    let vfc = 0;
    const onFrame = (_now: number, meta: { mediaTime: number; expectedDisplayTime: number }) => {
      frame = { media: meta.mediaTime, shown: meta.expectedDisplayTime };
      // A seek of ours, playing again: when it would have shown the frame it was sent
      // to, had it been playing all along. That is the seek's whole cost (the frame
      // itself appears sooner, then sits while the decoder restarts), on the video's
      // own timing alone, so no audio reading can bias it.
      if (sent && frame.shown > sent.at && frame.media > sent.to + 0.02 && frame.media < sent.to + 0.5) {
        landed(frame.shown - ((frame.media - sent.to) / (video.playbackRate || 1)) * 1000, frame.shown, frame.media);
      }
      vfc = (video as any).requestVideoFrameCallback(onFrame);
    };
    const hasVfc = typeof (video as any).requestVideoFrameCallback === "function";
    const webkit = /AppleWebKit/.test(navigator.userAgent) && !/Chrome|Chromium|Edg/.test(navigator.userAgent);
    syncStats.webkit = webkit;
    const follow = () => {
      raf = requestAnimationFrame(follow);
      if (!clock.engaged || video.paused) return;
      const now = performance.now();
      const lp = map.loop;
      if (lp) {
        const at = heard(now);
        const wraps = wrapsAt(map, at);
        if (wraps > wrapsSeen) {
          // The music is back at the loop's start. The picture is on its way there,
          // unless the frame loop was held up (a hidden tab): then straight to the music.
          wrapsSeen = wraps;
          syncStats.wraps++;
          if (!preSeeked) seekPicture(clock.heardAt(now) + seekLatency * map.rate, now);
          preSeeked = false;
          onWrapRef.current?.();
        } else if (!preSeeked && untilWrap(map, at) <= Math.min(seekLatency, (0.4 * (lp[1] - lp[0])) / map.rate)) {
          preSeeked = true;
          seekPicture(lp[0], now);
        } else if (!preSeeked && !video.seeking && video.currentTime >= lp[1]) {
          // The picture ran off the end of the loop (it was started within a breath of it).
          seekPicture(clock.heardAt(now) + seekLatency * map.rate, now);
        }
      }
      if (video.seeking) return;
      const fresh = frame && now - frame.shown < 250 ? frame : null;
      const d = aroundLoop(fresh ? fresh.media - clock.heardAt(fresh.shown) : video.currentTime - clock.heardAt(now), lp);
      syncStats.pictureMs = Math.round(d * 1000);
      if (now - lastFix < SETTLE_MS) return;
      if (Math.abs(d) > (webkit ? WEBKIT_SEEK_S : SEEK_S)) {
        // At the music itself, never `currentTime - d`: Safari's currentTime trails
        // the picture, so that landed every seek short by the same ~90 ms. A seek
        // ahead: playback resumes once the seek lands.
        seekPicture(clock.heardAt(now) + seekLatency * map.rate, now);
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
        syncStats.outputLatencyMs = Math.round((ctx.outputLatency ?? NaN) * 1000);
        syncStats.baseLatencyMs = Math.round((ctx.baseLatency ?? NaN) * 1000);
        video.addEventListener("play", onPlay);
        video.addEventListener("pause", onPause);
        video.addEventListener("ended", onEnded);
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
      video.removeEventListener("ended", onEnded);
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
      clock.engaged = false;
      restart.current = null;
      realign.current = null;
      changed();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- speed, loop, nudge and volume are applied below without a reload
  }, [video, url]);

  useEffect(() => {
    speedRef.current = speed;
    restart.current?.();
  }, [speed, loopKey]);

  useEffect(() => {
    offsetRef.current = offsetMs;
    syncStats.offsetMs = offsetMs;
    realign.current?.();
  }, [offsetMs]);

  useEffect(() => {
    if (gainRef.current) gainRef.current.gain.value = volume;
  }, [volume]);
}
