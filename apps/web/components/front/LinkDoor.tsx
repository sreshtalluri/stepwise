"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { privacy, upload } from "../../lib/copy";
import { submitLink, type Failure } from "../../lib/submit";
import { FAILURE_POSE, StateNote, type StateAction } from "../StateScreen";

const copy = upload.link;

/**
 * The pasted-link door, shared by the landing hero and /upload so the two
 * cannot drift: same endpoint, same invite gate, same rights line, same words.
 *
 * The gate is stated up front (links need an invite code during the beta; a
 * file works for everyone). The invite field and the link's rights line appear
 * once there is a link to use them on (audit: an invite field and a greyed
 * button before anything was pasted read as a wall).
 */
export default function LinkDoor({ id, onAddFile }: { id: string; onAddFile?: () => void }) {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [invite, setInvite] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ error: string; kind: Failure } | null>(null);
  const open = url.trim().length > 0;

  async function send() {
    setError(null);
    setBusy(true);
    const out = await submitLink(url, invite);
    if ("jobId" in out) router.push(`/job/${encodeURIComponent(out.jobId)}`);
    else {
      setBusy(false);
      setError(out);
    }
  }

  // One next step per failure. The file door works for everyone, so a link
  // the service would not take points there.
  const addFile: StateAction = onAddFile
    ? { label: upload.actions.addFile, onClick: onAddFile }
    : { label: upload.actions.addFile, href: "/upload" };
  const next: Record<Failure, StateAction> = {
    limit: { label: upload.actions.myLessons, href: "/lessons" },
    invite: addFile,
    refused: addFile,
    file: addFile,
    unreachable: { label: upload.actions.tryAgain, onClick: () => void send() },
  };

  return (
    <form
      className="fd-door"
      onSubmit={(e) => {
        e.preventDefault();
        if (open && !busy) void send();
      }}
    >
      <div className="fd-paste">
        <label className="sr-only" htmlFor={`${id}-url`}>{copy.label}</label>
        <input
          id={`${id}-url`}
          type="url"
          inputMode="url"
          autoComplete="off"
          required
          placeholder={copy.placeholder}
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
        <button type="submit" className="fd-btn" disabled={busy}>
          {busy ? copy.busy : copy.submit}
        </button>
      </div>
      <p className="fd-note">{copy.gated}</p>
      <p className="fd-note">
        {privacy.atHandover}{" "}
        <Link href="/privacy" style={{ textDecoration: "underline", textUnderlineOffset: 3 }}>
          {privacy.atHandoverLink}
        </Link>
      </p>
      {open && (
        <div className="fd-invite">
          <label htmlFor={`${id}-invite`}>{copy.inviteLabel}</label>
          <input
            id={`${id}-invite`}
            type="text"
            autoComplete="off"
            value={invite}
            onChange={(e) => setInvite(e.target.value)}
          />
          <p className="fd-note">{copy.rights}</p>
        </div>
      )}
      {error && <StateNote pose={FAILURE_POSE[error.kind]} message={error.error} action={next[error.kind]} />}
    </form>
  );
}
