"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import type { Focus } from "../Stage3D";
import {
  projectBoxToFrame,
  cropTransform,
  followStep,
  damp,
  sampleIndexAt,
  FOLLOW,
  type MotionResult,
  type Rect,
  type Vec3,
} from "../../lib/motion";
import { dancerBox } from "../../lib/dancers";
import { countAtTime, type CountGrid } from "../../../../packages/navigation/src/core";

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
export function useVideoClock(
  video: HTMLVideoElement | null,
  loopRef: React.RefObject<[number, number] | null>,
  onWrapRef: React.RefObject<(() => void) | null>,
) {
  const timeRef = useRef(0);
  const [displayTime, setDisplayTime] = useState(0);

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
    const step = (_now: number, meta: { mediaTime: number }) => {
      if (cancelled) return;
      lastFrameAt = performance.now();
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
    const onSeek = () => publish(video.currentTime);
    video.addEventListener("seeked", onSeek);
    video.addEventListener("loadedmetadata", onSeek);

    return () => {
      cancelled = true;
      if (hasRvfc && rvfcHandle) (video as any).cancelVideoFrameCallback(rvfcHandle);
      cancelAnimationFrame(rafHandle);
      video.removeEventListener("seeked", onSeek);
      video.removeEventListener("loadedmetadata", onSeek);
    };
  }, [video, loopRef, onWrapRef]);

  return { timeRef, displayTime };
}

/**
 * The count under the playhead, re-rendering only when it changes — the count
 * numerals must turn over on the beat, not on a 10 Hz display tick. +40 ms because a
 * seek to a count boundary lands a hair early on some decoders.
 */
export function useCount(timeRef: React.RefObject<number>, grid: CountGrid): number {
  const [count, setCount] = useState(() => Math.floor(countAtTime(grid, timeRef.current + 0.04)));
  useEffect(() => {
    let h = 0;
    const tick = () => {
      h = requestAnimationFrame(tick);
      const c = Math.floor(countAtTime(grid, timeRef.current + 0.04));
      setCount((prev) => (prev === c ? prev : c));
    };
    h = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(h);
  }, [timeRef, grid]);
  return count;
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

      const win = cropTransform({ x: centre[0] - raw.width / 2, y: centre[1] - height / 2, width: raw.width, height });
      // translate() percentages resolve against the ELEMENT box; `object-fit: contain`
      // letterboxes the frame inside it. Convert once, here.
      const elW = video.clientWidth;
      const elH = video.clientHeight;
      const aspect = doc.source_video.width_px / doc.source_video.height_px;
      const imgW = Math.min(elW, elH * aspect);
      const imgH = imgW / aspect;
      const tx = elW > 0 ? (win.tx * imgW) / elW : 0;
      const ty = elH > 0 ? (win.ty * imgH) / elH : 0;
      video.style.transform = `${mirror}translate(${(tx * 100).toFixed(3)}%, ${(ty * 100).toFixed(3)}%) scale(${win.zoom.toFixed(4)})`;

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
 * Stills from THIS clip, for the dancer picker: one frame per request, cropped to a
 * box, as a data URL. A second, muted, never-shown `<video>` on the same URL does the
 * seeking, so the lesson's own clock is never touched. Requests run one at a time.
 */
export function useFrameGrabs(
  videoUrl: string,
  requests: { t: number; box: Rect | null }[],
  enabled: boolean,
): (string | null)[] {
  const [urls, setUrls] = useState<(string | null)[]>(() => requests.map(() => null));
  const key = JSON.stringify(requests);
  useEffect(() => {
    if (!enabled || !requests.length) return;
    let cancelled = false;
    const v = document.createElement("video");
    v.muted = true;
    v.playsInline = true;
    v.preload = "auto";
    v.src = videoUrl;
    const grab = (t: number) =>
      new Promise<void>((resolve) => {
        const done = () => resolve();
        v.addEventListener("seeked", done, { once: true });
        v.currentTime = Math.max(0.001, t);
      });
    (async () => {
      await new Promise<void>((resolve, reject) => {
        if (v.readyState >= 1) resolve();
        v.addEventListener("loadeddata", () => resolve(), { once: true });
        v.addEventListener("error", () => reject(), { once: true });
      }).catch(() => (cancelled = true));
      for (let i = 0; i < requests.length && !cancelled; i++) {
        const { t, box } = requests[i];
        await grab(t);
        if (cancelled) break;
        const vw = v.videoWidth, vh = v.videoHeight;
        if (!vw || !vh) continue;
        const b = box ?? { x: 0, y: 0, width: 1, height: 1 };
        // Portrait card, centred on the box, grown to 3:4 without leaving the frame.
        let w = b.width * vw, h = b.height * vh;
        if (w / h < 0.75) w = h * 0.75; else h = w / 0.75;
        w = Math.min(w, vw); h = Math.min(h, vh);
        const cx = (b.x + b.width / 2) * vw, cy = (b.y + b.height / 2) * vh;
        const sx = Math.min(Math.max(cx - w / 2, 0), vw - w), sy = Math.min(Math.max(cy - h / 2, 0), vh - h);
        const c = document.createElement("canvas");
        c.width = 240;
        c.height = 320;
        c.getContext("2d")?.drawImage(v, sx, sy, w, h, 0, 0, 240, 320);
        let url: string | null = null;
        try {
          url = c.toDataURL("image/jpeg", 0.8);
        } catch {
          url = null; // a cross-origin video taints the canvas; the picker falls back to numbers
        }
        setUrls((prev) => prev.map((u, k) => (k === i ? url : u)));
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
