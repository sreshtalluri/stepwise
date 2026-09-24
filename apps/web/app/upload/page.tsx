"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { PRODUCT_NAME, upload as copy } from "../../lib/copy";
import { submitFile, submitLink, type Submitted } from "../../lib/submit";

/**
 * The upload screen: docs/DESIGN.md §7d, §11, laid out as the flow redesign's
 * "Add a clip" (direction B). The link comes first because it saves the most
 * steps; the file sits under an "or" and says it works for everyone, because
 * links are invite-gated while we test.
 *
 * States the real constraints as *what works*, not as what is rejected, and
 * carries each rights line once, beside the door it belongs to
 * (OPEN-DECISIONS.md D8, docs/research/link-ingestion.md).
 *
 * The constraints were reconciled against PRD §5 "Multi-dancer, revised
 * 2026-09-18". "One dancer" is NOT a constraint any more. Older copy in
 * DESIGN.md §7d/§11 still says "one dancer"; it predates the revision.
 */
export default function UploadPage() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [url, setUrl] = useState("");
  const [invite, setInvite] = useState("");

  async function go(work: Promise<Submitted>) {
    setError(null);
    setBusy(true);
    const out = await work;
    if ("jobId" in out) router.push(`/job/${encodeURIComponent(out.jobId)}`);
    else {
      setBusy(false);
      setError(out.error);
    }
  }

  return (
    <main className="wrap app-screen add">
      <nav className="site-nav" style={{ paddingLeft: 0, paddingRight: 0 }}>
        <Link href="/" className="logo">{PRODUCT_NAME}</Link>
      </nav>
      <h1 className="app-title">{copy.title}</h1>

      {/* The pasted-link door. A few seconds, not minutes: the service has to
          fetch the video before there is a clip at all, so the button says it
          is busy rather than routing to an empty processing screen. */}
      <form
        className="field"
        onSubmit={(e) => {
          e.preventDefault();
          if (url.trim()) void go(submitLink(url, invite));
        }}
      >
        <label className="sr-only" htmlFor="clip-url">{copy.link.placeholder}</label>
        <input
          id="clip-url"
          type="url"
          inputMode="url"
          autoComplete="off"
          placeholder={copy.link.placeholder}
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
        <button type="submit" className="btn" disabled={busy || !url.trim()}>
          {copy.link.submit}
        </button>
      </form>
      <div className="invite">
        <label className="sr-only" htmlFor="invite-code">{copy.link.inviteLabel}</label>
        <input
          id="invite-code"
          type="text"
          autoComplete="off"
          placeholder={copy.link.inviteLabel}
          value={invite}
          onChange={(e) => setInvite(e.target.value)}
        />
        <span className="meta">{copy.link.gated}</span>
      </div>
      {/* The link rights line sits with the link field, not the file one: the
          two make different claims and must not be read as one. */}
      <p className="meta" style={{ marginTop: 14, maxWidth: "56ch" }}>{copy.link.rights}</p>

      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}

      <div className="or">{copy.or}</div>

      <button
        type="button"
        className="dropzone"
        disabled={busy}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          const file = e.dataTransfer.files[0];
          if (file) void go(submitFile(file));
        }}
      >
        <b>{copy.choose}</b>
        <span className="meta">{copy.drop}</span>
      </button>
      <input
        ref={inputRef}
        type="file"
        accept="video/*"
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) void go(submitFile(file));
        }}
      />

      <ul className="works" aria-label={copy.worksBestHeading}>
        {copy.worksBest.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>

      <p className="meta" style={{ marginTop: 22 }}>{copy.rights}</p>
    </main>
  );
}
