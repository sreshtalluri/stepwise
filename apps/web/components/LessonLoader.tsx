"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import LessonViewer from "./LessonViewer";
import { lessonSource } from "../lib/lessons";
import { lesson as lessonCopy } from "../lib/copy";
import type { MotionResult } from "../lib/motion";

type Load =
  | { kind: "loading" }
  | { kind: "ok"; doc: MotionResult }
  | { kind: "error"; status: number };

/**
 * Resolves a lesson id in the browser: a fixture's static JSON, or a job's
 * MotionResult from the API. Status codes are services/motion-api's —
 * 409 not succeeded yet, 410 removed, 404 unknown; anything else is "reload".
 */
export default function LessonLoader({ lessonId }: { lessonId: string }) {
  const source = lessonSource(lessonId);
  const [load, setLoad] = useState<Load>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    setLoad({ kind: "loading" });
    fetch(source.docUrl, { cache: "no-store" })
      .then(async (res) => {
        if (!res.ok) return { kind: "error", status: res.status } as const;
        const doc = (await res.json()) as MotionResult;
        // Shallow guard, same reasoning as isJobStatus in lib/jobStatus.ts.
        if (!Array.isArray(doc?.persons)) return { kind: "error", status: 0 } as const;
        return { kind: "ok", doc } as const;
      })
      .catch(() => ({ kind: "error", status: 0 }) as const)
      .then((next) => {
        if (!cancelled) setLoad(next);
      });
    return () => {
      cancelled = true;
    };
  }, [source.docUrl]);

  if (load.kind === "ok") {
    return (
      <LessonViewer
        doc={load.doc}
        lessonId={lessonId}
        title={source.title ?? lessonCopy.load.jobTitle}
        videoUrl={source.videoUrl}
        glbUrls={source.glbUrls(load.doc)}
      />
    );
  }

  const copy = lessonCopy.load;
  const job = encodeURIComponent(lessonId);
  return (
    <main className="wrap app-screen">
      {load.kind === "loading" ? (
        <p className="muted" aria-live="polite">
          {copy.loading}
        </p>
      ) : load.status === 409 ? (
        <>
          <h1 className="app-title">{copy.notReady}</h1>
          <Link href={`/job/${job}`} className="btn" style={{ marginTop: 20 }}>
            {copy.notReadyLink}
          </Link>
        </>
      ) : load.status === 410 ? (
        <h1 className="app-title">{copy.removed}</h1>
      ) : load.status === 404 ? (
        <>
          <h1 className="app-title">{copy.notFound}</h1>
          <Link href="/upload" className="btn" style={{ marginTop: 20 }}>
            {copy.notFoundLink}
          </Link>
        </>
      ) : (
        <h1 className="app-title" role="alert">
          {copy.failed}
        </h1>
      )}
    </main>
  );
}
