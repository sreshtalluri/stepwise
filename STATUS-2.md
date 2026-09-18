# Master account/key checklist

## Required now for private alpha

[ ] GitHub account
[ ] Vercel account
[ ] Railway account
[ ] Cloudflare account
[ ] Cloudflare R2 bucket

Collect:

# Cloudflare R2
CLOUDFLARE_ACCOUNT_ID=
S3_ENDPOINT_URL=
S3_REGION=auto
S3_BUCKET=stepwise-mesh
S3_ACCESS_KEY_ID=
S3_SECRET_ACCESS_KEY=

# Railway
RAILWAY_API_DOMAIN=

# Vercel
NEXT_PUBLIC_MESH_API_URL=

## Required before public production

[ ] Railway Postgres
[ ] Modal account
[ ] Auth provider
[ ] Error tracking
[ ] Domain/DNS
[ ] Model commercial licenses, if needed

Collect:

# Railway Postgres
DATABASE_URL=

# Modal
MODAL_GPU_WORKER_URL=
MODAL_GPU_WORKER_TOKEN=

# Auth provider
AUTH_SECRET=
AUTH_CLIENT_ID=
AUTH_CLIENT_SECRET=
NEXT_PUBLIC_AUTH_PUBLISHABLE_KEY=

# Monitoring
SENTRY_DSN=
NEXT_PUBLIC_SENTRY_DSN=

———

# Recommended exact order

Do this in this order:

1. Push repo to GitHub.
2. Create Cloudflare account.
3. Create R2 bucket: stepwise-mesh.
4. Create R2 Object Read & Write API credentials.
5. Configure R2 CORS for localhost first.
6. Create Railway account/project.
7. Deploy services/mesh-api to Railway.
8. Add R2 env vars to Railway.
9. Generate Railway API domain.
10. Test Railway /health and /v1/models.
11. Create Vercel account/project.
12. Deploy apps/web to Vercel.
13. Set NEXT_PUBLIC_MESH_API_URL to Railway domain.
14. Add Vercel domain to Railway CORS_ORIGINS.
15. Add Vercel domain to R2 CORS.
16. Test private alpha upload → R2 → job → viewer.
17. Add auth/rate limits before sharing publicly.
18. Implement Postgres job store.
19. Provision Railway Postgres and set DATABASE_URL.
20. Split Railway API and worker.
21. Implement Modal GPU worker.
22. Create Modal account/secrets and set MODAL_* vars.
23. Run real model/license review.
24. Add monitoring, cleanup, and cost limits.
25. Run private beta.
26. Public launch only after concurrency and abuse controls are proven.

## Bottom line

For private alpha, create:

GitHub + Cloudflare R2 + Railway + Vercel

For real production, also add:

Railway Postgres + Modal + Auth + Monitoring + Model licenses

And the biggest thing to remember: do not treat the current app as production-ready for concurrent users
until jobs are durable in Postgres and processed by a background worker instead of inside the request
path.