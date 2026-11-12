"use client";

import { useEffect, useState } from "react";
import { syncStats } from "./audioClock";

/**
 * `?sync=1` on a lesson: what the audio clock is measuring on THIS device, to read
 * out (or tap to copy) when checking a phone. Nothing here changes playback.
 *
 * - picture: picture minus sound, ms. Near 0 is in sync; + is the picture ahead.
 * - landed: the same, on the first frame after the last loop wrap.
 * - seek: how long a video seek takes here (the picture is sent that early).
 */
export default function SyncReadout() {
  const [on, setOn] = useState(false);
  const [text, setText] = useState("");
  useEffect(() => setOn(new URLSearchParams(window.location.search).get("sync") === "1"), []);
  useEffect(() => {
    if (!on) return;
    const n = (v: number) => (Number.isFinite(v) ? String(v) : "-");
    const read = () => {
      const s = syncStats;
      setText(
        [
          `clock ${s.engaged ? "audio" : "video"} · ${s.webkit ? "webkit" : "other"} · ${s.rate}x`,
          `picture ${n(s.pictureMs)} ms · landed ${n(s.landedMs)} ms`,
          `seek ${n(s.seekMs)} ms · wraps ${s.wraps}`,
          `nudge ${s.offsetMs} ms · out ${n(s.outputLatencyMs)} · base ${n(s.baseLatencyMs)} · ts ${s.outputTimestamp ? "yes" : "no"}`,
        ].join("\n"),
      );
    };
    read();
    const id = window.setInterval(read, 250);
    return () => window.clearInterval(id);
  }, [on]);
  if (!on) return null;
  return (
    <pre
      onClick={() => void navigator.clipboard?.writeText(`${text}\n${navigator.userAgent}`).catch(() => {})}
      style={{
        position: "fixed", left: 8, top: 8, zIndex: 9999, margin: 0, padding: "6px 8px", borderRadius: 6,
        background: "rgba(0,0,0,.78)", color: "#fff", font: "11px/1.35 ui-monospace, monospace", pointerEvents: "auto",
      }}
    >
      {text}
    </pre>
  );
}
