-- stepwise, migration 002: what first-party analytics needs beyond `events`.
-- analytics.py is the code; identity-and-analytics.md §3.6 is the design.
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
-- `detail` is '' or, for job_finished, 'state:error_code'. Counts only: no
-- hashes, no lesson ids.
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

INSERT INTO schema_migrations (version) VALUES ('002_analytics')
    ON CONFLICT (version) DO NOTHING;
