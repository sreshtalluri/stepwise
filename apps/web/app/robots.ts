import type { MetadataRoute } from "next";

/**
 * Lessons, processing pages, the owner's dashboard and the API proxy stay out
 * of search (docs/legal/legal-public-learning.md §6(a)1). The landing page,
 * /upload and /privacy stay crawlable. /lesson and /job also send noindex
 * (next.config.mjs headers, and their layouts' metadata).
 */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: { userAgent: "*", allow: "/", disallow: ["/lesson/", "/job/", "/admin", "/api/"] },
  };
}
