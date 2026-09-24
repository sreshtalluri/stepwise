// Move `.next/standalone/apps/web/*` up to `.next/standalone/*`.
//
// Next and OpenNext disagree about where the standalone tree lives, and both
// are internally consistent:
//
//   * Next bases it on the inferred workspace root. `next.config.mjs` sets
//     `turbopack.root` to the repo (the sibling packages are plain directories
//     reached by relative path, with no workspace and no node_modules link), so
//     the tree comes out at `.next/standalone/apps/web/.next/`.
//   * OpenNext computes `path.relative(monorepoRoot, appBuildOutputPath)` and
//     finds `monorepoRoot` by walking up for a lockfile. `apps/web` has its own
//     `package-lock.json`, so it stops there, concludes the prefix is empty,
//     and reads `.next/standalone/.next/`.
//
// Neither has a knob that fixes it. `outputFileTracingRoot` looks like the one,
// and in Next 16 it also clamps module resolution and breaks every sibling
// import -- see next.config.mjs (3). Making OpenNext agree instead would mean a
// lockfile at the repo root, i.e. converting to a real npm workspace, which is
// the thing this repo has deliberately not done.
//
// So: let each tool be right, and move the directory in between. Runs after
// `next build` and before `opennextjs-cloudflare build --skipNextBuild`.
//
// ponytail: a move, not a symlink. Symlinks would survive a re-run without the
// idempotence check below, but OpenNext copies out of this tree and the AWS
// helper it shares does not consistently follow links.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const APP_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const STANDALONE = path.join(APP_DIR, ".next", "standalone");
const NESTED = path.join(STANDALONE, "apps", "web");

if (!fs.existsSync(STANDALONE)) {
  console.error(
    "flatten-standalone: no .next/standalone.\n" +
      "  `next build` must run with STEPWISE_CF_BUILD=1 for `output: \"standalone\"`.",
  );
  process.exit(1);
}

// Already flat: either Next stopped nesting (a version bump would do it, and
// this script should then be deleted, not silently kept) or this already ran.
if (!fs.existsSync(NESTED)) {
  if (!fs.existsSync(path.join(STANDALONE, ".next"))) {
    console.error("flatten-standalone: standalone tree has neither apps/web/ nor .next/.");
    process.exit(1);
  }
  console.log("flatten-standalone: already flat, nothing to do");
  process.exit(0);
}

for (const entry of fs.readdirSync(NESTED)) {
  const to = path.join(STANDALONE, entry);
  // The nested tree wins. `.next/standalone/node_modules` is written by the
  // tracer for the whole workspace and must survive; anything that collides
  // with an app-level entry of the same name is the stale outer copy.
  fs.rmSync(to, { recursive: true, force: true });
  fs.renameSync(path.join(NESTED, entry), to);
}

fs.rmSync(path.join(STANDALONE, "apps"), { recursive: true, force: true });

// The one file OpenNext dies on if this is wrong, named explicitly so a future
// failure points here instead of at a stack trace inside @opennextjs/aws.
const manifest = path.join(STANDALONE, ".next", "server", "pages-manifest.json");
if (!fs.existsSync(manifest)) {
  console.error(`flatten-standalone: expected ${path.relative(APP_DIR, manifest)} after flattening`);
  process.exit(1);
}

console.log("flatten-standalone: moved apps/web/* -> .next/standalone/");
