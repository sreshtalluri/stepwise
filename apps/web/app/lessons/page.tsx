"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { LESSONS } from "../../lib/lessons";
import { myLessons as copy } from "../../lib/copy";
import { forgetLesson, listMyLessons, type SavedLesson } from "../../lib/myLessons";
import s from "./lessons.module.css";

/**
 * "My lessons": what this browser has opened (lib/myLessons.ts). No accounts,
 * so nothing to sync and nothing to claim beyond "this device". The generated
 * contract fixtures stay reachable underneath, labelled as examples.
 */
export default function MyLessonsPage() {
  // null until mounted: the server has no localStorage, and rendering the empty
  // state first would flash "no lessons" at someone who has some.
  const [list, setList] = useState<SavedLesson[] | null>(null);
  useEffect(() => setList(listMyLessons()), []);

  const fmtDate = (ms: number) =>
    new Date(ms).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });

  return (
    <main className="wrap app-screen">
      <h1 className="app-title">{copy.title}</h1>
      <p className="muted">{copy.subtitle}</p>

      {list?.length === 0 && (
        <div className="dropzone">
          <p>{copy.empty}</p>
          <Link href="/upload" className="btn" style={{ marginTop: 16 }}>
            {copy.emptyLink}
          </Link>
        </div>
      )}

      {!!list?.length && (
        <>
          <ul className={s.list}>
            {list.map((l) => (
              <li key={l.id} className={s.item}>
                <Link href={`/lesson/${encodeURIComponent(l.id)}`} className={s.open}>
                  {l.thumb ? (
                    // eslint-disable-next-line @next/next/no-img-element -- a data: URL, nothing to optimise
                    <img src={l.thumb} alt="" className={s.thumb} />
                  ) : (
                    <span className={s.thumb} aria-hidden />
                  )}
                  <span>
                    <span className={s.title}>{l.title}</span>
                    <span className="meta">
                      {copy.duration(l.durationS)} · {copy.dancers(l.dancers)} · {copy.opened}{" "}
                      {fmtDate(l.lastOpened)}
                    </span>
                  </span>
                </Link>
                <button
                  type="button"
                  className={s.remove}
                  aria-label={`${copy.remove}: ${l.title}, ${fmtDate(l.lastOpened)}`}
                  onClick={() => {
                    forgetLesson(l.id);
                    setList(listMyLessons());
                  }}
                >
                  {copy.remove}
                </button>
              </li>
            ))}
          </ul>
          <p className="meta" style={{ marginTop: 12 }}>{copy.removeNote}</p>
        </>
      )}

      <section className={s.examples}>
        <h2 className="constraints-heading">{copy.examplesHeading}</h2>
        <p className="meta">{copy.examplesNote}</p>
        <ul className={s.exampleList}>
          {Object.entries(LESSONS).map(([slug, lesson]) => (
            <li key={slug}>
              <Link href={`/lesson/${slug}`}>{lesson.title}</Link>
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
