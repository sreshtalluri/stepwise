-- stepwise, migration 002: what first-party analytics needs beyond `events`.
-- analytics.py is the code; identity-and-analytics.md §3.6 is the design;
-- docs/research/analytics-options.md is why dashboards read the views below.
-- Idempotent like 001: `python3 migrate.py` re-runs it safely.

-- One random salt per UTC day for day_hash = HMAC(salt, ip | user-agent).
-- Rows older than today are deleted (analytics._salt_for, and the daily
-- sweeper), so a past day's hashes cannot be recomputed or linked by anyone.
CREATE TABLE IF NOT EXISTS analytics_salts (
    day   date PRIMARY KEY,
    salt  bytea NOT NULL
);

-- Row-level events live 13 months; then each whole day is folded in here and
-- the rows are deleted (analytics.rollup, from modal_app.sweep_expired).
-- `detail` is 'state:error_code' for job_finished, 'deduplicated' for a
-- deduplicated job_created, else ''. The '_visitors' row is the day's distinct
-- visitors across every event. Counts only: no hashes, no lesson ids.
CREATE TABLE IF NOT EXISTS event_daily (
    day       date NOT NULL,
    name      text NOT NULL,
    detail    text NOT NULL DEFAULT '',
    n         bigint NOT NULL,
    visitors  bigint NOT NULL,
    seconds   numeric,
    PRIMARY KEY (day, name, detail)
);

-- The per-visitor daily cap and the job_finished once-only check.
CREATE INDEX IF NOT EXISTS events_day_hash_idx ON events(day_hash, occurred_at);
CREATE INDEX IF NOT EXISTS events_job_idx ON events(job_id, name) WHERE job_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- Reporting views: the ONLY thing a dashboard (Grafana, Metabase, /admin) reads.
-- Aggregates per day, never a day_hash, never a raw row. 'dispatch' and
-- 'removal' are ratelimit.py's rows (a different hash), so they are left out
-- of visitor counts. Where a view unions in `event_daily`, it covers every day
-- ever; the rest cover the 13 months of rows.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW report_daily AS
SELECT occurred_at::date AS day,
       count(DISTINCT day_hash) FILTER (WHERE name NOT IN ('dispatch', 'removal')) AS visitors,
       count(*) FILTER (WHERE name = 'job_created') AS uploads,
       count(*) FILTER (WHERE name = 'job_created'
                        AND NOT coalesce((props->>'deduplicated')::boolean, false)) AS gpu_runs,
       count(*) FILTER (WHERE name = 'job_finished') AS finished,
       count(*) FILTER (WHERE name = 'job_finished' AND props->>'state' = 'succeeded') AS succeeded
FROM events GROUP BY 1
UNION ALL
SELECT day,
       sum(visitors) FILTER (WHERE name = '_visitors')::bigint,
       sum(n) FILTER (WHERE name = 'job_created')::bigint,
       sum(n) FILTER (WHERE name = 'job_created' AND detail = '')::bigint,
       sum(n) FILTER (WHERE name = 'job_finished')::bigint,
       sum(n) FILTER (WHERE name = 'job_finished' AND detail LIKE 'succeeded%')::bigint
FROM event_daily GROUP BY 1;

-- Feature use: events and visitors per name per day.
CREATE OR REPLACE VIEW report_events AS
SELECT occurred_at::date AS day, name, count(*) AS events, count(DISTINCT day_hash) AS visitors
FROM events WHERE name NOT IN ('dispatch', 'removal') GROUP BY 1, 2
UNION ALL
SELECT day, name, sum(n)::bigint, sum(visitors)::bigint FROM event_daily
WHERE name NOT IN ('dispatch', 'removal', '_visitors') GROUP BY 1, 2;

CREATE OR REPLACE VIEW report_failures AS
SELECT occurred_at::date AS day, coalesce(props->>'error_code', '(none)') AS error_code, count(*) AS jobs
FROM events WHERE name = 'job_finished' AND props->>'state' = 'failed' GROUP BY 1, 2
UNION ALL
SELECT day, coalesce(nullif(split_part(detail, ':', 2), ''), '(none)'), sum(n)::bigint
FROM event_daily WHERE name = 'job_finished' AND detail LIKE 'failed%' GROUP BY 1, 2;

CREATE OR REPLACE VIEW report_loops AS
SELECT occurred_at::date AS day, props->>'via' AS via, (props->>'snapped')::boolean AS snapped,
       (props->>'counts')::float AS counts, count(*) AS loops
FROM events WHERE name = 'loop_created' GROUP BY 1, 2, 3, 4;

-- One row per lesson visit (one visitor, one lesson, one day), without the
-- hash: enough to take a median or a rate over any range.
CREATE OR REPLACE VIEW report_lesson_visits AS
SELECT d AS day, lesson, play_seconds, corrected_count_one
FROM (
    SELECT occurred_at::date AS d, day_hash, job_id AS lesson,
           bool_or(name = 'lesson_opened') AS opened,
           coalesce(sum((props->>'seconds')::int) FILTER (WHERE name = 'play_seconds'), 0) AS play_seconds,
           bool_or(name IN ('tap_on_one', 'count_one_nudged', 'count_one_alternate')) AS corrected_count_one
    FROM events WHERE job_id IS NOT NULL AND name NOT IN ('dispatch', 'removal', 'job_created', 'job_finished')
    GROUP BY 1, 2, 3
) v WHERE opened;

CREATE OR REPLACE VIEW report_referrers AS
SELECT occurred_at::date AS day, coalesce(nullif(props->>'ref', ''), '(direct)') AS host, count(*) AS opens
FROM events WHERE name = 'lesson_opened' GROUP BY 1, 2;

-- The dashboard login. Created without a password or LOGIN here, because a
-- password in git is a password for everyone: docs/DEPLOYMENT.md §3.1 sets it
-- (ALTER ROLE ... LOGIN PASSWORD) from a value that lives only in the owner's
-- secrets. It can read the report_* views and nothing else.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'stepwise_reader') THEN
        CREATE ROLE stepwise_reader NOLOGIN;
    END IF;
END $$;
GRANT USAGE ON SCHEMA public TO stepwise_reader;
GRANT SELECT ON report_daily, report_events, report_failures, report_loops,
                report_lesson_visits, report_referrers TO stepwise_reader;

INSERT INTO schema_migrations (version) VALUES ('002_analytics')
    ON CONFLICT (version) DO NOTHING;
