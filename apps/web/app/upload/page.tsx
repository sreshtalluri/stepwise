"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import LinkDoor from "../../components/front/LinkDoor";
import { PRODUCT_NAME, marketing, upload as copy } from "../../lib/copy";
import { submitFile, type Submitted } from "../../lib/submit";

/**
 * "Add a clip", A2 (docs/DESIGN.md §7d, §11). The link door is the landing
 * hero's own component (components/front/LinkDoor.tsx), so the invite gate,
 * the rights line and the button's words are the same on both pages. The file
 * sits under an "or" and works for everyone.
 *
 * States the real constraints as what works, not as what is rejected, and
 * carries each rights line once, beside the door it belongs to
 * (OPEN-DECISIONS.md D8, docs/research/link-ingestion.md).
 */
export default function UploadPage() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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
    <main className="fd">
      <nav className="fd-nav">
        <Link href="/" className="fd-logo">{PRODUCT_NAME}</Link>
        <div className="fd-nav-r">
          <Link href="/lessons">{marketing.nav.myLessons}</Link>
        </div>
      </nav>

      <div className="fd-add">
        <h1 className="fd-h1 fd-h1-app">{copy.title}</h1>

        <LinkDoor id="add" />

        <div className="fd-or">{copy.or}</div>

        <button
          type="button"
          className="fd-drop"
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
          <span>{copy.drop}</span>
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
        {error && (
          <p role="alert" className="form-error">
            {error}
          </p>
        )}
        <p className="fd-note">{copy.rights}</p>

        <h2 className="fd-works-h">{copy.worksBestHeading}</h2>
        <ul className="fd-works">
          {copy.worksBest.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </div>
    </main>
  );
}
