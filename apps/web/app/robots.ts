import type { MetadataRoute } from "next";

/**
 * The owner's dashboard and the API proxy are never crawled. /lesson and /job
 * are NOT disallowed here on purpose: they send noindex (next.config.mjs
 * headers and their layouts' metadata), and a crawler blocked by robots.txt
 * never fetches the page, never sees the noindex, and can still list the bare
 * URL (docs/legal/legal-public-learning.md §6(a)1).
 */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: { userAgent: "*", allow: "/", disallow: ["/admin", "/api/"] },
  };
}
