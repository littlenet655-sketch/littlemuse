"""Per-account failed-login throttling for password logins (T1-007).

Design notes
------------
- State is keyed by the canonical users.user_id, so the username and email
  aliases of the same account share one budget and failed attempts accumulate
  across requests and source IPs.
- Concurrency safety comes from a transaction-scoped Postgres advisory lock
  (pg_advisory_xact_lock) per user_id, following the pattern used by the OTP
  resend path (auth/parent_email_otp.py). The lock namespace here is 842102,
  distinct from the OTP resend namespace 842101. A SELECT ... FOR UPDATE on
  the throttle row alone would not be enough: on a first-ever failure the row
  does not exist yet, so the SELECT would lock nothing and two parallel first
  failures could both INSERT — one silently killing the other's count.
- Policy (conservative, security-standard): 5 failed attempts inside a rolling
  15-minute window trigger a 15-minute lockout. A successful authentication
  clears the state. Attempts made while locked do not extend the lockout, so
  an attacker cannot keep an account locked indefinitely.
- Generic failures are preserved end to end: is_locked() returning True makes
  login_user() return None exactly like a wrong password — callers cannot
  distinguish "unknown identifier", "wrong password", "disallowed account" and
  "throttled" from the response. No distinct throttling error is surfaced.
"""

import logging
from datetime import datetime, timedelta, timezone

from database.connection import get_db_connection

logger = logging.getLogger(__name__)

# Conservative security-standard policy: 5 failures in a rolling 15-minute
# window, then a 15-minute lockout. A successful login clears all state.
MAX_FAILED_ATTEMPTS = 5
WINDOW = timedelta(minutes=15)
LOCKOUT = timedelta(minutes=15)

# Advisory-lock namespace for the login throttle. Must not collide with the
# OTP resend namespace (842101) in auth/parent_email_otp.py.
_ADVISORY_LOCK_NAMESPACE = 842102


def _now():
    return datetime.now(timezone.utc)


def _acquire(cur, user_id):
    """Serialize throttle read-modify-write cycles for one user."""
    cur.execute(
        "SELECT pg_advisory_xact_lock(%s, %s)",
        (_ADVISORY_LOCK_NAMESPACE, int(user_id)),
    )


def is_locked(user_id):
    """True when the account is inside an active throttle lockout.

    Fail-closed: on any database error we return True so a DB outage cannot
    be turned into unlimited guessing, and on a missing throttle table the
    login path keeps working (logged) instead of breaking every login.
    """
    conn = get_db_connection()
    if not conn:
        logger.warning("login_throttle: no DB connection; failing closed")
        return True
    try:
        with conn.cursor() as cur:
            _acquire(cur, user_id)
            cur.execute(
                "SELECT locked_until FROM login_throttle WHERE user_id=%s",
                (user_id,),
            )
            row = cur.fetchone()
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        logger.exception("login_throttle: is_locked lookup failed; failing closed")
        return True
    finally:
        try:
            conn.close()
        except Exception:
            pass
    if not row:
        return False
    locked_until = row.get("locked_until") if isinstance(row, dict) else row[0]
    return bool(locked_until) and locked_until > _now()


def record_failure(user_id):
    """Record one failed password attempt for user_id (atomic, concurrent-safe)."""
    conn = get_db_connection()
    if not conn:
        logger.warning("login_throttle: no DB connection; failure not recorded")
        return
    try:
        with conn.cursor() as cur:
            _acquire(cur, user_id)
            cur.execute(
                "SELECT failed_attempts, first_failed_at, locked_until "
                "FROM login_throttle WHERE user_id=%s",
                (user_id,),
            )
            row = cur.fetchone()
            now = _now()
            already_locked = False
            if not row:
                attempts = 1
                first_failed_at = now
            else:
                attempts = row.get("failed_attempts") if isinstance(row, dict) else row[0]
                first_failed_at = (
                    row.get("first_failed_at") if isinstance(row, dict) else row[1]
                )
                prev_locked_until = (
                    row.get("locked_until") if isinstance(row, dict) else row[2]
                )
                already_locked = bool(prev_locked_until) and prev_locked_until > now
                if first_failed_at is None or first_failed_at + WINDOW < now:
                    attempts = 1
                    first_failed_at = now
                else:
                    attempts = int(attempts or 0) + 1
            if already_locked:
                # Never extend an active lockout: an attacker hammering a
                # locked account must not be able to keep it locked forever.
                locked_until = prev_locked_until
            else:
                locked_until = now + LOCKOUT if attempts >= MAX_FAILED_ATTEMPTS else None
            cur.execute(
                """
                INSERT INTO login_throttle
                    (user_id, failed_attempts, first_failed_at, last_failed_at, locked_until)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    failed_attempts = EXCLUDED.failed_attempts,
                    first_failed_at = EXCLUDED.first_failed_at,
                    last_failed_at = EXCLUDED.last_failed_at,
                    locked_until = EXCLUDED.locked_until
                """,
                (user_id, attempts, first_failed_at, now, locked_until),
            )
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        logger.exception("login_throttle: record_failure failed")
    finally:
        try:
            conn.close()
        except Exception:
            pass


def clear(user_id):
    """Clear all throttle state after a successful authentication."""
    conn = get_db_connection()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            _acquire(cur, user_id)
            cur.execute("DELETE FROM login_throttle WHERE user_id=%s", (user_id,))
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        logger.exception("login_throttle: clear failed")
    finally:
        try:
            conn.close()
        except Exception:
            pass
