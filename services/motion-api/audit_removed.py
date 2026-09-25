"""Which removed lessons still have bytes somewhere -- and, with --fix, remove them.

    python3 audit_removed.py            # read-only report
    python3 audit_removed.py --fix      # run retention.delete_clip on each one found

A removal leaves exactly one thing: `{clip_id}.removed.json`. This lists every
clip with a tombstone and anything else still keyed by it, in all four places a
lesson lives -- the results Volume, the uploads Volume, R2, and Postgres (the
`jobs` row, plus the not-yet-used `lessons`/`assets`/`clips` tables) -- and the
content fingerprint in `/fingerprints/index.json`. job_6037... is the case this
exists for: a lesson whose job wrote its files after it was removed.

`--fix` runs the same idempotent `retention.delete_clip` the takedown runs. It
keeps the tombstone (its time and reason are the record), deletes everything
else, and is safe to run twice.

Needs a Modal token (for the Volumes). R2 and Postgres are read from the
environment, or from ~/.stepwise-secrets/{r2,neon}.env when unset; a store
whose credentials are missing is reported as "not checked", never as clean.
`events` rows are counted but not flagged: the rate limiter and analytics keep
them across a removal by design (ratelimit.py).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

SECRETS = Path.home() / ".stepwise-secrets"


def _load_env(name: str) -> None:
    """KEY=value lines into os.environ, without overriding and without echoing."""
    path = SECRETS / name
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _pg_rows(clip_id: str, job_ids: list[str]) -> dict | None:
    if not os.environ.get("DATABASE_URL"):
        return None
    import psycopg
    out = {}
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        conn.execute("SET default_transaction_read_only = on")
        out["jobs"] = [r[0] for r in conn.execute(
            "SELECT job_id FROM jobs WHERE clip_id = %s OR job_id = ANY(%s)", (clip_id, job_ids))]
        for table in ("lessons", "assets", "clips"):
            (n,) = conn.execute(f"SELECT count(*) FROM {table} WHERE clip_id = %s", (clip_id,)).fetchone()
            if n:
                out[table] = n
        (out["events (kept by design)"],) = conn.execute(
            "SELECT count(*) FROM events WHERE clip_id = %s OR job_id = ANY(%s)",
            (clip_id, job_ids)).fetchone()
    return out


def audit(results, uploads) -> list[dict]:
    import retention
    import storage

    listing = [e.path.lstrip("/") for e in results.listdir("/")]
    uploaded = {e.path.lstrip("/") for e in uploads.listdir("/")}
    index = retention.read_index(results)
    r2_on = storage.enabled()

    report = []
    for tomb in sorted(n for n in listing if n.endswith(".removed.json")):
        clip_id = tomb[: -len(".removed.json")]
        job_ids = sorted({f"job_{clip_id}"} | {e["job_id"] for e in index
                                                if e.get("clip_id") == clip_id and e.get("job_id")})
        found = {}
        paths = set()
        for job_id in job_ids:
            paths |= set(retention.clip_artifact_paths(listing, clip_id, job_id)["results"])
        found["results"] = sorted(p.lstrip("/") for p in paths if p.lstrip("/") in listing)
        found["uploads"] = sorted({f"{clip_id}.mp4"} & uploaded)
        found["fingerprint"] = [e.get("job_id") for e in index if e.get("clip_id") == clip_id]
        found["r2"] = storage.clip_keys(clip_id) if r2_on else None
        found["postgres"] = _pg_rows(clip_id, job_ids)
        doc = retention.read_json(results, f"/{tomb}") or {}
        survivors = (found["results"] or found["uploads"] or found["fingerprint"] or found["r2"]
                     or any(v for k, v in (found["postgres"] or {}).items() if "kept by design" not in k))
        report.append({"clip_id": clip_id, "job_ids": job_ids, "removed_at": doc.get("removed_at"),
                       "reason": doc.get("reason"), "found": found, "dirty": bool(survivors)})
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--fix", action="store_true",
                    help="run the idempotent retention.delete_clip on every removed lesson with survivors")
    args = ap.parse_args()

    for name in ("r2.env", "neon.env"):
        _load_env(name)
    import modal

    import retention
    import storage

    results = modal.Volume.from_name("stepwise-results")
    uploads = modal.Volume.from_name("stepwise-uploads")
    report = audit(results, uploads)
    print(f"{len(report)} removed lessons; R2 {'checked' if storage.enabled() else 'NOT checked (no credentials)'}, "
          f"Postgres {'checked' if os.environ.get('DATABASE_URL') else 'NOT checked (no DATABASE_URL)'}\n")
    import datetime
    for r in report:
        when = (datetime.datetime.fromtimestamp(r["removed_at"], datetime.timezone.utc).isoformat(timespec="seconds")
                if r["removed_at"] else "?")
        print(f"{'SURVIVORS' if r['dirty'] else 'clean    '}  {r['clip_id']}  removed {when}  ({r['reason']!r})")
        for where, what in r["found"].items():
            if what:
                print(f"             {where}: {what}")
    dirty = [r for r in report if r["dirty"]]
    print(f"\n{len(dirty)} of {len(report)} removed lessons still have bytes somewhere.")

    if args.fix and dirty:
        for r in dirty:
            for job_id in r["job_ids"]:
                out = retention.delete_clip(uploads, results, r["clip_id"], job_id, "")
                print(f"fixed {r['clip_id']} ({job_id}): deleted {out['deleted']}")
        print("\nre-auditing...")
        left = [r["clip_id"] for r in audit(results, uploads) if r["dirty"]]
        print(f"{len(left)} still dirty{': ' + ', '.join(left) if left else ''}")
        return 1 if left else 0
    return 1 if dirty else 0


if __name__ == "__main__":
    sys.exit(main())
