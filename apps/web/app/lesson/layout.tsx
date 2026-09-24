import type { Metadata } from "next";

// A lesson is someone's video: unlisted, never in search
// (docs/legal/legal-public-learning.md §6(a)1; app/robots.ts, next.config.mjs).
export const metadata: Metadata = { robots: { index: false, follow: false } };

export default function LessonLayout({ children }: { children: React.ReactNode }) {
  return children;
}
