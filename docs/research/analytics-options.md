# Analytics: build it, or use a company's?

Owner question, 2026-09-23. Read with `identity-and-analytics.md` §3 (on `research-identity-analytics`),
which this does not overturn. Constraints: no consent banner, EU/UK visitors possible, free
public site, solo builder, /privacy states only what the code does.

## What we already pay for (or get free)

| Service | Gives analytics? |
|---|---|
| **Sentry** | No. Errors, traces, replays, profiles, logs; no product events or funnels ([docs](https://docs.sentry.io/product/)). Ours is errors-only, replay off (`instrumentation-client.ts`). |
| **Neon** | No. It is the Postgres the events table lives in. |
| **Modal** | GPU spend and run counts in its dashboard. Nothing about visitors. |
| **Cloudflare Web Analytics** | Traffic, yes. Free. Page views, visits, referrer, country, device, Core Web Vitals ([metrics](https://developers.cloudflare.com/web-analytics/data-metrics/)). No cookies or localStorage and no fingerprinting; a "visit" is a page view with an off-site referrer ([Cloudflare blog](https://blog.cloudflare.com/the-rum-diaries-enabling-web-analytics-by-default/)). Works on a non-proxied site, so a workers.dev Worker too, by pasting a JS snippet ([setup](https://developers.cloudflare.com/web-analytics/get-started/)). **No custom events** ([FAQ](https://developers.cloudflare.com/web-analytics/faq/)). Sampled after 7 days. |

## The alternatives

- **PostHog Cloud (EU).** Free tier: 1M events a month and 5K recordings ([pricing](https://posthog.com/pricing)). Out of the box it does the things §3.4 rules out: autocapture, pageleave and session recording are all on, and persistence is cookie plus localStorage ([config](https://posthog.com/docs/libraries/js/config)). `cookieless_mode: "always"` stores nothing on the device and counts users with a daily-rotating hash on PostHog's servers. It needs a project setting turned on, and `identify` no longer works ([tutorial](https://posthog.com/tutorials/cookieless-tracking)). That gets rid of the banner. It still makes PostHog a data processor: we would need a DPA, a new named recipient on /privacy, and a new SDK in the bundle. Our questions would still need the same `track()` calls by hand, because autocapture cannot tell which counts someone looped or that they corrected count 1.
- **Plausible Cloud.** Costs $9 a month for 10k page views. No cookies, hosted in the EU, and it has goals ([pricing](https://plausible.io/#pricing)). It measures traffic well and product questions poorly.
- **Umami** (self-hosted or cloud). MIT and cookieless. It is the escape hatch that §3.5 already approved. It adds nothing that Cloudflare's free tier plus our own events does not already give us.
- **First-party events in our Postgres.** Takes about a day to build. Zero dollars, no new processor, and it answers every product question directly: which stretches people loop, the count-1 correction rate, completion rate, failure codes, play time. What we give up is ready-made funnels and charts, and cross-day retention, which no cookieless option can measure.

## What each option answers

| Question | CF Web Analytics | First-party | PostHog cookieless |
|---|---|---|---|
| Traffic, referrers, countries, page speed | yes | referrer host only | yes |
| Failure reasons, completion, GPU cost | no | yes (server-side) | only if we send it |
| Loops, count-1 corrections, play time | no | yes | yes, with the same hand-written events |
| Funnels and dashboards | no | SQL and a small /admin page | yes |
| Retention across days | no | no, by design | no in cookieless mode |

## Recommendation

**Confirm the hybrid.** Paste the Cloudflare Web Analytics snippet for traffic. It is free, cookieless, and on a host we already name. Adding it is a separate one-line change with a /privacy line. Keep the first-party events for product signals. The evidence gives no reason to stop: going with PostHog-cookieless now would add a processor, a DPA and an SDK, and we would still write every product event by hand. The only thing it saves is the metrics page and the retention job, about 300 lines. **Upgrade path, if we ever want funnels we don't want to write as SQL:** PostHog Cloud EU with `cookieless_mode: "always"`, autocapture, pageleave and recording off, and `person_profiles: "never"`. Forward the same allowlisted events to it, for a fixed number of weeks (§3.5).
