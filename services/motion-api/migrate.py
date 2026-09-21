"""Apply `migrations/*.sql` in order. No framework, no psql binary needed.

    DATABASE_URL=postgresql://... python3 migrate.py           # apply
    DATABASE_URL=postgresql://... python3 migrate.py --check   # report only

Every migration is written to be idempotent (`IF NOT EXISTS` throughout), so
this re-runs safely and a half-applied file is finished by running it again.
The ledger is `schema_migrations`; a version already in it is skipped.

infrastructure.md §7 is explicit that a migration tool is worth adding at the
*second* migration, not the first. This is twenty lines so that "run the
migrations" is one command in the runbook at 2am rather than a psql invocation
somebody has to get right.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parent / "migrations"


def applied(conn) -> set[str]:
    try:
        return {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
    except Exception:  # noqa: BLE001 -- the ledger itself is created by 001
        conn.rollback() if not conn.autocommit else None
        return set()


def main(argv: list[str]) -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set.\n"
              "  Neon:  see docs/DEPLOYMENT.md\n"
              "  local: docker run -d -p 5433:5432 -e POSTGRES_PASSWORD=stepwise postgres:16\n"
              "         DATABASE_URL=postgresql://postgres:stepwise@localhost:5433/postgres")
        return 2

    import psycopg

    files = sorted(MIGRATIONS.glob("*.sql"))
    if not files:
        print(f"no migrations found in {MIGRATIONS}")
        return 1

    with psycopg.connect(url, autocommit=True) as conn:
        done = applied(conn)
        for path in files:
            version = path.stem
            if version in done:
                print(f"  skip   {version} (already applied)")
                continue
            if "--check" in argv:
                print(f"  PENDING {version}")
                continue
            print(f"  apply  {version}")
            # One statement-block per file, one transaction. A migration that
            # fails half way leaves nothing behind rather than a schema nobody
            # can name.
            with conn.transaction():
                conn.execute(path.read_text())
        # Report the end state rather than assuming the writes landed.
        tables = [r[0] for r in conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")]
    print(f"tables: {', '.join(tables)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
