/**
 * Browser error reporting. Next runs this file before hydration.
 *
 * `@sentry/browser`, not `@sentry/nextjs`: the latter wants `withSentryConfig`
 * around next.config.mjs and server/edge instrumentation that does not run in
 * a Cloudflare Worker, and next.config.mjs has already cost two build breaks
 * (its notes (3) and (4)). The `stepwise-web` project is errors only, so the
 * browser SDK is all of it.
 *
 * Off unless NEXT_PUBLIC_SENTRY_DSN was set at BUILD time (next.config.mjs
 * maps it from SENTRY_DSN_WEB). A browser DSN is public by design -- it ships
 * in the bundle -- so this is not a secret, only a switch.
 */
import * as Sentry from "@sentry/browser";

import { scrub } from "./lib/scrub";

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;

if (dsn) {
  const origin = typeof location === "undefined" ? undefined : location.origin;
  Sentry.init({
    dsn,
    release: process.env.NEXT_PUBLIC_STEPWISE_GIT_SHA || undefined,
    environment: process.env.NODE_ENV,
    sendDefaultPii: false,
    // Errors only: no tracing, no replay. Replay would record the paste box.
    tracesSampleRate: 0,
    beforeSend: (event) => scrub(event, origin),
    beforeBreadcrumb: (crumb) => scrub(crumb, origin),
  });
}
