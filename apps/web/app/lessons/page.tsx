import Link from "next/link";
import { LESSONS } from "../../lib/lessons";

/**
 * A plain index of the fixture lessons, for developing the viewer. The real front
 * door — marketing site, upload, processing, reveal — is W7's, at /.
 * This dev index moved from / to /lessons at integration.
 */
export default function Home() {
  return (
    <main className="lesson">
      <header className="lesson-head">
        <h1 className="title">Lesson viewer</h1>
        <p className="sub">Built against the frozen MotionResult v1 fixtures.</p>
      </header>
      <div className="chips">
        {Object.entries(LESSONS).map(([slug, lesson]) => (
          <Link key={slug} className="chip" href={`/lesson/${slug}`}>
            {lesson.title}
          </Link>
        ))}
      </div>
    </main>
  );
}
