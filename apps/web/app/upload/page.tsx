"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { upload as copy } from "../../lib/copy";
import { rememberLocalClip } from "../../lib/jobStatus";

/**
 * The upload screen — docs/DESIGN.md §7d, §11.
 *
 * States the real constraints as *what works*, not as what is rejected, and
 * carries the rights line once, plainly (OPEN-DECISIONS.md D8).
 *
 * The constraints below were reconciled against PRD §5 "Multi-dancer, revised
 * 2026-09-18". "One dancer" is NOT a constraint any more: RTMO, ByteTrack and
 * the frozen contract's `persons` array are all multi-person, and the MVP
 * reconstructs every dancer with a picker for whose body you learn from
 * (DESIGN.md §7a2). Older copy in DESIGN.md §7d/§11 still says "one dancer" —
 * it predates the revision. Do not copy it back in.
 */

const MAX_SECONDS = 60;

export default function UploadPage() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleFile(file: File) {
    setError(null);
    if (!file.type.startsWith("video/")) {
      setError(copy.errors.wrongType);
      return;
    }
    const seconds = await readDuration(file);
    // A clip whose duration cannot be read is not rejected here — the service
    // normalises with ffprobe and is the authority. Only a confidently
    // over-long clip is stopped, to save the upload.
    if (seconds !== null && seconds > MAX_SECONDS + 0.5) {
      setError(copy.errors.tooLong);
      return;
    }

    setBusy(true);
    try {
      const body = new FormData();
      body.append("video", file);
      const res = await fetch("/api/jobs", { method: "POST", body });
      if (!res.ok) throw new Error(String(res.status));
      const { job_id: jobId } = (await res.json()) as { job_id: string };
      // Not revoked: the processing screen plays this immediately, so there is
      // no dead time while the job runs (DESIGN.md §7c).
      rememberLocalClip(jobId, URL.createObjectURL(file));
      router.push(`/job/${jobId}`);
    } catch {
      setBusy(false);
      setError("The upload did not go through. Check your connection and try again.");
    }
  }

  return (
    <main className="wrap app-screen">
      <h1 className="app-title">{copy.title}</h1>
      <p className="muted">{copy.subtitle}</p>

      <div
        className="dropzone"
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          const file = e.dataTransfer.files[0];
          if (file) void handleFile(file);
        }}
      >
        <button
          type="button"
          className="btn btn-lg"
          disabled={busy}
          onClick={() => inputRef.current?.click()}
        >
          {copy.choose}
        </button>
        <p className="meta" style={{ marginTop: 12 }}>
          {copy.drop}
        </p>
        <input
          ref={inputRef}
          type="file"
          accept="video/*"
          hidden
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void handleFile(file);
          }}
        />
      </div>

      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}

      <section className="constraints">
        <h2 className="constraints-heading">{copy.worksBestHeading}</h2>
        <ul>
          {copy.worksBest.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </section>

      <p className="meta rights">{copy.rights}</p>
    </main>
  );
}

/** Duration in seconds, or null if the browser cannot tell us. */
function readDuration(file: File): Promise<number | null> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const video = document.createElement("video");
    video.preload = "metadata";
    const done = (value: number | null) => {
      URL.revokeObjectURL(url);
      resolve(value);
    };
    video.onloadedmetadata = () =>
      done(Number.isFinite(video.duration) ? video.duration : null);
    video.onerror = () => done(null);
    video.src = url;
  });
}
