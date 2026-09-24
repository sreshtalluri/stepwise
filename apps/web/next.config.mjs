import path from "node:path";
import { fileURLToPath } from "node:url";

// This app is one workspace in a repo with no root package.json, so Next infers
// the project root as apps/web and refuses to resolve anything above it. It has
// to: `lib/motion.ts` reads types from packages/motion-contract and the lesson
// page imports the real components from packages/navigation. Type-only imports
// got away with it (they are erased before the bundler sees them); a runtime
// import does not.
const repoRoot = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "..");

/** @type {import('next').NextConfig} */
export default {
  reactStrictMode: true,
  turbopack: { root: repoRoot },
  // `next dev` otherwise writes its own apps/web/AGENTS.md and apps/web/CLAUDE.md
  // on every run. This repo's agent instructions live at the root; a second,
  // framework-authored CLAUDE.md appearing under apps/ is noise that would be
  // committed by accident.
  agentRules: false,
};
