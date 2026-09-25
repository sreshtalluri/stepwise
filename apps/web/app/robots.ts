import type { MetadataRoute } from "next";

/**
 * The API proxy is never crawled. /lesson and /job
 * are NOT disallowed here on purpose: they send noindex (next.config.mjs
 * headers and their layouts' metadata), and a crawler blocked by robots.txt
 * never fetches the page, never sees the noindex, and can still list the bare
 * URL (docs/legal/legal-public-learning.md §6(a)1). /owner is the exception:
 * the owner's tool holds nobody's video in its URL, so there is nothing a bare
 * listing would leak, and it is both disallowed and noindex.
 */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: { userAgent: "*", allow: "/", disallow: ["/api/", "/owner"] },
  };
}
