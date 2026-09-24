"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { marketing, upload } from "../lib/copy";
import { submitLink } from "../lib/submit";

/**
 * The paste box in the landing hero (flow redesign, direction A): one step
 * from the front door to a running job. Same endpoint, same invite gate and
 * the same link rights line as /upload, through the same lib/submit.ts.
 *
 * The file door is a link to /upload rather than a picker here: that page
 * carries the file's own rights line and the "works best with" constraints,
 * and a file uploaded from the hero would skip both.
 */
export default function PasteHero() {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [invite, setInvite] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const copy = marketing.paste;

  async function send() {
    setError(null);
    setBusy(true);
    const out = await submitLink(url, invite);
    if ("jobId" in out) router.push(`/job/${encodeURIComponent(out.jobId)}`);
    else {
      setBusy(false);
      setError(out.error);
    }
  }

  return (
    <div className="paste">
      <form
        className="field"
        onSubmit={(e) => {
          e.preventDefault();
          if (url.trim()) void send();
        }}
      >
        <label className="sr-only" htmlFor="hero-url">{copy.label}</label>
        <input
          id="hero-url"
          type="url"
          inputMode="url"
          autoComplete="off"
          placeholder={copy.placeholder}
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
        <button type="submit" className="btn" disabled={busy || !url.trim()}>
          {busy ? copy.busy : copy.submit}
        </button>
      </form>
      <div className="invite">
        <label className="sr-only" htmlFor="hero-invite">{copy.inviteLabel}</label>
        <input
          id="hero-invite"
          type="text"
          autoComplete="off"
          placeholder={copy.inviteLabel}
          value={invite}
          onChange={(e) => setInvite(e.target.value)}
        />
        <span className="meta">{copy.inviteNote}</span>
      </div>
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
      <div className="under">
        <Link href="/upload" className="linkish">{copy.orFile}</Link>
        <span className="meta">{marketing.hero.noAccount}</span>
      </div>
      <p className="meta paste-rights">{upload.link.rights}</p>
    </div>
  );
}
