import type { Metadata } from "next";

// The owner's tool: unlinked, never in search (robots.ts, next.config.mjs).
export const metadata: Metadata = { title: "Owner: count 1", robots: { index: false, follow: false } };

export default function OwnerLayout({ children }: { children: React.ReactNode }) {
  return children;
}
