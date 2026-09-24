"use client";

import * as Sentry from "@sentry/browser";
import { useEffect } from "react";

/**
 * Next 16 prerenders a `/_global-error` route and fails the build if the app does
 * not define one. Copy follows DESIGN.md §11: say what happened and what to do,
 * never apologise, no exclamation marks.
 */
export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  // A render error is caught by this boundary, so it never reaches the SDK's
  // global handler on its own. `digest` links it to the server-side log line.
  useEffect(() => {
    Sentry.captureException(error, { tags: { boundary: "global-error", digest: error.digest } });
  }, [error]);

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
