"use client";

/**
 * Next 16 prerenders a `/_global-error` route and fails the build if the app does
 * not define one. Copy follows DESIGN.md §11: say what happened and what to do,
 * never apologise, no exclamation marks.
 */
export default function GlobalError({ reset }: { error: Error; reset: () => void }) {
  return (
    <html lang="en">
      <body>
        <main className="lesson">
          <header className="lesson-head">
            <h1 className="title">The lesson stopped loading</h1>
            <p className="sub">Reload to try again. Your clip is not affected.</p>
          </header>
          <div className="chips">
            <button className="chip" onClick={reset}>
              Reload the lesson
            </button>
          </div>
        </main>
      </body>
    </html>
  );
}
