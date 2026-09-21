import path from "node:path";
import { fileURLToPath } from "node:url";

/**
 * `root` is the repo, not this app.
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
 * @type {import('next').NextConfig}
 */
export default {
  reactStrictMode: true,
  turbopack: { root: path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..") },
};
