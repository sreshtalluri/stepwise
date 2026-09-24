"use client";

import * as Sentry from "@sentry/browser";
import { useEffect } from "react";
import StateScreen from "../components/StateScreen";
import { PRODUCT_NAME, site } from "../lib/copy";
// global-error replaces layout.tsx when it renders, so layout's stylesheets
// and font links are not there: bring both here.
import "./globals.css";
import "./front.css";

/**
 * A render crash anywhere. Next 16 prerenders a `/_global-error` route and
 * fails the build if the app does not define one. It wraps every route, so the
 * copy never says "lesson". The button really reloads the page: Next's
 * retry() only re-renders, which rarely helps after a crash.
 */
export default function GlobalError({ error }: { error: Error & { digest?: string } }) {
  // A render error is caught by this boundary, so it never reaches the SDK's
  // global handler on its own. `digest` links it to the server-side log line.
  useEffect(() => {
    Sentry.captureException(error, { tags: { boundary: "global-error", digest: error.digest } });
  }, [error]);

  const copy = site.crashed;
  return (
    <html lang="en">
      <head>
        <title>{PRODUCT_NAME}</title>
        {/* Same fonts as layout.tsx. */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wdth,wght@12..96,75..100,400..800&display=swap"
        />
        <link rel="stylesheet" href="https://api.fontshare.com/v2/css?f[]=switzer@400,500,600,700&display=swap" />
      </head>
      <body>
        <StateScreen pose="sitback" title={copy.title} body={copy.body}
          action={{ label: copy.action, onClick: () => window.location.reload() }} />
      </body>
    </html>
  );
}
