"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import LessonViewer from "./LessonViewer";
import RemoveLessonDialog from "./RemoveLessonDialog";
import LessonLoading from "./LessonLoading";
import StateScreen from "./StateScreen";
import { LESSONS, lessonSource, parseCredit, type Credit } from "../lib/lessons";
import { captureThumb, forgetLesson, hasThumb, recordOpened } from "../lib/myLessons";
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
  const [reporting, setReporting] = useState(false);
  const [credit, setCredit] = useState<Credit | null>(null);
  const router = useRouter();
  // Built-in examples are static files: nothing on the server to remove, and
  // they are listed as examples rather than in My lessons.
  const isExample = Object.hasOwn(LESSONS, lessonId);

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

  // The creator credit, beside the document rather than in it: MotionResult is
  // a strict contract. An uploaded file answers 404 and gets no line.
  useEffect(() => {
    if (!source.creditUrl) return;
    let cancelled = false;
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

  // "My lessons" (lib/myLessons.ts): remember a job lesson on this device when
  // it opens; forget it when its link says it was removed. Fixtures are listed
  // as examples already.
  useEffect(() => {
    if (Object.hasOwn(LESSONS, lessonId)) return;
    if (load.kind === "error" && load.status === 410) forgetLesson(lessonId);
    if (load.kind !== "ok") return;
    recordOpened({
      id: lessonId,
      title: source.title ?? lessonCopy.load.jobTitle,
      durationS: load.doc.source_video.duration_s,
      dancers: load.doc.persons.length,
    });
    if (!hasThumb(lessonId)) captureThumb(lessonId, source.videoUrl);
  }, [load, lessonId, source.title, source.videoUrl]);

  if (load.kind === "ok") {
    return (
      <>
      <LessonViewer
        doc={load.doc}
        lessonId={lessonId}
        title={source.title ?? lessonCopy.load.jobTitle}
        videoUrl={source.videoUrl}
        credit={credit}
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

function LoadFailed({ status, lessonId }: { status: number; lessonId: string }) {
  const copy = lessonCopy.load;
  if (status === 409) {
    return (
      <StateScreen pose="sit" title={copy.notReady} body={copy.notReadyBody}
        action={{ label: copy.notReadyLink, href: `/job/${encodeURIComponent(lessonId)}` }} />
    );
  }
  if (status === 410) {
    return <StateScreen pose="wave" title={copy.removed} body={copy.removedBody} action={{ label: copy.removedLink, href: "/" }} />;
  }
  if (status === 404) {
    return <StateScreen pose="shrug" title={copy.notFound} body={copy.notFoundBody} action={{ label: copy.notFoundLink, href: "/upload" }} />;
  }
  return (
    <StateScreen pose="look" title={copy.failed} body={copy.failedBody} alert
      action={{ label: copy.failedLink, onClick: () => window.location.reload() }} />
  );
}
