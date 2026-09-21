import { notFound } from "next/navigation";
import { readFile } from "node:fs/promises";
import path from "node:path";
import LessonViewer from "../../../components/LessonViewer";
import { LESSONS } from "../../../lib/lessons";
import type { MotionResult } from "../../../lib/motion";

export function generateStaticParams() {
  return Object.keys(LESSONS).map((lesson) => ({ lesson }));
}

export default async function LessonPage({ params }: { params: Promise<{ lesson: string }> }) {
  const { lesson } = await params;
  const meta = LESSONS[lesson];
  if (!meta) notFound();

  // Stands in for the job service's "resolve this lesson" call (W4). The viewer
  // itself never assumes where the document came from.
  const file = path.join(process.cwd(), "public", "fixtures", `${lesson}.json`);
  const doc = JSON.parse(await readFile(file, "utf-8")) as MotionResult;

  return (
    <LessonViewer
      doc={doc}
      lessonId={lesson}
      title={meta.title}
      videoUrl={`/fixtures/${lesson}.mp4`}
      glbUrls={doc.persons.map((p) => `/fixtures/${lesson}.${p.person_id}.glb`)}
    />
  );
}
