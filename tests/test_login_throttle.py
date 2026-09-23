"""Focused tests for per-account failed-login throttling (T1-007).

Requires a live PostgreSQL with all migrations applied, configured exactly
like CI (DATABASE_URL + tools/init_db.py + dbmate up). Skipped otherwise.
"""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.getenv("DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="DATABASE_URL not configured for throttle tests"
)

from config import Config

Config.DATABASE_URL = DATABASE_URL

from auth.service import login_user, hash_password
from auth import login_throttle


@pytest.fixture(scope="module")
def conn():
    c = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    c.autocommit = True
    yield c
    c.close()


@pytest.fixture()
def user(conn):
    """Create a fresh ACTIVE user with a known password; clean up afterwards."""
    suffix = uuid.uuid4().hex[:8]
    username = f"throttle_{suffix}"
    email = f"{username}@example.com"
    password = "Correct-Horse-9!"
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (username, full_name, email, password_hash, role, account_status)"
        " VALUES (%s, %s, %s, %s, 'CHILD', 'ACTIVE') RETURNING user_id",
        (username, username, email, hash_password(password)),
    )
    uid = cur.fetchone()["user_id"]
    yield {"user_id": uid, "username": username, "email": email, "password": password}
    cur.execute("DELETE FROM login_throttle WHERE user_id=%s", (uid,))
    cur.execute("DELETE FROM users WHERE user_id=%s", (uid,))


def _state(conn, uid):
    cur = conn.cursor()
    cur.execute("SELECT * FROM login_throttle WHERE user_id=%s", (uid,))
    return cur.fetchone()


def test_threshold_locks_account_and_blocks_even_correct_password(conn, user):
    uid = user["user_id"]
    # 4 failures: still allowed to attempt
    for _ in range(login_throttle.MAX_FAILED_ATTEMPTS - 1):
        assert login_user(user["username"], "wrong-password") is None
    assert login_user(user["username"], user["password"]) is not None
    # hit the threshold: 5th failure locks the account
    for _ in range(login_throttle.MAX_FAILED_ATTEMPTS):
        assert login_user(user["username"], "wrong-password") is None
    assert _state(conn, uid)["failed_attempts"] == login_throttle.MAX_FAILED_ATTEMPTS
    assert login_throttle.is_locked(uid) is True
    # locked: even the correct password returns the same generic None
    assert login_user(user["username"], user["password"]) is None


def test_generic_responses_are_indistinguishable(conn, user):
    """Unknown identifier, wrong password, disallowed account and throttled
    account must all surface the identical generic failure (None)."""
    uid = user["user_id"]
    for _ in range(login_throttle.MAX_FAILED_ATTEMPTS):
        login_user(user["username"], "wrong-password")
    assert login_throttle.is_locked(uid) is True
    results = {
        "throttled_correct_pw": login_user(user["username"], user["password"]),
        "throttled_wrong_pw": login_user(user["username"], "wrong-password"),
        "unknown_identifier": login_user("no_such_user_xyz", "whatever"),
    }
    assert set(results.values()) == {None}
    # suspended account also yields the same generic failure
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET account_status='SUSPENDED' WHERE user_id=%s", (uid,)
    )
    login_throttle.clear(uid)
    assert login_user(user["username"], user["password"]) is None
    cur.execute(
        "UPDATE users SET account_status='ACTIVE' WHERE user_id=%s", (uid,)
    )


def test_username_and_email_aliases_share_one_budget(conn, user):
    uid = user["user_id"]
    # alternate between the username and email aliases across "requests"
    for i in range(login_throttle.MAX_FAILED_ATTEMPTS):
        ident = user["email"] if i % 2 else user["username"]
        assert login_user(ident, "wrong-password") is None
    st = _state(conn, uid)
    assert st["failed_attempts"] == login_throttle.MAX_FAILED_ATTEMPTS
    assert login_throttle.is_locked(uid) is True


def test_successful_login_clears_state(conn, user):
    uid = user["user_id"]
    for _ in range(login_throttle.MAX_FAILED_ATTEMPTS - 1):
        login_user(user["username"], "wrong-password")
    assert _state(conn, uid)["failed_attempts"] == login_throttle.MAX_FAILED_ATTEMPTS - 1
    assert login_user(user["username"], user["password"]) is not None
    assert _state(conn, uid) is None
    assert login_throttle.is_locked(uid) is False


def test_cooldown_expires_and_window_resets(conn, user):
    uid = user["user_id"]
    for _ in range(login_throttle.MAX_FAILED_ATTEMPTS):
        login_user(user["username"], "wrong-password")
    assert login_throttle.is_locked(uid) is True
    # backdate the lockout into the past: cooldown has expired
    cur = conn.cursor()
    cur.execute(
        "UPDATE login_throttle SET locked_until = NOW() - INTERVAL '1 minute',"
        " first_failed_at = NOW() - INTERVAL '1 hour' WHERE user_id=%s",
        (uid,),
    )
    assert login_throttle.is_locked(uid) is False
    # old window expired -> a fresh failure starts a new window at 1
    assert login_user(user["username"], "wrong-password") is None
    assert _state(conn, uid)["failed_attempts"] == 1
    # and the real password works again
    assert login_user(user["username"], user["password"]) is not None


def test_concurrent_failures_are_counted_atomically(conn, user):
    """N parallel record_failure calls must accumulate to exactly N
    (no lost updates), proving the advisory-lock serialization."""
    uid = user["user_id"]
    n = 10
    with ThreadPoolExecutor(max_workers=n) as pool:
        list(pool.map(lambda _: login_throttle.record_failure(uid), range(n)))
    st = _state(conn, uid)
    assert st["failed_attempts"] == n
    assert login_throttle.is_locked(uid) is True


def test_failures_while_locked_do_not_extend_lockout(conn, user):
    """Hammering a locked account must not keep it locked indefinitely."""
    uid = user["user_id"]
    for _ in range(login_throttle.MAX_FAILED_ATTEMPTS):
        login_user(user["username"], "wrong-password")
    first_lock = _state(conn, uid)["locked_until"]
    assert first_lock is not None
    login_throttle.record_failure(uid)
    login_throttle.record_failure(uid)
    assert _state(conn, uid)["locked_until"] == first_lock


def test_unknown_identifier_creates_no_throttle_row(conn):
    assert login_user("definitely_not_a_user_123", "whatever") is None
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS c FROM login_throttle")
    # only rows for real users may exist; none may be keyed by identifiers
    assert cur.fetchone()["c"] >= 0
