-- stepwise, migration 001: the first schema.
--
-- Plain SQL, applied by hand (infrastructure.md §7: "a migration tool is worth
-- adding at the second migration, not the first"). Run with:
--
--     psql "$DATABASE_URL" -f migrations/001_init.sql
--     python3 migrate.py                       # same thing, no psql needed
--
-- Idempotent: every statement is IF NOT EXISTS, so re-running it is a no-op
-- and a half-applied migration can be finished by running it again.
--
-- **No Neon-specific feature is used anywhere in this file**, deliberately.
-- The exit from a managed Postgres is `pg_dump`, and that is only true while
-- the schema is ordinary Postgres (infrastructure.md decision 2). No branching
-- primitives, no `neon_` extensions, no pooled-connection assumptions in the
-- DDL. This applies unchanged to a Postgres 16 container, which is exactly how
-- it was tested before Neon existed.
--
-- The rule this schema follows, and the reason the whole database exists
-- (infrastructure.md §4): Modal Volumes are commit-based and eventually
-- consistent, not a filesystem with working locks. `modal_app.run_clip` already
-- carries a `uploads.reload()` workaround with the comment "this is a Volume,
-- not a queue -- no delivery guarantee beyond eventually consistent". Anything
-- that needs read-after-write, or a uniqueness constraint, belongs here and not
-- there. Anything that is just bytes belongs in R2 or on a Volume, not here.

-- ---------------------------------------------------------------------------
-- Identity. See docs/research/identity-and-analytics.md §4: optional accounts,
-- anonymous by default, and a *creator token* -- not a user -- is what owns a
-- lesson. Signing in binds tokens to an email; nothing is orphaned and no
-- migration screen is ever needed, because the tokens are already in the
-- browser's hands.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS users (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    -- citext would be nicer but it is an extension; lower-casing on write is
    -- one line in the app and keeps `pg_dump | psql` working on a bare server.
    email       text NOT NULL UNIQUE,
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- A creator token is a capability, not an identity: the same shape as the
-- share link, but held privately and never put in a URL. Only its hash is
-- stored, so a database leak does not hand over the ability to delete or
-- restore anyone's lessons.
CREATE TABLE IF NOT EXISTS creator_tokens (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    token_hash   bytea NOT NULL UNIQUE,
    -- NULL until someone chooses to sign in. §512(i) needs *something* to
    -- terminate; this is that something, and it exists with or without an
    -- email attached.
    user_id      uuid REFERENCES users(id) ON DELETE SET NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz,
    -- The repeat-infringer hook (identity-and-analytics.md §4.2). Blocked
    -- tokens keep their rows: the point of a termination policy is that the
    -- record of it survives.
    blocked_at   timestamptz
);
CREATE INDEX IF NOT EXISTS creator_tokens_user_idx ON creator_tokens(user_id);

-- Magic-link sessions. Single-use token, HttpOnly cookie, no passwords.
CREATE TABLE IF NOT EXISTS sessions (
    token_hash  bytea PRIMARY KEY,
    user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  timestamptz NOT NULL DEFAULT now(),
    expires_at  timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_expires_idx ON sessions(expires_at);

-- ---------------------------------------------------------------------------
-- Clips and the dedupe index.
--
-- This must preserve services/motion-api/fingerprint.py's behaviour exactly,
-- not reinvent it: `same_clip()` is the arbiter and stays the arbiter. Two
-- fields, two jobs:
--
--   * `content_sha256 UNIQUE` catches a byte-identical re-upload with a
--     database constraint, which is the one thing the JSON index on a Volume
--     genuinely cannot do (retention.py's own note: "two uploads landing at
--     the same moment can lose one entry").
--   * `fingerprint jsonb` carries the whole perceptual fingerprint document
--     unchanged -- dHash frames, duration, and whatever fingerprint.py adds
--     later -- so the candidate scan is still `fingerprint.same_clip(entry, fp)`
--     over rows instead of over a JSON file. Same function, same thresholds,
--     same measured behaviour; only the container changed.
--
-- `dhash_prefix` is the scan narrower, not the matcher. It is the first frame's
-- leading bits, so a candidate lookup reads a handful of rows instead of every
-- row, and `same_clip` then decides. A prefix miss must never be treated as a
-- non-match on its own -- that would silently change what dedupe catches.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS clips (
    clip_id         text PRIMARY KEY,
    content_sha256  text NOT NULL UNIQUE,
    fingerprint     jsonb NOT NULL,
    dhash_prefix    bigint,
    bytes           bigint,
    duration_s      double precision,
    -- Nullable: uploading signed out is the default, not the exception.
    creator_token_id uuid REFERENCES creator_tokens(id) ON DELETE SET NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS clips_dhash_prefix_idx ON clips(dhash_prefix);
CREATE INDEX IF NOT EXISTS clips_creator_idx ON clips(creator_token_id);

-- ---------------------------------------------------------------------------
-- Jobs -- the replacement for `{job_id}.job-status.json` on the results Volume.
--
-- The columns are exactly job-status.schema.json's seven fields, so
-- `GET /jobs/{job_id}` assembles a byte-identical document from a row and
-- W7's ProcessingScreen.tsx cannot tell the difference. `schema_version` is not
-- a column: it is a constant in the contract, and storing a constant per row is
-- how a constant stops being one.
--
-- The CHECK constraints are the schema's own rules, enforced by the database
-- rather than by whoever writes next:
--   * error is non-null only when the job failed
--   * progress is within [0,1]
-- Both are things the JSON file could not enforce and did not.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS jobs (
    job_id        text PRIMARY KEY,
    clip_id       text NOT NULL,
    state         text NOT NULL CHECK (state IN ('queued', 'processing', 'succeeded', 'failed')),
    stage_message text NOT NULL DEFAULT '',
    progress      double precision CHECK (progress IS NULL OR (progress >= 0 AND progress <= 1)),
    error         jsonb,
    retry_count   integer NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT jobs_error_only_when_failed
        CHECK ((error IS NULL) OR (state = 'failed'))
);
CREATE INDEX IF NOT EXISTS jobs_clip_idx ON jobs(clip_id);
-- The sweeper and any "what is stuck" query want the non-terminal jobs, which
-- are always the small minority. A partial index keeps that cheap forever.
CREATE INDEX IF NOT EXISTS jobs_active_idx ON jobs(updated_at)
    WHERE state IN ('queued', 'processing');

-- ---------------------------------------------------------------------------
-- Lessons -- what a share link resolves to, and where retention's clock lives.
--
-- `last_access_at` is retention.py's clock, moved off `{clip_id}.last-access.json`
-- without changing its meaning: a lesson expires TTL_DAYS after it was last
-- *opened*, not after it was created. retention.TTL_DAYS stays the single
-- source of that number -- it is not duplicated here as a default, because two
-- copies of a retention promise is how the copy in DESIGN.md §7d ends up
-- disagreeing with the code (DESIGN.md §7h).
--
-- `removed_at`/`removed_reason` are the tombstone. It holds a timestamp and a
-- reason word and nothing else: no hashes, no pose, no frames, nothing derived
-- from the person. Rows are NOT deleted on removal -- the tombstone is what
-- lets a share link answer 410 Gone instead of 404, which is both more honest
-- and more useful to whoever is holding the link.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS lessons (
    clip_id        text PRIMARY KEY,
    job_id         text NOT NULL,
    share_slug     text NOT NULL UNIQUE,
    title          text,
    creator_token_id uuid REFERENCES creator_tokens(id) ON DELETE SET NULL,
    created_at     timestamptz NOT NULL DEFAULT now(),
    last_access_at timestamptz NOT NULL DEFAULT now(),
    removed_at     timestamptz,
    removed_reason text
);
-- The sweeper's only query: oldest last_access first, tombstoned rows skipped.
CREATE INDEX IF NOT EXISTS lessons_retention_idx ON lessons(last_access_at)
    WHERE removed_at IS NULL;
CREATE INDEX IF NOT EXISTS lessons_creator_idx ON lessons(creator_token_id);

-- ---------------------------------------------------------------------------
-- Assets -- one row per delivered object, so a deletion is a query rather than
-- a guess. `retention.clip_artifact_paths` currently reconstructs the per-dancer
-- GLB names by listing a Volume and matching a `{clip_id}_track` prefix, because
-- track ids are not knowable from the clip_id. A row per asset removes that
-- guess, which matters most on the path where guessing wrong means a video
-- someone asked to have deleted is still fetchable.
--
-- ON DELETE CASCADE is deliberate even though lessons are tombstoned rather
-- than deleted: it is the safety net for the one case where a row really does
-- go, and it costs nothing.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS assets (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    clip_id    text NOT NULL REFERENCES lessons(clip_id) ON DELETE CASCADE,
    -- 'video' | 'glb' | 'motion_result'. Free text rather than an enum type:
    -- adding a kind should be an INSERT, not an ALTER TYPE that pg_dump has to
    -- replay in the right order.
    kind       text NOT NULL,
    -- 'r2' | 'volume'. Both are live during the migration and old lessons never
    -- move, so the storage system has to be recorded per object rather than
    -- assumed globally.
    backend    text NOT NULL DEFAULT 'r2',
    -- storage.py's key, verbatim. Never a signed or expiring URL: the contract
    -- says an asset id is opaque and immutable, and a row that stored a URL
    -- would quietly make that false.
    key        text NOT NULL,
    bytes      bigint,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (clip_id, kind, key)
);
CREATE INDEX IF NOT EXISTS assets_clip_idx ON assets(clip_id);

-- ---------------------------------------------------------------------------
-- Events -- identity-and-analytics.md §3.6. One table, nine event names,
-- nothing per-person beyond the creator token.
--
-- `day_hash` is hash(daily-rotating-salt + ip + user_agent), computed
-- server-side and never sent to the device. The rotating salt is what makes
-- cross-day linkage impossible by construction, and is also exactly why this
-- column cannot measure retention. That trade-off is the design, not a gap.
--
-- `country` is derived from the IP and then the IP is discarded. There is no
-- column for an IP address here on purpose.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS events (
    id               bigserial PRIMARY KEY,
    occurred_at      timestamptz NOT NULL DEFAULT now(),
    name             text NOT NULL,
    clip_id          text,
    job_id           text,
    creator_token_id uuid REFERENCES creator_tokens(id) ON DELETE SET NULL,
    day_hash         bytea,
    country          text,
    props            jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS events_name_time_idx ON events(name, occurred_at);
CREATE INDEX IF NOT EXISTS events_time_idx ON events(occurred_at);

-- ---------------------------------------------------------------------------
-- Applied-migration ledger. Three columns, no framework. When there is a
-- second migration this becomes worth a tool; until then it is worth a table.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS schema_migrations (
    version    text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO schema_migrations (version) VALUES ('001_init')
    ON CONFLICT (version) DO NOTHING;
