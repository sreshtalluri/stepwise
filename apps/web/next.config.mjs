import path from "node:path";
import { fileURLToPath } from "node:url";

/**
 * Two unrelated things live here, from two branches.
 *
 * 1. `turbopack.root` is the repo, not this app.
 *
 * `packages/navigation` and `packages/motion-contract` are plain directories —
 * there is no workspace root, no node_modules link, and importing them means a
 * relative path up out of `apps/web`. Turbopack infers its root from the
 * project directory and will not resolve above it, so the first *value* import
 * from a sibling package fails with "Module not found" even though the file is
 * right there.
 *
 * It had never come up before because the only cross-package import in this app
 * was `import type { MotionResult }` in lib/motion.ts — type-only, erased before
 * the bundler ever sees it. `<LessonNavigator>` is the first one that has to
 * survive to runtime.
 *
 * 2. `/api/*` is a proxy to services/motion-api, not a set of route handlers.
 *
 * The app already fetched `/api/jobs/...` from three places with nothing
 * serving them -- W7 built against the recorded fixture, and the wiring was
 * never added. One rewrite is cheaper than a route handler per endpoint and
 * keeps the browser on one origin, so no CORS config is needed on the service.
 *
 * ponytail: a rewrite, not a BFF. It adds no auth, no caching and no request
 * shaping, because there is nothing yet that needs any of those. The moment
 * one endpoint needs a server-side secret (a signed asset URL, an invite code
 * held for the visitor rather than typed by them) this becomes a route handler
 * for that endpoint only, and the rest keep using the rewrite.
 *
 * @type {import('next').NextConfig}
 */
const MOTION_API = process.env.MOTION_API_URL ?? "http://127.0.0.1:8811";

export default {
  reactStrictMode: true,
  turbopack: { root: path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..") },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${MOTION_API}/:path*` }];
  },
};
