"""First-party product analytics: one table, an allowlist, and some SQL.

docs/research/identity-and-analytics.md §3 is the design and these are its
rules, kept rather than paraphrased:

  * No third-party suite, no autocapture, no session replay, no mouse or
    scroll tracking. An event is one of the names below with the props listed
    for it, validated here; anything else is dropped. (PostHog, when
    POSTHOG_KEY is set, only receives a server-side copy of these accepted
    events for dashboards -- see forward().)
  * Nothing is stored on the device for analytics and nothing is read from it.
    The browser sends a batch of `{name, props}` with no identifier at all.
  * `day_hash` = HMAC(today's salt, ip | user-agent), computed here. The salt
    is random, lives in `analytics_salts` for one UTC day and is then DELETED,
    so after midnight nobody -- including us -- can recompute or link
    yesterday's hashes. That is also why this cannot measure retention (§3.6).
    The IP is never written anywhere.
  * Referrer: host only, never a path or query.
  * Row-level events live 13 months, then `rollup()` folds each day into
    `event_daily` and deletes the rows (modal_app.sweep_expired, daily).

**Degrades to dropping.** No Postgres, or a database error, means the event
is not recorded and the request still succeeds -- analytics must never be the
reason something 500s.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import urllib.request

import jobstore
import ratelimit

# ---------------------------------------------------------------------------
# The allowlist. name -> {prop: validator}. A validator returns the cleaned
# value or raises ValueError; a prop not listed is dropped, a listed one that
# fails drops the whole event.
# ---------------------------------------------------------------------------

_HOST = re.compile(r"^[a-z0-9.-]{1,253}$")


def _host(v):
    v = str(v).strip().lower()
    if v == "" or _HOST.match(v):
        return v
    raise ValueError("host")


def _num(lo, hi, integer=False):
    def check(v):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi:
            raise ValueError("num")
        return int(v) if integer else round(float(v), 2)
    return check


def _bool(v):
    if not isinstance(v, bool):
        raise ValueError("bool")
    return v


def _one_of(*options):
    def check(v):
        if v not in options:
            raise ValueError("enum")
        return v
    return check


VIEWS = ("overlay", "video", "front", "side", "back", "top", "hands", "feet")

CLIENT_EVENTS: dict[str, dict] = {
    "lesson_opened": {"ref": _host},
    "play_seconds": {"seconds": _num(1, 30, integer=True)},
    "loop_created": {"counts": _num(0.5, 2000), "start": _num(0, 2000), "snapped": _bool,
                     "via": _one_of("drag", "count", "marker", "preset", "step", "handoff", "other")},
    "speed_changed": {"speed": _num(0.1, 2)},
    "build_up_toggled": {"on": _bool},
    "click_toggled": {"on": _bool, "mode": _one_of("counts", "ands")},
    "view_toggled": {"view": _one_of(*VIEWS), "on": _bool},
    "tap_on_one": {},
    "count_one_nudged": {"by": _num(-8, 8)},
    "count_one_alternate": {"shift": _num(-16, 16)},
    "dancer_picked": {"persons": _num(1, 20, integer=True), "index": _num(0, 19, integer=True)},
    "link_copied": {},
}
SERVER_EVENTS = ("job_created", "job_finished")

MAX_BATCH = 50           # events per POST; the client sends far fewer
MAX_BODY = 16 * 1024     # bytes
_LESSON = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def validate(item) -> tuple[str, dict, str | None] | None:
    """One client event -> (name, clean props, lesson id) or None to drop it."""
    if not isinstance(item, dict):
        return None
    name, props = item.get("name"), item.get("props") or {}
    schema = CLIENT_EVENTS.get(name) if isinstance(name, str) else None
    if schema is None or not isinstance(props, dict):
        return None
    clean = {}
    try:
        for key, check in schema.items():
            if key in props:
                clean[key] = check(props[key])
    except ValueError:
        return None
    lesson = item.get("lesson")
    lesson = lesson if isinstance(lesson, str) and _LESSON.match(lesson) else None
    return name, clean, lesson


def daily_cap() -> int:
    return int(os.environ.get("STEPWISE_EVENTS_PER_DAY") or 2000)


# ---------------------------------------------------------------------------
# day_hash
# ---------------------------------------------------------------------------

_salt: tuple[dt.date, bytes] | None = None


def _today() -> dt.date:
    return dt.datetime.now(dt.timezone.utc).date()


def _salt_for(conn, day: dt.date) -> bytes:
    """Today's random salt, shared by every replica through the database.
    Any older salt is deleted on the way, so a past day's hash is unrecoverable."""
    global _salt
    if _salt and _salt[0] == day:
        return _salt[1]
    conn.execute("DELETE FROM analytics_salts WHERE day < %s", (day,))
    conn.execute("INSERT INTO analytics_salts (day, salt) VALUES (%s, %s) ON CONFLICT (day) DO NOTHING",
                 (day, secrets.token_bytes(32)))
    salt = conn.execute("SELECT salt FROM analytics_salts WHERE day = %s", (day,)).fetchone()[0]
    _salt = (day, bytes(salt))
    return _salt[1]


def day_hash(salt: bytes, ip: str, user_agent: str) -> bytes:
    return hmac.new(salt, f"{ip}|{user_agent}".encode(), hashlib.sha256).digest()


def _visitor(conn, headers, client_host) -> bytes:
    ip = ratelimit.client_ip(headers, client_host)
    return day_hash(_salt_for(conn, _today()), ip, headers.get("user-agent", ""))


# ---------------------------------------------------------------------------
# writes
# ---------------------------------------------------------------------------

def _guarded(what: str, fn, default=None):
    if not jobstore.postgres_enabled():
        return default
    try:
        return fn()
    except Exception as e:  # noqa: BLE001 -- dropped, never a 500
        print(f"[analytics] {what} dropped: {type(e).__name__}: {e}")
        return default


def record(name: str, props: dict, headers, client_host, *, job_id=None, clip_id=None) -> None:
    """A server-side event (job_created). Best-effort."""
    def run():
        with jobstore.connection() as conn:
            visitor = _visitor(conn, headers, client_host)
            conn.execute("INSERT INTO events (name, job_id, clip_id, day_hash, props) "
                         "VALUES (%s, %s, %s, %s, %s::jsonb)",
                         (name, job_id, clip_id, visitor, json.dumps(props)))
        _forward_soon(visitor, [(name, props, job_id)])
    _guarded(name, run)


_FINISHED: set[tuple[str, int]] = set()


def record_finished(doc: dict, clip_id: str, persons_of) -> None:
    """job_finished, once per (job, attempt), from a terminal job-status the API
    served. `persons_of()` is only called the first time.

    Wall seconds run from this attempt's dispatch row to the moment we first
    SAW the terminal state. ponytail: if nobody was polling (tab closed), that
    is the next lesson open, so it overstates; the worker writing its own
    finish time is the upgrade if the number starts to matter."""
    key = (doc["job_id"], doc.get("retry_count", 0))
    if key in _FINISHED or doc["state"] not in ("succeeded", "failed"):
        return

    def run():
        with jobstore.connection() as conn:
            seen = conn.execute(
                "SELECT 1 FROM events WHERE name = 'job_finished' AND job_id = %s "
                "AND (props->>'retry_count')::int = %s", (key[0], key[1])).fetchone()
            if not seen:
                (wall,) = conn.execute(
                    "SELECT extract(epoch FROM now() - max(occurred_at)) FROM events "
                    "WHERE name = 'dispatch' AND job_id = %s", (key[0],)).fetchone()
                props = {"state": doc["state"], "retry_count": key[1],
                         "error_code": (doc.get("error") or {}).get("code"),
                         "wall_s": round(float(wall)) if wall is not None else None,
                         "persons": persons_of() if doc["state"] == "succeeded" else None}
                # ponytail: two replicas seeing the same finish in the same
                # instant can both insert; one duplicate in a completion rate is
                # noise. An advisory lock is the fix if it ever is not.
                conn.execute("INSERT INTO events (name, job_id, clip_id, props) "
                             "VALUES ('job_finished', %s, %s, %s::jsonb)",
                             (key[0], clip_id, json.dumps(props)))
                # No visitor here (the worker finished it, not a browser): the
                # job id is the PostHog distinct_id.
                _forward_soon(key[0], [("job_finished", props, key[0])])
        _FINISHED.add(key)
    _guarded("job_finished", run)


# ---------------------------------------------------------------------------
# PostHog Cloud (US): dashboards only (docs/research/analytics-options.md,
# "Upgrade path"). Server-side forwarding of rows we already accepted -- no
# browser SDK, no cookies. It gets the same allowlisted props and the same
# day_hash we store, never the IP or user agent: `$ip` is sent as null and
# geoip is off, so the only address PostHog could see is Modal's.
# ---------------------------------------------------------------------------

def posthog_batch(key: str, visitor: bytes | str, rows: list, when: str) -> dict:
    """rows are validate()'s (name, props, lesson) tuples. `visitor` is the
    day_hash, or a job id for job_finished, which has no visitor."""
    distinct = visitor if isinstance(visitor, str) else visitor.hex()
    return {"api_key": key, "batch": [
        {"event": name, "distinct_id": distinct, "timestamp": when,
         "properties": {**props, **({"lesson": lesson} if lesson else {}),
                        "$process_person_profile": False, "$geoip_disable": True, "$ip": None}}
        for name, props, lesson in rows]}


def forward(visitor: bytes | str, rows: list, when: str) -> None:
    """POST the batch to PostHog. No POSTHOG_KEY -> no-op. Runs after the
    response (api.py BackgroundTasks); a failure is logged and dropped."""
    key = os.environ.get("POSTHOG_KEY")
    if not key or not rows:
        return
    host = (os.environ.get("POSTHOG_HOST") or "https://us.i.posthog.com").rstrip("/")
    req = urllib.request.Request(f"{host}/batch/", method="POST",
                                 data=json.dumps(posthog_batch(key, visitor, rows, when)).encode(),
                                 headers={"content-type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=3).close()
    except Exception as e:  # noqa: BLE001 -- dashboards are optional
        print(f"[analytics] posthog forward dropped: {type(e).__name__}: {e}")


def _forward_soon(visitor, rows: list) -> None:
    """forward() off the request thread, for the server-side events, which have
    no BackgroundTasks to hand. No key -> nothing, not even a thread."""
    if os.environ.get("POSTHOG_KEY"):
        threading.Thread(target=forward, daemon=True, args=(
            visitor, rows, dt.datetime.now(dt.timezone.utc).isoformat())).start()


def ingest(body: bytes, headers, client_host, defer=None) -> int:
    """POST /events. Returns how many events were kept; never raises.
    `defer(fn, *args)` (BackgroundTasks.add_task) schedules the PostHog
    forward so it runs after the response, never inside it."""
    if len(body) > MAX_BODY:
        return 0
    try:
        items = json.loads(body)
    except ValueError:
        return 0
    if not isinstance(items, list):
        return 0
    kept = [v for v in map(validate, items[:MAX_BATCH]) if v]
    if not kept:
        return 0

    def run():
        with jobstore.connection() as conn:
            visitor = _visitor(conn, headers, client_host)
            (n,) = conn.execute(
                "SELECT count(*) FROM events WHERE day_hash = %s AND occurred_at >= %s "
                "AND name = ANY(%s)", (visitor, _today(), list(CLIENT_EVENTS))).fetchone()
            room = max(0, daily_cap() - n)
            rows = [(name, lesson, visitor, json.dumps(props)) for name, props, lesson in kept[:room]]
            if rows:
                with conn.cursor() as cur:
                    cur.executemany("INSERT INTO events (name, job_id, day_hash, props) "
                                    "VALUES (%s, %s, %s, %s::jsonb)", rows)
                if defer and os.environ.get("POSTHOG_KEY"):
                    defer(forward, visitor, kept[:room], dt.datetime.now(dt.timezone.utc).isoformat())
            return len(rows)
    return _guarded("batch", run, 0)


# ---------------------------------------------------------------------------
# reads: /metrics
# ---------------------------------------------------------------------------

def admin_ok(headers) -> bool:
    """STEPWISE_ADMIN_KEY via `x-stepwise-admin-key` or HTTP basic (any user).
    Unset -> nobody."""
    key = os.environ.get("STEPWISE_ADMIN_KEY")
    if not key:
        return False
    given = headers.get("x-stepwise-admin-key", "")
    auth = headers.get("authorization", "")
    if not given and auth.lower().startswith("basic "):
        import base64
        try:
            given = base64.b64decode(auth[6:]).decode().partition(":")[2]
        except Exception:  # noqa: BLE001
            given = ""
    return hmac.compare_digest(given.encode(), key.encode())


def metrics(conn, days: int = 30) -> dict:
    """The owner's summary, read from the same report_* views (migration 002)
    a Grafana or Metabase dashboard reads, so the two cannot disagree."""
    since = _today() - dt.timedelta(days=days - 1)
    q = lambda sql: conn.execute(sql, (since,)).fetchall()  # noqa: E731

    daily = q("SELECT day, visitors, uploads, gpu_runs, finished, succeeded FROM report_daily "
              "WHERE day >= %s ORDER BY day DESC")
    finished = sum(r[4] or 0 for r in daily)
    succeeded = sum(r[5] or 0 for r in daily)
    failures = q("SELECT error_code, sum(jobs) FROM report_failures WHERE day >= %s "
                 "GROUP BY 1 ORDER BY 2 DESC LIMIT 10")
    features = q("SELECT name, sum(events), sum(visitors) FROM report_events WHERE day >= %s "
                  "AND name NOT IN ('job_created', 'job_finished') GROUP BY 1 ORDER BY 2 DESC")
    (visits, corrected, median_play) = conn.execute(
        "SELECT count(*), count(*) FILTER (WHERE corrected_count_one), "
        "  percentile_cont(0.5) WITHIN GROUP (ORDER BY play_seconds) "
        "FROM report_lesson_visits WHERE day >= %s", (since,)).fetchone()
    loops = q("SELECT via, snapped, sum(loops) FROM report_loops WHERE day >= %s "
              "GROUP BY 1, 2 ORDER BY 3 DESC")
    lengths = q("SELECT counts, sum(loops) FROM report_loops WHERE day >= %s "
                "GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 5")
    referrers = q("SELECT host, sum(opens) FROM report_referrers WHERE day >= %s "
                  "GROUP BY 1 ORDER BY 2 DESC LIMIT 10")
    return {
        "since": str(since), "days": days,
        "daily": [dict(zip(("day", "visitors", "uploads", "gpu_runs", "finished", "succeeded"),
                           (str(r[0]), *r[1:]))) for r in daily],
        "completion_rate": round(succeeded / finished, 3) if finished else None,
        "jobs_finished": finished,
        "top_failures": [{"code": c, "n": n} for c, n in failures],
        "features": [{"name": n, "events": c, "visitors": v} for n, c, v in features],
        "lesson_visits": visits,
        "count_one_correction_rate": round(corrected / visits, 3) if visits else None,
        "median_play_seconds": median_play,
        "loops": [{"via": v, "snapped": s, "n": n} for v, s, n in loops],
        "loop_lengths": [{"counts": c, "n": n} for c, n in lengths],
        "referrers": [{"host": h, "n": n} for h, n in referrers],
    }


# ---------------------------------------------------------------------------
# retention: 13 months of rows, then daily roll-ups
# ---------------------------------------------------------------------------

def rollup(conn, dry_run: bool = False) -> dict:
    """Fold every whole day older than 13 months into `event_daily`, then delete
    those rows. Whole days only (the cutoff is a midnight), so one day is always
    folded in a single pass and its distinct-visitor count stays exact. One
    transaction: a crash leaves both tables as they were."""
    cutoff = "date_trunc('day', now() - interval '13 months')"
    with conn.transaction():
        (n,) = conn.execute(f"SELECT count(*) FROM events WHERE occurred_at < {cutoff}").fetchone()
        if n and not dry_run:
            # detail: what report_daily / report_failures need after the rows go.
            conn.execute(
                "INSERT INTO event_daily (day, name, detail, n, visitors, seconds) "
                "SELECT occurred_at::date, name, CASE "
                "    WHEN name = 'job_finished' THEN coalesce(props->>'state', '') || ':' || coalesce(props->>'error_code', '') "
                "    WHEN name = 'job_created' AND (props->>'deduplicated')::boolean THEN 'deduplicated' "
                "    ELSE '' END, "
                "  count(*), count(DISTINCT day_hash), sum((props->>'seconds')::numeric) "
                f"FROM events WHERE occurred_at < {cutoff} GROUP BY 1, 2, 3 "
                "ON CONFLICT (day, name, detail) DO NOTHING")
            # A day's visitors across every event: not the sum of per-event visitors.
            conn.execute(
                "INSERT INTO event_daily (day, name, n, visitors) "
                "SELECT occurred_at::date, '_visitors', count(*), count(DISTINCT day_hash) "
                f"FROM events WHERE occurred_at < {cutoff} AND name NOT IN ('dispatch', 'removal') "
                "GROUP BY 1 ON CONFLICT (day, name, detail) DO NOTHING")
            conn.execute(f"DELETE FROM events WHERE occurred_at < {cutoff}")
        conn.execute("DELETE FROM analytics_salts WHERE day < %s", (_today(),))
    return {"rolled_up_rows": n, "dry_run": dry_run}
