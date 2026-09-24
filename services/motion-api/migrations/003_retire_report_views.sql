-- stepwise, migration 003: retire the Grafana / /admin read path (2026-09-24).
-- Dashboards are PostHog now (analytics.forward, docs/DEPLOYMENT.md §3.2), so
-- the report_* views from 002 and the stepwise_reader login that read them go.
-- Nothing in the app reads them: analytics.rollup writes event_daily straight
-- from `events`. events, event_daily, analytics_salts and the roll-up stay.
-- Idempotent like 001/002.

DROP VIEW IF EXISTS report_daily, report_events, report_failures, report_loops,
                    report_lesson_visits, report_referrers;

-- The views' grants went with them; what is left is the schema grant (and a
-- database CONNECT, if one was ever given by hand). A role holding privileges
-- cannot be dropped, and REVOKE on a missing role is an error, so all of it
-- waits for the existence check.
DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'stepwise_reader') THEN
        REVOKE ALL ON SCHEMA public FROM stepwise_reader;
        EXECUTE format('REVOKE ALL ON DATABASE %I FROM stepwise_reader', current_database());
        DROP ROLE stepwise_reader;
    END IF;
END $$;

INSERT INTO schema_migrations (version) VALUES ('003_retire_report_views')
    ON CONFLICT (version) DO NOTHING;
