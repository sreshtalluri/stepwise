"use client";

import { useEffect, useId, useRef, useState } from "react";
import { privacy as privacyCopy, removal as copy } from "../lib/copy";
import { LESSONS, lessonIdFromLink } from "../lib/lessons";
import { forgetLesson } from "../lib/myLessons";
import { StateFigure, StateNote } from "./StateScreen";
import s from "./RemoveLessonDialog.module.css";

/**
 * "Report or remove this video" — the takedown (OPEN-DECISIONS D7,
 * docs/legal/rights-and-privacy.md §6.1). Deletes for EVERYONE, now:
 * POST /api/jobs/{jobId}/removal, which services/motion-api resolves to the
 * one canonical (deduplicated) lesson.
 *
 * A native <dialog> opened with showModal(): the rest of the page is inert
 * (that is the focus trap), Esc closes it, and focus returns to the trigger.
 *
 * Mount with <RemoveLessonMenuItem jobId={lessonId} /> — see apps/web/README.md.
 */

type Relationship = keyof typeof copy.relationships;
type State =
  | { kind: "form"; error?: string; limit?: boolean }
  | { kind: "sending" }
  | { kind: "done" };

export default function RemoveLessonDialog({
  jobId,
  open,
  onClose,
  onRemoved,
}: {
  jobId: string;
  open: boolean;
  onClose: () => void;
  /** After a successful removal, when the dialog closes. Default: reload, so the page shows the removed state. */
  onRemoved?: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const [state, setState] = useState<State>({ kind: "form" });
  const [relationship, setRelationship] = useState<Relationship | null>(null);
  const [reason, setReason] = useState("");
  const id = useId();

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);

  function handleClose() {
    // Fires for Esc, the buttons, and form method="dialog" alike.
    const removed = state.kind === "done";
    setState({ kind: "form" });
    onClose();
    if (removed) (onRemoved ?? (() => window.location.reload()))();
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!relationship) return setState({ kind: "form", error: copy.pickOne });
    setState({ kind: "sending" });
    try {
      const res = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/removal`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ relationship, reason: reason.trim() }),
      });
      if (!res.ok) {
        // 429 carries a sentence in the service's voice; anything else gets ours.
        const body = (await res.json().catch(() => null)) as { detail?: { error?: { message?: string } } } | null;
        return setState({ kind: "form", error: body?.detail?.error?.message ?? copy.failed, limit: res.status === 429 });
      }
      forgetLesson(jobId);
      setState({ kind: "done" });
    } catch {
      setState({ kind: "form", error: copy.failed });
    }
  }

  const sending = state.kind === "sending";
  return (
    <dialog
      ref={ref}
      className={s.dialog}
      aria-labelledby={`${id}-t`}
      aria-describedby={`${id}-d`}
      onClose={handleClose}
    >
      {state.kind === "done" ? (
        <div className={s.body} style={{ justifyItems: "center", textAlign: "center" }}>
          <StateFigure pose="wave" size="mid" />
          <h2 id={`${id}-t`} className={s.title}>{copy.doneTitle}</h2>
          <p id={`${id}-d`} role="status">{copy.done}</p>
          <form method="dialog" className={s.actions} style={{ justifyContent: "center" }}>
            <button className="btn" autoFocus>{copy.close}</button>
          </form>
        </div>
      ) : (
        <form className={s.body} onSubmit={submit}>
          <h2 id={`${id}-t`} className={s.title}>{copy.title}</h2>
          <p id={`${id}-d`}>{copy.body}</p>

          <fieldset className={s.fieldset} disabled={sending}>
            <legend className={s.legend}>{copy.relationshipLegend}</legend>
            {(Object.keys(copy.relationships) as Relationship[]).map((r) => (
              <label key={r} className={s.radio}>
                <input
                  type="radio"
                  name="relationship"
                  value={r}
                  checked={relationship === r}
                  onChange={() => setRelationship(r)}
                />
                {copy.relationships[r]}
              </label>
            ))}
          </fieldset>

          <label className={s.legend} htmlFor={`${id}-r`}>{copy.reasonLabel}</label>
          <textarea
            id={`${id}-r`}
            className={s.textarea}
            maxLength={500}
            rows={3}
            value={reason}
            disabled={sending}
            onChange={(e) => setReason(e.target.value)}
          />

          {state.kind === "form" && state.error && (
            state.error === copy.pickOne ? (
              <p className="form-error" role="alert">{state.error}</p>
            ) : (
              <StateNote pose={state.limit ? "breathe" : "look"} message={state.error} />
            )
          )}

          <div className={s.actions}>
            <button type="button" className="btn btn-ghost" onClick={() => ref.current?.close()} disabled={sending}>
              {copy.cancel}
            </button>
            <button type="submit" className={`btn ${s.danger}`} disabled={sending} aria-busy={sending}>
              {sending ? copy.submitting : copy.submit}
            </button>
          </div>
        </form>
      )}
    </dialog>
  );
}

/**
 * The same dialog, reached from a pasted lesson link — for /privacy, so a
 * removal works for someone who has the link but is not on the lesson page.
 */
export function RemoveByLink() {
  const [text, setText] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [invalid, setInvalid] = useState(false);
  const id = useId();
  return (
    <>
    <form
      className={s.byLink}
      onSubmit={(e) => {
        e.preventDefault();
        const found = lessonIdFromLink(text);
        setInvalid(!found);
        setJobId(found);
      }}
    >
      <label className={s.legend} htmlFor={`${id}-l`}>{privacyCopy.linkLabel}</label>
      <div className={s.row}>
        <input
          id={`${id}-l`}
          className={s.textarea}
          inputMode="url"
          autoComplete="off"
          placeholder={privacyCopy.linkPlaceholder}
          value={text}
          aria-invalid={invalid}
          aria-describedby={invalid ? `${id}-e` : undefined}
          onChange={(e) => setText(e.target.value)}
        />
        <button className="btn btn-ghost">{privacyCopy.linkSubmit}</button>
      </div>
      {invalid && <p id={`${id}-e`} className="form-error" role="alert">{privacyCopy.linkInvalid}</p>}
    </form>
    {/* Outside the form: the dialog has a form of its own, and forms do not nest. */}
    {jobId && (
      <RemoveLessonDialog jobId={jobId} open onClose={() => setJobId(null)} onRemoved={() => setText("")} />
    )}
    </>
  );
}

/**
 * The entry point a lesson page mounts (in its menu, footer, wherever). Renders
 * nothing for the built-in example fixtures, which are static files with no
 * server-side lesson to remove.
 */
export function RemoveLessonMenuItem({
  jobId,
  className,
  onRemoved,
}: {
  jobId: string;
  className?: string;
  onRemoved?: () => void;
}) {
  const [open, setOpen] = useState(false);
  if (Object.hasOwn(LESSONS, jobId)) return null;
  return (
    <>
      <button type="button" className={className ?? s.trigger} onClick={() => setOpen(true)} aria-haspopup="dialog">
        {copy.menuItem}
      </button>
      <RemoveLessonDialog jobId={jobId} open={open} onClose={() => setOpen(false)} onRemoved={onRemoved} />
    </>
  );
}
