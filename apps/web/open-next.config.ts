// The OpenNext adapter that turns `next build` output into a Cloudflare Worker.
//
// Deliberately empty. The defaults give a Worker that serves the static assets
// off Cloudflare's CDN and runs everything else -- the server components, the
// `/api/*` rewrite -- in workerd.
//
// What is NOT configured, and why:
//   * No incremental cache. `app/lesson/[lesson]` is prerendered at build time
//     by generateStaticParams, so it ships as a static asset and never needs
//     revalidating at runtime. An R2 or KV cache binding here would be a
//     binding to maintain for a cache with nothing to put in it. The moment a
//     route becomes ISR, this is where `incrementalCache` goes.
//   * No queue and no tag cache, for the same reason: both exist to serve
//     on-demand revalidation, which nothing here uses.
import { defineCloudflareConfig } from "@opennextjs/cloudflare";

export default defineCloudflareConfig();
