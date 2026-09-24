import type { Metadata } from "next";

// The processing page for someone's video: never in search
// (docs/legal/legal-public-learning.md §6(a)1; app/robots.ts, next.config.mjs).
export const metadata: Metadata = { robots: { index: false, follow: false } };

export default function JobLayout({ children }: { children: React.ReactNode }) {
  return children;
}
