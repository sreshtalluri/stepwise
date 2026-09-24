"use client";

import { useEffect, useRef, useState } from "react";
import { COCO_BONES, detectionIndex, type Detections } from "../lib/flow";

/**
 * The detector's own 2D skeleton over the learner's clip, while the 3D is
 * still being built (flow redesign, direction A's cheapest reveal). It makes
 * the work visible without claiming anything the model has not produced: these
 * are the RTMO keypoints from the detection pass, drawn where the detector saw
 * them. Missing keypoints are simply not drawn.
 *
 * One accent on screen (DESIGN.md §3): the dancer seen in the most samples is
 * drawn in the accent, anyone else in a muted neutral (§7a2's rule that only
 * the selected dancer is saturated).
 *
 * Fetched once, when `available` says the sidecar exists; drawn every frame
 * against the video's current time, mapped into the video's object-fit:contain
 * box. The canvas sits inside the mirrored wrapper, so mirror flips it too.
 */
export default function SkeletonOverlay({
  jobId,
  video,
  available,
}: {
  jobId: string;
  video: HTMLVideoElement | null;
  available: boolean;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [det, setDet] = useState<Detections | null>(null);

  useEffect(() => {
    if (!available || det) return;
    let cancelled = false;
    let tries = 0;
    let timer: ReturnType<typeof setTimeout>;
    const load = async () => {
      try {
        const res = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/detections`, { cache: "no-store" });
        if (!res.ok) throw new Error(String(res.status));
        const body = (await res.json()) as Detections;
        if (!cancelled && Array.isArray(body?.dancers) && Array.isArray(body.times)) setDet(body);
      } catch {
        // The milestone can arrive a moment before the Volume commit is
        // readable; a few spaced retries, then the overlay simply stays off.
        if (!cancelled && ++tries < 4) timer = setTimeout(load, 2000 * tries);
      }
    };
    void load();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [jobId, available, det]);

  useEffect(() => {
    const cv = canvas.current;
    if (!cv || !video || !det) return;
    const ctx = cv.getContext("2d");
    if (!ctx) return;
    const count = (d: Detections["dancers"][number]) => d.points.filter(Boolean).length;
    const lead = det.dancers.reduce((a, b) => (count(b) > count(a) ? b : a), det.dancers[0]);
    const styles = getComputedStyle(cv);
    const accent = styles.getPropertyValue("--accent").trim() || "#e8952f";
    const muted = styles.getPropertyValue("--ink-faint").trim() || "#9a9188";

    let raf = 0;
    const draw = () => {
      raf = requestAnimationFrame(draw);
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const w = cv.clientWidth;
      const h = cv.clientHeight;
      if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
        cv.width = Math.round(w * dpr);
        cv.height = Math.round(h * dpr);
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      const i = detectionIndex(det, video.currentTime);
      const vw = video.videoWidth || det.width;
      const vh = video.videoHeight || det.height;
      if (i < 0 || !vw || !vh) return;
      const s = Math.min(w / vw, h / vh);
      const ox = (w - vw * s) / 2;
      const oy = (h - vh * s) / 2;
      const P = (p: [number, number]) => [ox + p[0] * vw * s, oy + p[1] * vh * s] as const;

      ctx.lineCap = "round";
      for (const d of det.dancers) {
        const pts = d.points[i];
        if (!pts) continue;
        const color = d === lead ? accent : muted;
        for (const [a, b] of COCO_BONES) {
          const pa = pts[a];
          const pb = pts[b];
          if (!pa || !pb) continue;
          const [x1, y1] = P(pa);
          const [x2, y2] = P(pb);
          // A dark underlay so the line reads on a bright frame too.
          ctx.strokeStyle = "rgba(18,16,15,0.55)";
          ctx.lineWidth = 6;
          ctx.beginPath();
          ctx.moveTo(x1, y1);
          ctx.lineTo(x2, y2);
          ctx.stroke();
          ctx.strokeStyle = color;
          ctx.lineWidth = 3;
          ctx.beginPath();
          ctx.moveTo(x1, y1);
          ctx.lineTo(x2, y2);
          ctx.stroke();
        }
        ctx.fillStyle = "#f2efe9";
        for (let k = 0; k < pts.length; k++) {
          const p = pts[k];
          if (!p || (k > 0 && k < 5)) continue; // nose only; eyes and ears are noise here
          const [x, y] = P(p);
          ctx.beginPath();
          ctx.arc(x, y, 2.4, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [video, det]);

  return <canvas ref={canvas} className="proc-overlay" aria-hidden="true" />;
}
