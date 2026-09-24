import { execSync } from "node:child_process";
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
 * 2. `/api/*` is a proxy to services/motion-api: app/api/[...path]/route.ts.
 *
 * It was a rewrite here until the proxy needed to add server-side headers
 * (the origin key and the learner's IP, for the rate limit) -- a rewrite
 * cannot. The target is MOTION_API_URL, read at runtime: wrangler.jsonc
 * `vars` in the Worker, the shell env (default 127.0.0.1:8811) in dev.
 *
 * @type {import('next').NextConfig}
 */
const APP_DIR = path.dirname(fileURLToPath(import.meta.url));

/**
 * The commit being built, for Sentry's `release`. Same rule as
 * services/motion-api/modal_app.py: `-dirty` when the tree has uncommitted
 * changes, nothing at all when there is no git, never a guess.
 */
function gitSha() {
  try {
    const run = (cmd) => execSync(cmd, { cwd: APP_DIR, stdio: ["ignore", "pipe", "ignore"] }).toString().trim();
    const sha = run("git rev-parse HEAD");
    return run("git status --porcelain") ? `${sha}-dirty` : sha;
  } catch {
    return "";
  }
}

export default {
  reactStrictMode: true,
  turbopack: { root: path.resolve(APP_DIR, "..", "..") },

  /**
   * 5. Browser Sentry (instrumentation-client.ts). Inlined at build time, so
   * these have to be in the environment of `npm run cf:build`, e.g. with
   * ~/.stepwise-secrets/sentry.env sourced. No DSN -> Sentry stays off.
   */
  env: {
    NEXT_PUBLIC_SENTRY_DSN: process.env.NEXT_PUBLIC_SENTRY_DSN ?? process.env.SENTRY_DSN_WEB ?? "",
    NEXT_PUBLIC_STEPWISE_GIT_SHA: gitSha(),
  },

  /**
   * 3. `outputFileTracingRoot` is deliberately NOT set here. Do not add it.
   *
   * It looks like the fix for the Cloudflare build: Next emits the standalone
   * tree at `.next/standalone/apps/web/.next/` (because it infers the repo as
   * the workspace root), while OpenNext looks for `.next/standalone/.next/`
   * (because it finds the root by walking up for a *lockfile*, and
   * `apps/web/package-lock.json` is the first hit). Pointing this at the app
   * directory makes the two agree on paper.
   *
   * In Next 16 it also clamps module resolution, overriding `turbopack.root`
   * above, so every `../../../packages/navigation/...` import in (1) fails with
   * "Module not found" -- five of them, and the build never reaches the step
   * the setting was added to fix. The two are not independent knobs here.
   *
   * The path mismatch is reconciled in `scripts/flatten-standalone.mjs`
   * instead, which is why `cf:build` runs the Next build itself rather than
   * letting `opennextjs-cloudflare build` drive it.
   */

  /**
   * 4. Standalone output, only for the Cloudflare build.
   *
   * `opennextjs-cloudflare build` normally injects this itself when it drives
   * the Next build. `cf:build` drives the Next build instead (see (3)), so it
   * has to be asked for here -- and asked for *conditionally*, because plain
   * `next build` is what CI and `npm run build` run, and neither has any use
   * for a second full copy of the server tree on disk.
   */
  output: process.env.STEPWISE_CF_BUILD ? "standalone" : undefined,

  /**
   * 6. Lessons and processing pages stay out of search
   * (docs/legal/legal-public-learning.md §6(a)1). The header covers what a
   * meta tag cannot (a crawler that skips HTML); the pages' layouts carry the
   * meta tag too; robots.ts leaves them crawlable so the noindex is seen. OpenNext applies these
   * (@opennextjs/aws core/routing/matcher.js getNextConfigHeaders).
   */
  async headers() {
    const noindex = [{ key: "X-Robots-Tag", value: "noindex, nofollow" }];
    return [
      { source: "/lesson/:path*", headers: noindex },
      { source: "/job/:path*", headers: noindex },
    ];
  },

};
