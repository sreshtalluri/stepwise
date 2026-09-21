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
  const [url, setUrl] = useState("");
  const [invite, setInvite] = useState("");

  /**
   * The pasted-link door. Unlike a file, there is nothing to show the learner
   * while this runs — the service has to fetch the video before there is a
   * clip at all — so the button states what it is doing and the wait is a few
   * seconds, not a few minutes. Measured against the builder's own clips: 1–3s
   * when the link is already a lesson, 8–10s when it has to be fetched.
   *
   * Failure text comes from the service and is rendered as-is. The service is
   * the only thing that saw the failure, and inventing a friendlier local
   * sentence for it is exactly the §7h mistake — see lib/copy.ts's note.
   */
  async function handleLink() {
    setError(null);
    if (!url.trim()) return;
    setBusy(true);
    try {
      const res = await fetch("/api/clips/link", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Invite-Code": invite },
        body: JSON.stringify({ url: url.trim() }),
      });
      const body = (await res.json()) as {
        job_id?: string;
        detail?: { error?: { message?: string } };
      };
      if (!res.ok) {
        setBusy(false);
        setError(body.detail?.error?.message ?? copy.linkErrors.unreachable);
        return;
      }
      // No blob URL to hand the processing screen: the clip lives on the
      // service, and ProcessingScreen already falls back to fetching it.
      router.push(`/job/${body.job_id}`);
    } catch {
      setBusy(false);
      setError(copy.linkErrors.unreachable);
    }
  }

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

      <section className="link-ingest">
        <h2 className="constraints-heading">{copy.link.heading}</h2>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void handleLink();
          }}
        >
          <label className="sr-only" htmlFor="clip-url">
            {copy.link.placeholder}
          </label>
          <input
            id="clip-url"
            type="url"
            inputMode="url"
            autoComplete="off"
            placeholder={copy.link.placeholder}
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
          <label className="sr-only" htmlFor="invite-code">
            {copy.link.inviteLabel}
          </label>
          <input
            id="invite-code"
            type="text"
            autoComplete="off"
            placeholder={copy.link.invitePlaceholder}
            value={invite}
            onChange={(e) => setInvite(e.target.value)}
          />
          <button type="submit" className="btn" disabled={busy || !url.trim()}>
            {copy.link.submit}
          </button>
        </form>
        <p className="meta">{copy.link.gated}</p>
        {/* The link rights line sits with the link field, not with the file
            one: the two make different claims and must not be read as one.
            See lib/copy.ts and docs/research/link-ingestion.md. */}
        <p className="meta rights">{copy.link.rights}</p>
      </section>

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
