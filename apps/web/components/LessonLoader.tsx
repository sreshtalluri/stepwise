"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import LessonViewer from "./LessonViewer";
import RemoveLessonDialog from "./RemoveLessonDialog";
import LessonLoading from "./LessonLoading";
import { LoadFailed } from "./StateScreen";
import { LESSONS, lessonSource, parseCredit, type Credit } from "../lib/lessons";
import { captureThumb, forgetLesson, hasThumb, recordOpened } from "../lib/myLessons";
import { lesson as lessonCopy } from "../lib/copy";
import { forgetLessonDoc, loadLessonDoc } from "../lib/lessonDoc";
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
  const [reporting, setReporting] = useState(false);
  /** undefined while GET /source is out; null for an upload (404) or a fixture. */
  const [credit, setCredit] = useState<Credit | null | undefined>(source.creditUrl ? undefined : null);
  const router = useRouter();
  // Built-in examples are static files: nothing on the server to remove, and
  // they are listed as examples rather than in My lessons.
  const isExample = Object.hasOwn(LESSONS, lessonId);

  useEffect(() => {
    let cancelled = false;
    setLoad({ kind: "loading" });
    // Joins the processing screen's prefetch when there was one; retries a
    // transient failure either way (lib/lessonDoc.ts).
    loadLessonDoc(source.docUrl).then((next) => {
      if (cancelled) return;
      forgetLessonDoc(source.docUrl);
      setLoad(next);
    });
    return () => {
      cancelled = true;
    };
  }, [source.docUrl]);

  // The creator credit, beside the document rather than in it: MotionResult is
  // a strict contract. An uploaded file answers 404 and gets no line.
  useEffect(() => {
    if (!source.creditUrl) return setCredit(null);
    let cancelled = false;
    setCredit(undefined);
    fetch(source.creditUrl)
      .then((res) => (res.ok ? res.json() : null))
      .catch(() => null)
      .then((c) => {
        if (!cancelled) setCredit(parseCredit(c));
      });
    return () => {
      cancelled = true;
    };
  }, [source.creditUrl]);

  // A link lesson is named for its post ("@handle on TikTok · Choreo @x"); an
  // upload is "Your dance".
  const title = source.title ?? (credit ? lessonCopy.creditTitle(credit) : lessonCopy.load.jobTitle);

  // "My lessons" (lib/myLessons.ts): remember a job lesson on this device when
  // it opens; forget it when its link says it was removed. Fixtures are listed
  // as examples already. Recorded once the credit has answered, so the name is
  // the post's, and an entry saved as "Your dance" before this gets its name on open.
  useEffect(() => {
    if (Object.hasOwn(LESSONS, lessonId)) return;
    if (load.kind === "error" && load.status === 410) forgetLesson(lessonId);
    if (load.kind !== "ok" || credit === undefined) return;
    recordOpened({
      id: lessonId,
      title,
      durationS: load.doc.source_video.duration_s,
      dancers: load.doc.persons.length,
    });
    if (!hasThumb(lessonId)) captureThumb(lessonId, source.videoUrl);
  }, [load, lessonId, title, credit, source.videoUrl]);

  if (load.kind === "ok") {
    return (
      <>
      <LessonViewer
        doc={load.doc}
        lessonId={lessonId}
        title={title}
        videoUrl={source.videoUrl}
        credit={credit ?? null}
        glbUrls={source.glbUrls(load.doc)}
        onRemoveFromMyLessons={isExample ? undefined : () => {
          forgetLesson(lessonId);
          router.push("/lessons");
        }}
        onReportOrRemove={isExample ? undefined : () => setReporting(true)}
      />
      {isExample ? null : (
        <RemoveLessonDialog jobId={lessonId} open={reporting} onClose={() => setReporting(false)} />
      )}
      </>
    );
  }

  if (load.kind === "loading") return <LessonLoading />;

  return <LoadFailed status={load.status} lessonId={lessonId} />;
}
