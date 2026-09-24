# Analytics: build it, or use a company's?

Owner question, 2026-09-23. Read with `identity-and-analytics.md` §3 (on `research-identity-analytics`),
which this does not overturn. Constraints: no consent banner, EU/UK visitors possible, free
public site, solo builder, /privacy states only what the code does.

**Status (2026-09-24): superseded by the upgrade path.** Dashboards are PostHog Cloud (US), fed by
server-side forwarding (`analytics.forward`, docs/DEPLOYMENT.md §3.2). Options (b) and (c) below
were built and are now retired: `/admin`, `GET /metrics`, the `report_*` views and the
`stepwise_reader` role are gone (migration `003_retire_report_views`). Neon keeps the events.

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

## Dashboards (owner follow-up: "I want to see dashboards of everything")

| Option | Dashboards | Cost here | What it costs us |
|---|---|---|---|
| **(a) PostHog Cloud EU, cookieless** | Best out of the box: trends, funnels and retention over our own events | $0 inside 1M events a month | A third party receiving every event, a DPA, a new SDK in the bundle, and defaults we must turn off. Cookieless retention is limited to one day. We still write every event call by hand |
| **(b) Our events in Neon + a BI tool** | Grafana Cloud: free, 3 users, has a PostgreSQL data source ([pricing](https://grafana.com/pricing/)). It connects over TLS to a public endpoint; Neon's is public. Grafana's own docs say to give it a user with `SELECT` only ([docs](https://grafana.com/docs/grafana/latest/datasources/postgres/configure/)). Metabase: Cloud Starter is $100 a month after a 14-day trial, or self-hosted for free (needs a server) ([pricing](https://www.metabase.com/pricing/)). Neon's console has a SQL editor but no dashboards. Evidence.dev gives static pages but means another build | $0 with Grafana Cloud | Grafana stores the charts, and the numbers it reads are aggregates we chose. We build the charts ourselves, and funnels are SQL |
| **(c) Our own /admin** | One fixed page of totals | Already built, about 130 lines | Nothing new to trust, but charts are not worth building by hand once (b) exists |
| **(d) Cloudflare Web Analytics** | Its own dashboard for traffic | $0 | Works alongside any of the above |

**What makes (b) safe to hand to a dashboard.** Migration 002 adds six `report_*` views: daily totals, feature use, failures, loops, lesson visits and referrers. Each one aggregates per day, and none exposes a `day_hash` or a raw row. It also adds a `stepwise_reader` role that can `SELECT` those views and nothing else, and the test suite proves it. Its password is set from the owner's secrets, not in git.

## Recommendation

**For dashboards now: (b) with Grafana Cloud's free tier, plus (d) for traffic.** Keep (c) as the backup page that needs no setup. It runs on the same views, so the two always agree. Choose (a) only if hand-written SQL funnels turn out to be the bottleneck.

**On the original question: confirm the hybrid.** Paste the Cloudflare Web Analytics snippet for traffic. It is free, cookieless, and on a host we already name. Adding it is a separate one-line change with a /privacy line. Keep the first-party events for product signals. The evidence gives no reason to stop: going with PostHog-cookieless now would add a processor, a DPA and an SDK, and we would still write every product event by hand. The only thing it saves is the metrics page and the retention job, about 300 lines. **Upgrade path, if we ever want funnels we don't want to write as SQL:** PostHog Cloud EU with `cookieless_mode: "always"`, autocapture, pageleave and recording off, and `person_profiles: "never"`. Forward the same allowlisted events to it, for a fixed number of weeks (§3.5).
