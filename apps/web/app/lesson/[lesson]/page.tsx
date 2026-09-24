import LessonLoader from "../../../components/LessonLoader";
import { LESSONS } from "../../../lib/lessons";

// Prerenders the fixture shells. Any other id is a job_id, rendered on demand;
// the document itself is always fetched in the browser (components/LessonLoader).
export function generateStaticParams() {
  return Object.keys(LESSONS).map((lesson) => ({ lesson }));
}

export default async function LessonPage({ params }: { params: Promise<{ lesson: string }> }) {
  const { lesson } = await params;
  return <LessonLoader lessonId={lesson} />;
}
