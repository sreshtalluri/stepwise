"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { Lockup } from "../../components/brand/Mark";
import { useRouter } from "next/navigation";
import LinkDoor from "../../components/front/LinkDoor";
import { marketing, upload as copy } from "../../lib/copy";
import { submitFile, type Failure, type Submitted } from "../../lib/submit";
import { FAILURE_POSE, StateNote, type StateAction } from "../../components/StateScreen";

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
  const [error, setError] = useState<{ error: string; kind: Failure } | null>(null);
  const [busy, setBusy] = useState(false);
  const lastFile = useRef<File | null>(null);

  async function go(work: Promise<Submitted>) {
    setError(null);
    setBusy(true);
    const out = await work;
    if ("jobId" in out) router.push(`/job/${encodeURIComponent(out.jobId)}`);
    else {
      setBusy(false);
      setError(out);
    }
  }

  function send(file: File) {
    lastFile.current = file;
    void go(submitFile(file));
  }

  const chooseFile = () => inputRef.current?.click();
  // One next step per failure, beside the sentence (components/StateScreen.tsx).
  const next: Record<Failure, StateAction> = {
    limit: { label: copy.actions.myLessons, href: "/lessons" },
    invite: { label: copy.actions.chooseFile, onClick: chooseFile },
    refused: { label: copy.actions.chooseFile, onClick: chooseFile },
    file: { label: copy.actions.chooseFile, onClick: chooseFile },
    unreachable: { label: copy.actions.tryAgain, onClick: () => lastFile.current && send(lastFile.current) },
  };

  return (
    <main className="fd">
      <nav className="fd-nav">
        <Lockup />
        <div className="fd-nav-r">
          <Link href="/lessons">{marketing.nav.myLessons}</Link>
        </div>
      </nav>

      <div className="fd-add">
        <h1 className="fd-h1 fd-h1-app">{copy.title}</h1>

        <LinkDoor id="add" onAddFile={chooseFile} />

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
            if (file) send(file);
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
            // Cleared, so choosing the same file again after a failure still fires.
            e.target.value = "";
            if (file) send(file);
          }}
        />
        {error && <StateNote pose={FAILURE_POSE[error.kind]} message={error.error} action={next[error.kind]} />}
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
