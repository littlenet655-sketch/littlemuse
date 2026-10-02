"""Reset all LittleNet user/demo state while keeping schema and learning banks.

This is intentionally destructive and is only for the college/demo database.
It refuses to execute unless the caller supplies the exact confirmation phrase.
"""
from __future__ import annotations

import argparse
import os
from urllib.parse import urlparse

from database.connection import get_db_connection

CONFIRMATION = "RESET_ALL_ACCOUNTS"
OPTIONAL_STATE_TABLES = (
    "deleted_posts",
    "media_delete_outbox",
    "admin_audit_logs",
)


def _database_label() -> str:
    url = (os.getenv("DATABASE_URL") or "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is not configured")
    parsed = urlparse(url)
    host = parsed.hostname or "unknown-host"
    database = (parsed.path or "/unknown-db").lstrip("/")
    return f"{host}/{database}"


def _count_users(cur) -> dict[str, int]:
    cur.execute(
        """
        SELECT role, COUNT(*)::int AS n
        FROM users
        GROUP BY role
        ORDER BY role
        """
    )
    counts = {"CHILD": 0, "PARENT": 0, "ADMIN": 0}
    for row in cur.fetchall() or []:
        counts[str(row["role"])] = int(row["n"])
    return counts


def reset_all_accounts(confirm: str, *, dry_run: bool = False) -> dict:
    if confirm != CONFIRMATION:
        raise RuntimeError(
            f"Refusing destructive reset. Pass --confirm {CONFIRMATION} exactly."
        )

    target = _database_label()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.users') AS users")
            if not (cur.fetchone() or {}).get("users"):
                raise RuntimeError("This database does not contain the LittleNet users table")

            before = _count_users(cur)
            optional_present = []
            for table in OPTIONAL_STATE_TABLES:
                cur.execute("SELECT to_regclass(%s) AS table_name", (f"public.{table}",))
                if (cur.fetchone() or {}).get("table_name"):
                    optional_present.append(table)

            if dry_run:
                conn.rollback()
                return {
                    "ok": True,
                    "dry_run": True,
                    "database": target,
                    "accounts_before": before,
                    "optional_state_tables": optional_present,
                }

            # users is the ownership root for LittleNet. PostgreSQL TRUNCATE ...
            # CASCADE clears every FK-linked account/post/message/relationship/
            # moderation/session row atomically. Curated non-FK tombstone/audit
            # tables are reset separately below.
            cur.execute("TRUNCATE TABLE users RESTART IDENTITY CASCADE")
            for table in optional_present:
                cur.execute(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE')

            after = _count_users(cur)
        conn.commit()
        return {
            "ok": True,
            "dry_run": False,
            "database": target,
            "accounts_before": before,
            "accounts_after": after,
            "preserved": ["quizzes", "learning_challenges", "schema", "migrations"],
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Reset LittleNet college/demo accounts")
    parser.add_argument("--confirm", default="", help=f"must equal {CONFIRMATION}")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = reset_all_accounts(args.confirm, dry_run=args.dry_run)
    print(result)


if __name__ == "__main__":
    main()
