"""Initialize the LittleNet PostgreSQL baseline schema (legacy bootstrap).

MIGRATION OWNERSHIP: dbmate owns every schema change adopted after 2026-09-06.
This script applies ONLY the blessed legacy baseline, in this order:

  1. database/schema.sql
  2. database/upgrade.sql
  3. database/friendship_upgrade.sql
  4. (only with --seed) database/seed.sql

On a fresh database the required order is::

    python tools/init_db.py
    dbmate --no-dump-schema --migrations-dir db/migrations up

Never run ``dbmate up`` alone on an empty database: the migrations are deltas,
not a full baseline (no migration creates the ``users`` table, for example).

Safety contract:
  * Idempotent: every statement in the legacy files must be safely re-runnable
    (``IF NOT EXISTS`` / ``ON CONFLICT DO NOTHING`` / convergent data repair).
  * Never destructive: the script refuses to run if any legacy file contains a
    top-level ``DROP TABLE`` / ``DROP SCHEMA`` / ``TRUNCATE`` / ``DELETE FROM``
    outside a function body. Destructive changes belong in dbmate migrations,
    never in this bootstrap.
  * Loud on inconsistent migration state: when dbmate's ``schema_migrations``
    table exists, every recorded version must correspond to a migration file in
    ``db/migrations/`` and the adoption marker (20260906180000) must be present
    whenever later migrations are recorded. Anything else raises instead of
    silently papering over a broken history.
"""
from pathlib import Path
import argparse
import re
import sys

root = Path(__file__).parents[1]
sys.path.insert(0, str(root))
from dotenv import load_dotenv

load_dotenv(root / '.env')
from database.connection import get_db_connection

ADOPTION_MARKER = "20260906180000"
LEGACY_FILES = [
    "database/schema.sql",
    "database/upgrade.sql",
    "database/friendship_upgrade.sql",
]

# Top-level destructive statements. The scan runs on SQL with comments and
# dollar-quoted function bodies stripped, so trigger bodies (e.g. the
# friendship delete-pair trigger) do not trip the guard.
_DESTRUCTIVE_RE = re.compile(
    r"\bDROP\s+(TABLE|SCHEMA)\b|\bTRUNCATE\b|\bDELETE\s+FROM\b",
    re.IGNORECASE,
)
_DOLLAR_QUOTE_RE = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$")


def _strip_sql_noise(sql: str) -> str:
    """Remove line/block comments and dollar-quoted bodies for safety scans."""
    out = []
    i, n = 0, len(sql)
    while i < n:
        if sql.startswith("--", i):
            j = sql.find("\n", i)
            i = n if j == -1 else j + 1
            continue
        if sql.startswith("/*", i):
            j = sql.find("*/", i + 2)
            i = n if j == -1 else j + 2
            continue
        m = _DOLLAR_QUOTE_RE.match(sql, i)
        if m:
            tag = m.group(0)
            j = sql.find(tag, m.end())
            i = n if j == -1 else j + len(tag)
            continue
        out.append(sql[i])
        i += 1
    return "".join(out)


def _assert_legacy_files_safe() -> None:
    """Refuse to run the bootstrap if a legacy file turned destructive."""
    for name in LEGACY_FILES:
        sql = (root / name).read_text(encoding="utf-8")
        cleaned = _strip_sql_noise(sql)
        hit = _DESTRUCTIVE_RE.search(cleaned)
        if hit:
            raise RuntimeError(
                f"Refusing to run legacy bootstrap: {name} contains a top-level "
                f"destructive statement ({hit.group(0)!r}). Destructive schema "
                "changes belong in db/migrations/ (dbmate), never in the "
                "idempotent baseline files."
            )


def _on_disk_migration_versions() -> set:
    versions = set()
    migrations_dir = root / "db" / "migrations"
    if migrations_dir.is_dir():
        for path in migrations_dir.glob("*.sql"):
            m = re.match(r"^(\d+)_", path.name)
            if m:
                versions.add(m.group(1))
    return versions


def _assert_migration_state_consistent(cur) -> None:
    """Error loudly when dbmate history disagrees with this checkout.

    Running the legacy bootstrap on a database whose migration history came
    from a different checkout (or a hand-edited schema_migrations table) must
    fail here instead of letting a later ``dbmate up`` mis-apply migrations.
    """
    cur.execute("SELECT to_regclass('public.schema_migrations') AS rel")
    row = cur.fetchone()
    if not row or not row["rel"]:
        return  # dbmate has never run here; `dbmate up` applies the baseline.
    cur.execute("SELECT version FROM schema_migrations")
    recorded = {str(r["version"]) for r in cur.fetchall()}
    known = _on_disk_migration_versions()
    unknown = sorted(recorded - known)
    if unknown:
        raise RuntimeError(
            "Refusing legacy bootstrap: schema_migrations records versions "
            f"with no matching file in db/migrations/: {unknown}. The database "
            "was migrated by a different checkout; reconcile migration history "
            "before proceeding."
        )
    if recorded and ADOPTION_MARKER not in recorded:
        raise RuntimeError(
            "Refusing legacy bootstrap: schema_migrations is missing the dbmate "
            f"adoption marker {ADOPTION_MARKER} while later migrations are "
            "recorded. Migration history is out of order; reconcile it before "
            "proceeding."
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Initialize/update LittleNet PostgreSQL baseline schema."
    )
    parser.add_argument(
        "--seed",
        action="store_true",
        help="also insert the academic demo quiz seed data",
    )
    args = parser.parse_args()

    _assert_legacy_files_safe()

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            _assert_migration_state_consistent(cur)
            for name in LEGACY_FILES:
                cur.execute((root / name).read_text(encoding="utf-8"))
            if args.seed:
                cur.execute((root / "database/seed.sql").read_text(encoding="utf-8"))
        conn.commit()
        print(
            "LittleNet database baseline initialized."
            + (" Demo seed applied." if args.seed else "")
            + " Next: dbmate --no-dump-schema --migrations-dir db/migrations up"
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
