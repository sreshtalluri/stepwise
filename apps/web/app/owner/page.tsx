"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { OPTION_LETTERS, barOptions, countAt, leadInStart, optionOf } from "../../lib/ownerCount";
import s from "./owner.module.css";

/**
 * /owner: check and set the canonical count 1 of recent lessons
 * (services/motion-api /owner/*). Not linked from anywhere, noindex, and
 * useless without the owner key, which lives in this device's localStorage only.
 *
 * The current pick is revealed only after a choice, so it cannot bias one.
 */

const KEY_STORE = "stepwise-owner-key";

interface Job {
  job_id: string;
  clip_id: string;
  created_at: number | null;
  duration_s: number | null;
  bpm: number | null;
  seconds_per_count: number | null;
  count_one_s: number | null;
  confirmed: boolean;
  credit: { creator?: string | null; host?: string; url?: string } | null;
  video_url: string;
}

function readKey(): string {
  try {
    return localStorage.getItem(KEY_STORE) ?? "";
  } catch {
    return "";
  }
}

function writeKey(v: string | null) {
  try {
    if (v) localStorage.setItem(KEY_STORE, v);
    else localStorage.removeItem(KEY_STORE);
  } catch {
    /* private mode: the key lasts this visit only */
  }
}

let audio: AudioContext | null = null;
function click(strong: boolean) {
  try {
    audio ??= new AudioContext();
    const o = audio.createOscillator();
    const g = audio.createGain();
    o.frequency.value = strong ? 1760 : 1100;
    g.gain.setValueAtTime(strong ? 0.5 : 0.2, audio.currentTime);
    g.gain.exponentialRampToValueAtTime(0.0001, audio.currentTime + 0.07);
    o.connect(g).connect(audio.destination);
    o.start();
    o.stop(audio.currentTime + 0.08);
  } catch {
    /* no audio: the flashing counts still work */
  }
}

export default function OwnerPage() {
  const [key, setKey] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [onlyOpen, setOnlyOpen] = useState(false);
  // Saved this visit: stays on screen under the filter, so the reveal is seen.
  const [savedNow, setSavedNow] = useState<Set<string>>(new Set());

  useEffect(() => setKey(readKey()), []);

  useEffect(() => {
    if (!key) return;
    setError(null);
    fetch("/api/owner/queue", { headers: { "x-stepwise-owner-key": key } })
      .then(async (r) => {
        if (r.status === 403 || r.status === 404) {
          writeKey(null);
          setKey("");
          setError(r.status === 403 ? "That key was not accepted." : "The owner tool is not switched on for this API.");
        } else if (!r.ok) {
          setError(`Could not load the queue (${r.status}).`);
        } else {
          setJobs((await r.json()).jobs);
        }
      })
      .catch(() => setError("Could not reach the API."));
  }, [key]);

  const onSaved = useCallback((jobId: string, countOneS: number) => {
    setSavedNow((prev) => new Set(prev).add(jobId));
    setJobs((prev) => prev && prev.map((j) => (j.job_id === jobId ? { ...j, confirmed: true, count_one_s: countOneS } : j)));
  }, []);

  if (key === null) return null;

  if (!key) {
    return (
      <main className={`wrap app-screen ${s.page}`}>
        <h1 className="app-title">Count 1</h1>
        <form
          className={s.keyForm}
          onSubmit={(e) => {
            e.preventDefault();
            const v = draft.trim();
            if (!v) return;
            writeKey(v);
            setDraft("");
            setKey(v);
          }}
        >
          <label htmlFor="owner-key">Owner key</label>
          <input id="owner-key" type="password" autoComplete="off" autoCapitalize="off" spellCheck={false}
            value={draft} onChange={(e) => setDraft(e.target.value)} />
          <button className="btn btn-sm" type="submit">Continue</button>
          <p className="meta">Kept on this device only.</p>
        </form>
        {error && <p className={s.error} role="alert">{error}</p>}
      </main>
    );
  }

  const open = jobs?.filter((j) => !j.confirmed).length ?? 0;
  const shown = jobs?.filter((j) => !onlyOpen || !j.confirmed || savedNow.has(j.job_id)) ?? [];

  return (
    <main className={`wrap app-screen ${s.page}`}>
      <div className={s.head}>
        <h1 className="app-title">Where is count 1?</h1>
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => { writeKey(null); setKey(""); setJobs(null); }}>
          Forget key
        </button>
      </div>
      <p className="muted">
        Press <b>Play</b> on an option: it starts four counts early and flashes the counts with a click, louder on 1.
        Pick the option where 1 lands on the dancer&apos;s 1. None fits? Use <b>Tap the 1</b>. A pick is saved for
        every new learner; anyone who already set their own counts keeps theirs.
      </p>
      {error && <p className={s.error} role="alert">{error}</p>}
      {jobs && (
        <label className={s.filter}>
          <input type="checkbox" checked={onlyOpen} onChange={(e) => setOnlyOpen(e.target.checked)} />
          Not yet confirmed only ({open} of {jobs.length})
        </label>
      )}
      {!jobs && !error && <p className="meta">Loading…</p>}
      {shown.map((j) => (
        <Card key={j.job_id} job={j} ownerKey={key} onSaved={onSaved} />
      ))}
    </main>
  );
}

function Card({ job, ownerKey, onSaved }: { job: Job; ownerKey: string; onSaved: (jobId: string, t: number) => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const countEl = useRef<HTMLDivElement>(null);
  const origin = useRef<number | null>(null);
  const lastBeat = useRef<number | null>(null);
  const raf = useRef(0);
  const clicksOn = useRef(true);
  const [clicks, setClicks] = useState(true);
  const [lead, setLead] = useState("");
  const [duration, setDuration] = useState(job.duration_s);
  const [tapping, setTapping] = useState(false);
  const [tapT, setTapT] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState("");
  // What was served when this card loaded; shown only once a choice is made.
  const [pickAtLoad] = useState(job.count_one_s);
  const [chosen, setChosen] = useState<{ option: number | null; tap: boolean } | null>(null);

  useEffect(() => () => cancelAnimationFrame(raf.current), []);

  const spc = job.seconds_per_count;
  if (!spc || job.count_one_s === null || pickAtLoad === null) {
    return (
      <section className={s.card}>
        <Meta job={job} duration={duration} />
        <p className="meta">No beat grid for this clip, so there is nothing to set.</p>
      </section>
    );
  }
  const options = barOptions(job.count_one_s, spc);
  const wasOption = optionOf(pickAtLoad, job.count_one_s, spc);

  const loop = () => {
    const v = video.current;
    const el = countEl.current;
    if (v && el && origin.current !== null) {
      const { beat, count } = countAt(v.currentTime, origin.current, spc);
      if (beat !== lastBeat.current) {
        lastBeat.current = beat;
        el.textContent = String(count);
        el.classList.toggle(s.one, count === 1);
        el.classList.remove(s.pulse);
        void el.offsetWidth; // restart the pulse
        el.classList.add(s.pulse);
        if (clicksOn.current && !v.paused) click(count === 1);
      }
      setLead(beat < 0 ? "lead-in" : "");
    }
    raf.current = requestAnimationFrame(loop);
  };

  const pauseOthers = () =>
    document.querySelectorAll("video").forEach((o) => {
      if (o !== video.current) o.pause();
    });

  const playFrom = (t: number) => {
    const v = video.current;
    if (!v) return;
    pauseOthers();
    setTapping(false);
    origin.current = t;
    lastBeat.current = null;
    v.currentTime = leadInStart(t, spc);
    void v.play();
    cancelAnimationFrame(raf.current);
    raf.current = requestAnimationFrame(loop);
  };

  const startTap = () => {
    const v = video.current;
    if (!v) return;
    pauseOthers();
    cancelAnimationFrame(raf.current);
    origin.current = null;
    if (countEl.current) countEl.current.textContent = "";
    setLead("listening for your tap");
    setTapping(true);
    v.currentTime = 0;
    void v.play();
  };

  const tap = () => {
    const v = video.current;
    if (v && !v.paused) setTapT(v.currentTime);
  };

  const save = async (t: number, method: "option" | "tap", option: number | null) => {
    setSaving(true);
    setStatus("Saving… this can take half a minute.");
    try {
      const r = await fetch(`/api/owner/jobs/${encodeURIComponent(job.job_id)}/count-one`, {
        method: "POST",
        headers: { "content-type": "application/json", "x-stepwise-owner-key": ownerKey },
        body: JSON.stringify({ count_one_s: t, method, option: option === null ? null : OPTION_LETTERS[option] }),
      });
      if (!r.ok) {
        const detail = await r.json().then((b) => b.detail).catch(() => null);
        setStatus(`Not saved (${r.status}${typeof detail === "string" ? `: ${detail}` : ""}).`);
        return;
      }
      const out = await r.json();
      const snapped: number = out.proposed_counts.count_one_s;
      const picked = optionOf(snapped, job.count_one_s!, spc);
      setChosen({ option: picked, tap: method === "tap" });
      const was = `${OPTION_LETTERS[wasOption]} (${pickAtLoad.toFixed(2)} s)`;
      setStatus(
        `Saved: ${method === "tap" ? "your tap, on" : "option"} ${OPTION_LETTERS[picked]}, 1 at ${snapped.toFixed(2)} s. ` +
          (picked === wasOption ? `The pick before was the same beat: ${was}.` : `The pick before was ${was}.`),
      );
      onSaved(job.job_id, snapped);
    } catch {
      setStatus("Not saved: could not reach the API.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className={s.card}>
      <div className={s.stage}>
        <video ref={video} src={`${job.video_url}#t=0.1`} preload="metadata" playsInline
          onLoadedMetadata={(e) => { if (duration == null) setDuration(e.currentTarget.duration); }} />
        <div ref={countEl} className={s.count} aria-hidden />
        {lead && <div className={s.lead}>{lead}</div>}
      </div>
      <div className={s.body}>
        <Meta job={job} duration={duration} />
        <label className={s.small}>
          <input type="checkbox" checked={clicks}
            onChange={(e) => { setClicks(e.target.checked); clicksOn.current = e.target.checked; }} />
          Click on each count
        </label>
        <ol className={s.opts}>
          {options.map((t, i) => (
            <li key={i} className={s.opt}>
              <b>{OPTION_LETTERS[i]}</b>
              <span>
                1 at {t.toFixed(2)} s
                {chosen && i === wasOption && <span className={s.was}>was the pick</span>}
              </span>
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => playFrom(t)}>Play</button>
              <button type="button" disabled={saving}
                className={`btn btn-sm ${chosen && !chosen.tap && chosen.option === i ? s.chosen : ""}`}
                onClick={() => save(t, "option", i)}>
                This is the 1
              </button>
            </li>
          ))}
        </ol>
        <div className={s.tap}>
          <b>None of these? Tap the 1</b>
          <p className="meta">Plays from the start. Press the button (or Space) the moment you&apos;d say &ldquo;1&rdquo;.</p>
          <div className={s.row}>
            <button type="button" className="btn btn-ghost btn-sm" onClick={startTap}>Play from the start</button>
            <button type="button" className="btn btn-sm" disabled={!tapping} onClick={tap}
              onKeyDown={(e) => { if (e.code === "Space") { e.preventDefault(); tap(); } }}>
              Tap: this is 1
            </button>
            {tapT !== null && <span className="meta">tapped at {tapT.toFixed(2)} s</span>}
          </div>
          <div className={s.row}>
            <button type="button" className="btn btn-ghost btn-sm" disabled={tapT === null} onClick={() => tapT !== null && playFrom(tapT)}>
              Play from my tap
            </button>
            <button type="button" disabled={tapT === null || saving}
              className={`btn btn-sm ${chosen?.tap ? s.chosen : ""}`}
              onClick={() => tapT !== null && save(tapT, "tap", null)}>
              Use my tap
            </button>
          </div>
        </div>
        <p className={s.status} role="status">{status}</p>
      </div>
    </section>
  );
}

function Meta({ job, duration }: { job: Job; duration: number | null }) {
  const when = job.created_at ? new Date(job.created_at * 1000).toLocaleString(undefined, {
    day: "numeric", month: "short", hour: "numeric", minute: "2-digit" }) : null;
  return (
    <div className={s.meta}>
      <h2 className={s.title}>
        <a href={`/lesson/${encodeURIComponent(job.job_id)}`} target="_blank" rel="noreferrer">
          {job.credit?.creator || job.clip_id.slice(0, 10)}
        </a>
        <span className={job.confirmed ? s.badgeOn : s.badge}>{job.confirmed ? "confirmed" : "not yet confirmed"}</span>
      </h2>
      <p className="meta">
        {[
          job.bpm ? `${Math.round(job.bpm)} counts a minute` : null,
          job.seconds_per_count ? `one count ${job.seconds_per_count.toFixed(3)} s` : null,
          duration ? `${duration.toFixed(1)} s long` : null,
          when,
          job.credit?.host,
        ].filter(Boolean).join(" · ")}
      </p>
    </div>
  );
}
