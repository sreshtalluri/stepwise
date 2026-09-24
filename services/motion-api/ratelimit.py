"""Who may start a GPU run, and how many runs a day there are.

Every reconstruction is ~$0.08 of L40S (api.py's measured $0.0839), and a
public URL means anyone can loop a script at `POST /clips`. Two ceilings:

    per client IP   STEPWISE_LIMIT_IP_HOUR   (default 5)   -- a learner making
                    STEPWISE_LIMIT_IP_DAY    (default 20)     a lesson takes minutes
                                                              each; 5 an hour is
                                                              generous, 20 a day is
                                                              a whole practice night
    everyone        STEPWISE_LIMIT_GLOBAL_DAY (default 200) -- worst case $17/day,
                                                              ~$500/month, and the
                                                              only ceiling a spoofed
                                                              header cannot dodge

**Only a real dispatch is charged.** `charge()` is called at the top of
`api._store_and_dispatch`, i.e. after both dedupe layers have said "no existing
lesson". A dedupe hit spends no GPU, so it spends no quota either -- re-opening
a lesson you (or a friend) already made must never be what locks you out.

**Storage: the `events` table, no new schema.** A dispatch is recorded as one
`events` row, `name = 'dispatch'`, with `day_hash` = HMAC(secret, UTC date + IP).
That is 001_init.sql's own privacy rule applied here: the IP is hashed with a
salt that rotates daily and then discarded -- there is still no IP column
anywhere. Two differences from the analytics day_hash, both deliberate: the
user agent is left out (it is one header to change, so it would make the limit
optional), and the secret is server-side so the 2^32 IPv4 space cannot simply
be hashed through. `events` rows are not deleted by a removal, so taking a
lesson down does not refund its dispatch.

ponytail: the daily salt means the per-IP counts reset at UTC midnight rather
than rolling -- the price of cross-day unlinkability. Accepted.

**Degrades to allow.** No Postgres (the Volume job backend) means no shared
counter across Modal replicas, and an in-memory one would be a limit per
container, which is not a limit. So it allows, and says so once in the log --
the same stance /health takes on missing config. A database error on the way
also allows (logged every time): a DB hiccup must not take uploads down.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import os

import jobstore

# An arbitrary constant: one advisory lock serialises charge() across replicas
# so two simultaneous requests cannot both read "199" and both dispatch.
_LOCK_KEY = 0x5354_4550  # "STEP"

_warned = False


class Limited(Exception):
    def __init__(self, code: str, message: str, retry_after: int):
        super().__init__(code)
        self.code, self.message, self.retry_after = code, message, retry_after


def _limit(name: str, default: int) -> int:
    return int(os.environ.get(name) or default)


def origin_key_ok(headers) -> bool:
    """True when this request came through the Cloudflare Worker.

    The Worker (apps/web/app/api/[...path]/route.ts) adds
    `x-stepwise-origin-key`; STEPWISE_ORIGIN_KEY (Modal Secret `stepwise-origin`)
    is the same value. Unset means dev/local: everything is "from the Worker".
    """
    key = os.environ.get("STEPWISE_ORIGIN_KEY")
    if not key:
        return True
    return hmac.compare_digest(headers.get("x-stepwise-origin-key", ""), key)


def client_ip(headers, client_host: str | None) -> str:
    """The address to charge.

    Behind the Worker, the socket peer is Cloudflare and so is any
    CF-Connecting-IP on a Worker subrequest (a fixed Workers egress address,
    which would put every learner in one bucket). So the Worker forwards the
    learner's address as `x-stepwise-client-ip`, and that header is believed
    ONLY alongside a valid origin key -- anyone else could set it. Without
    the Worker (dev, or no key configured) the socket peer is the caller:
    Modal's asgi proxy puts the real address in request.client.host (checked
    live, 2026-09-23).
    """
    if os.environ.get("STEPWISE_ORIGIN_KEY") and origin_key_ok(headers):
        forwarded = headers.get("x-stepwise-client-ip", "").strip()
        if forwarded:
            return forwarded
    return client_host or "unknown"


def _ip_hash(ip: str, today: dt.date) -> bytes:
    secret = os.environ.get("STEPWISE_IP_SALT") or os.environ.get("DATABASE_URL", "")
    return hmac.new(secret.encode(), f"{today.isoformat()}|{ip}".encode(), hashlib.sha256).digest()


def _loosely(seconds: int) -> str:
    # DESIGN.md §7c: time stated loosely, never a countdown.
    return "in about an hour" if seconds <= 3600 else f"in about {round(seconds / 3600)} hours"


def check(ip: str) -> None:
    """Raise Limited if `ip` could not dispatch now; record nothing.

    For work that costs us before the dispatch does -- the link door's
    download. charge() still decides at dispatch; this only stops an IP that
    is already over from making us fetch a video first.
    """
    _guarded(lambda: _charge(ip, None, None))


def charge(ip: str, job_id: str, clip_id: str) -> None:
    """Record one dispatch for `ip`, or raise Limited without recording it."""
    _guarded(lambda: _charge(ip, job_id, clip_id))


def charge_removal(ip: str, clip_id: str, relationship: str) -> None:
    """Record one takedown for `ip`, or raise Limited without recording it.

    A removal deletes a lesson for everyone holding its link, and with no
    accounts anyone holding the link can ask (OPEN-DECISIONS D5/D7). One
    person clearing out every lesson they were shared is the abuse this caps:
    STEPWISE_LIMIT_REMOVALS_IP_DAY (default 5). Same `events` table, same
    daily-salted day_hash, name 'removal'; `props` holds the relationship
    category only -- never the free-text reason.
    """
    _guarded(lambda: _charge_removal(ip, clip_id, relationship))


def _guarded(fn) -> None:
    global _warned
    if not jobstore.postgres_enabled():
        if not _warned:
            print("[ratelimit] no postgres job backend -- dispatch limits are OFF")
            _warned = True
        return
    try:
        fn()
    except Limited:
        raise
    except Exception as e:  # noqa: BLE001
        print(f"[ratelimit] could not check limits, allowing: {type(e).__name__}: {e}")


def _charge(ip: str, job_id: str, clip_id: str) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    ip_hash = _ip_hash(ip, now.date())
    midnight = dt.datetime.combine(now.date() + dt.timedelta(days=1), dt.time(), dt.timezone.utc)
    ip_hour, ip_day, global_day = (_limit("STEPWISE_LIMIT_IP_HOUR", 5),
                                   _limit("STEPWISE_LIMIT_IP_DAY", 20),
                                   _limit("STEPWISE_LIMIT_GLOBAL_DAY", 200))

    with jobstore.connection() as conn, conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (_LOCK_KEY,))

        def window(hours: int, by_ip: bool):
            sql = ("SELECT count(*), min(occurred_at) FROM events "
                   "WHERE name = 'dispatch' AND occurred_at > now() - make_interval(hours => %s)")
            args: tuple = (hours,)
            if by_ip:
                sql += " AND day_hash = %s"
                args += (ip_hash,)
            return conn.execute(sql, args).fetchone()

        def wait(oldest, hours: int, cap=None) -> int:
            # When the oldest counted dispatch ages out, a slot frees up.
            free_at = (oldest or now) + dt.timedelta(hours=hours)  # None: a limit of 0
            if cap is not None:
                free_at = min(free_at, cap)
            return max(60, int((free_at - now).total_seconds()))

        n, oldest = window(24, by_ip=False)
        if n >= global_day:
            s = wait(oldest, 24)
            raise Limited("daily_limit_reached",
                          "New lessons are paused for now — today's limit is reached. "
                          f"Try again {_loosely(s)}. Lessons already made still open.", s)
        n, oldest = window(24, by_ip=True)
        if n >= ip_day:
            s = wait(oldest, 24, cap=midnight)  # the salt rotates at midnight
            raise Limited("too_many_lessons",
                          f"You have started {ip_day} lessons today, which is the limit. "
                          f"Try again {_loosely(s)}.", s)
        n, oldest = window(1, by_ip=True)
        if n >= ip_hour:
            s = wait(oldest, 1, cap=midnight)
            raise Limited("too_many_lessons",
                          f"You have started {ip_hour} lessons this hour, which is the limit. "
                          f"Try again {_loosely(s)}.", s)

        if job_id is None:
            return  # check(): nothing to record
        conn.execute("INSERT INTO events (name, clip_id, job_id, day_hash) "
                     "VALUES ('dispatch', %s, %s, %s)", (clip_id, job_id, ip_hash))


def _charge_removal(ip: str, clip_id: str, relationship: str) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    ip_hash = _ip_hash(ip, now.date())
    midnight = dt.datetime.combine(now.date() + dt.timedelta(days=1), dt.time(), dt.timezone.utc)
    cap = _limit("STEPWISE_LIMIT_REMOVALS_IP_DAY", 5)
    with jobstore.connection() as conn, conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (_LOCK_KEY,))
        n = conn.execute("SELECT count(*) FROM events WHERE name = 'removal' AND day_hash = %s "
                         "AND occurred_at > now() - interval '24 hours'", (ip_hash,)).fetchone()[0]
        if n >= cap:
            # The salt rotates at midnight, so that is when this IP's count resets.
            s = max(60, int((midnight - now).total_seconds()))
            raise Limited("too_many_removals",
                          f"You have removed {cap} lessons today, which is the limit. "
                          f"Try again {_loosely(s)}.", s)
        conn.execute("INSERT INTO events (name, clip_id, day_hash, props) "
                     "VALUES ('removal', %s, %s, %s::jsonb)",
                     (clip_id, ip_hash, json.dumps({"relationship": relationship})))
