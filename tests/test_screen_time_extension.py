"""Screen-time parent-control + extension flow.

Covers by source assertion plus one functional lock_state test (monkeypatched
DB layer, no live Postgres):
1. PARENT-ONLY RESET: the child reset endpoint is hard-disabled; only Parent
   Mode may reset or extend usage.
2. EXTENSION REQUEST FLOW: child POSTs a request (one PENDING at a time);
   parent approves/rejects from an owns()-scoped queue; approval writes a
   today-only bonus that services/usage.py lock_state() reads at check time
   (server-enforced grant, no client time math trusted); both sides get
   notifications; stale PENDING rows expire; decided rows are immutable.
"""
from datetime import date, timedelta
from pathlib import Path

import services.usage as usage

ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text(encoding='utf-8')


# ---------- migration ----------

def test_extension_migration_follows_dbmate_convention():
    mig = text('db/migrations/20260928000002_screen_time_extension_requests.sql')
    assert '-- migrate:up' in mig
    assert '-- migrate:down' in mig
    assert 'CREATE TABLE' in mig and 'screen_time_extension_requests' in mig
    for col in ('child_id', 'requested_minutes', 'status', 'created_at',
                'decided_at', 'decided_by', 'granted_minutes'):
        assert col in mig, f'missing column {col}'
    for status in ("'PENDING'", "'APPROVED'", "'REJECTED'", "'EXPIRED'"):
        assert status in mig, f'missing status {status}'
    assert 'bonus_minutes' in mig and 'bonus_date' in mig
    assert 'DROP TABLE IF EXISTS screen_time_extension_requests' in mig


# ---------- parent-only reset ----------

def test_child_self_reset_is_disabled_server_side():
    api = text('mobile/api.py')
    assert 'def mobile_kids_time_limit_self_reset():' in api
    block = api.split('def mobile_kids_time_limit_self_reset():', 1)[1].split(
        '# ---- Screen-time extension requests', 1
    )[0]
    assert 'error="parent_action_required"' in block
    assert 'Only your parent can reset or extend screen time.' in block
    assert 'KID_SCREEN_TIME_SELF_RESET' not in block
    assert 'DELETE FROM child_usage_logs' not in block


# ---------- extension request flow: child ----------

def test_child_extension_request_endpoint():
    api = text('mobile/api.py')
    assert '"/api/mobile/v1/kids/time-limit/extension-request"' in api
    # Child can only ever request for self: the uid comes from the session.
    assert 'def mobile_kids_time_limit_extension_request():' in api
    assert 'uid = int(g.mobile_user["user_id"])' in api
    # One pending request at a time per child.
    assert "AND status='PENDING'" in api
    assert 'error="extension_request_pending"' in api
    assert ', 409' in api
    # Requested minutes are server-clamped; no client math is trusted.
    assert '5 <= requested <= 180' in api
    # Parents are notified through the existing pipeline.
    assert 'SCREEN_TIME_EXTENSION_REQUEST' in api
    assert 'parent_notify(' in api


# ---------- extension request flow: parent decide ----------

def test_parent_decide_endpoints_are_scoped_and_immutable():
    api = text('mobile/api.py')
    assert 'extension-requests/<int:req_id>/approve' in api
    assert 'extension-requests/<int:req_id>/reject' in api
    # Parent can only decide for their own children.
    assert 'if not req or not owns(pid, req["child_id"]):' in api
    # Decided requests are immutable: transitions only leave PENDING.
    assert "SET status='APPROVED'" in api
    assert "SET status='REJECTED'" in api
    assert 'WHERE request_id=%s AND status=\'PENDING\'' in api
    assert 'error="request_already_decided"' in api
    # Granted minutes are server-clamped.
    assert '1 <= granted <= 720' in api


def test_approval_writes_today_only_bonus_grant():
    api = text('mobile/api.py')
    # The grant is written server-side into child_time_limits...
    assert 'bonus_minutes' in api and 'bonus_date = CURRENT_DATE' in api
    # ...zeroing any stale (non-today) bonus instead of stacking it.
    assert 'WHEN child_time_limits.bonus_date = CURRENT_DATE' in api
    # ...and the child is notified.
    assert 'SCREEN_TIME_EXTENSION_APPROVED' in api
    assert 'SCREEN_TIME_EXTENSION_REJECTED' in api


def test_stale_pending_requests_expire():
    api = text('mobile/api.py')
    assert "SET status='EXPIRED'" in api
    assert "status='PENDING' AND created_at::date < CURRENT_DATE" in api


# ---------- enforcement: lock_state reads the grant ----------

def test_enforcement_reads_bonus_at_check_time():
    svc = text('services/usage.py')
    assert "lim.get('bonus_minutes')" in svc
    assert "lim.get('bonus_date')==date.today()" in svc
    assert 'def effective_daily_limit(child_id):' in svc


def test_lock_state_includes_today_bonus(monkeypatch):
    lim = {'child_id': 7, 'daily_limit_minutes': 60, 'strict_mode': True,
           'bonus_minutes': 30, 'bonus_date': date.today()}
    monkeypatch.setattr(usage, 'fetch_one', lambda sql, params=(): lim)
    monkeypatch.setattr(usage, 'minutes_today', lambda cid: 70)
    locked, remaining = usage.lock_state(7)
    assert locked is False
    assert remaining == 20  # 60 + 30 bonus - 70 used


def test_lock_state_ignores_stale_bonus(monkeypatch):
    lim = {'child_id': 7, 'daily_limit_minutes': 60, 'strict_mode': True,
           'bonus_minutes': 30, 'bonus_date': date.today() - timedelta(days=1)}
    monkeypatch.setattr(usage, 'fetch_one', lambda sql, params=(): lim)
    monkeypatch.setattr(usage, 'minutes_today', lambda cid: 70)
    locked, remaining = usage.lock_state(7)
    assert locked is True
    assert remaining == 0  # stale bonus ignored: 60 - 70 -> 0


def test_effective_daily_limit_matches_enforcement(monkeypatch):
    lim = {'child_id': 7, 'daily_limit_minutes': 60, 'strict_mode': True,
           'bonus_minutes': 45, 'bonus_date': date.today()}
    monkeypatch.setattr(usage, 'fetch_one', lambda sql, params=(): lim)
    assert usage.effective_daily_limit(7) == 105


# ---------- real-SQL behavior: bonus upsert + migration syntax (SQLite) ----------

import sqlite3


def _bonus_upsert_sql():
    """The approve-time grant, ported 1:1 from mobile/api.py (%s -> ?)."""
    return """INSERT INTO child_time_limits(child_id, daily_limit_minutes, strict_mode, bonus_minutes, bonus_date)
               VALUES(?, 60, TRUE, ?, CURRENT_DATE)
               ON CONFLICT(child_id) DO UPDATE SET
                 bonus_minutes = CASE
                   WHEN child_time_limits.bonus_date = CURRENT_DATE
                   THEN child_time_limits.bonus_minutes ELSE 0 END + excluded.bonus_minutes,
                 bonus_date = CURRENT_DATE,
                 updated_at = CURRENT_TIMESTAMP"""


def _limits_table(con):
    con.execute(
        "CREATE TABLE child_time_limits(child_id INTEGER PRIMARY KEY, "
        "daily_limit_minutes INTEGER NOT NULL DEFAULT 60, "
        "strict_mode BOOLEAN NOT NULL DEFAULT FALSE, "
        "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
        "bonus_minutes INTEGER NOT NULL DEFAULT 0, bonus_date DATE)")


def test_bonus_grant_zeroes_stale_bonus_and_stacks_same_day():
    con = sqlite3.connect(':memory:')
    _limits_table(con)
    # Stale bonus from yesterday must be zeroed, not stacked.
    con.execute("INSERT INTO child_time_limits(child_id, bonus_minutes, bonus_date) "
                "VALUES(7, 30, date('now','-1 day'))")
    con.execute(_bonus_upsert_sql(), (7, 45))
    got = con.execute("SELECT bonus_minutes FROM child_time_limits WHERE child_id=7").fetchone()[0]
    assert got == 45, f'stale bonus stacked: {got}'
    # A second same-day grant stacks on top.
    con.execute(_bonus_upsert_sql(), (7, 15))
    got = con.execute("SELECT bonus_minutes FROM child_time_limits WHERE child_id=7").fetchone()[0]
    assert got == 60, f'same-day grant did not stack: {got}'


def test_migration_up_runs_against_real_sql_engine():
    mig = text('db/migrations/20260928000002_screen_time_extension_requests.sql')
    up = mig.split('-- migrate:up')[1].split('-- migrate:down')[0]
    # Strip full-line comments so multi-line statements survive the split.
    up = '\n'.join(line for line in up.splitlines()
                   if not line.strip().startswith('--'))
    # NOW() and ADD COLUMN IF NOT EXISTS are valid Postgres but unknown to
    # SQLite; normalize for the syntax check only.
    up = up.replace('NOW()', 'CURRENT_TIMESTAMP')
    up = up.replace('ADD COLUMN IF NOT EXISTS', 'ADD COLUMN')
    con = sqlite3.connect(':memory:')
    con.execute("CREATE TABLE users(user_id INTEGER PRIMARY KEY)")
    con.execute("CREATE TABLE child_time_limits(child_id INTEGER PRIMARY KEY, "
                "daily_limit_minutes INTEGER NOT NULL DEFAULT 60, "
                "strict_mode BOOLEAN NOT NULL DEFAULT FALSE, "
                "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    con.executescript(up)
    cols = {r[1] for r in con.execute("PRAGMA table_info(screen_time_extension_requests)").fetchall()}
    assert {'request_id', 'child_id', 'requested_minutes', 'status',
            'created_at', 'decided_at', 'decided_by', 'granted_minutes'} <= cols
    lim_cols = {r[1] for r in con.execute("PRAGMA table_info(child_time_limits)").fetchall()}
    assert 'bonus_minutes' in lim_cols and 'bonus_date' in lim_cols
    # Status CHECK is enforced: bogus status rejected.
    con.execute("INSERT INTO users(user_id) VALUES(7)")
    try:
        con.execute("INSERT INTO screen_time_extension_requests(child_id, requested_minutes, status) "
                    "VALUES(7, 30, 'BOGUS')")
        raise AssertionError('status CHECK not enforced')
    except sqlite3.IntegrityError:
        pass
    con.execute("INSERT INTO screen_time_extension_requests(child_id, requested_minutes) VALUES(7, 30)")
    row = con.execute("SELECT status FROM screen_time_extension_requests").fetchone()
    assert row[0] == 'PENDING'


# ---------- web parent surface ----------

def test_web_parent_time_limit_handles_extension_decisions():
    routes = text('parent/routes.py')
    assert "action=='approve_extension'" in routes
    assert "action=='reject_extension'" in routes
    assert 'if not req or int(req[' in routes  # child-scoped decide
    assert 'bonus_minutes' in routes
    tpl = text('parent/templates/time_limit.html')
    assert 'extension_requests' in tpl
    assert 'approve_extension' in tpl
    assert 'reject_extension' in tpl


# ---------- mobile client ----------

def test_mobile_surfaces():
    client = text('mobile_app/src/api/client.ts')
    assert 'kidsExtensionRequest' in client
    assert 'parentExtensionRequests' in client
    assert 'parentExtensionRequestAction' in client
    kids = text('mobile_app/src/api/kidsFeed.ts')
    assert 'requestScreenTimeExtension' in kids
    assert 'fetchExtensionRequestStatus' in kids
    lock = text('mobile_app/src/screens/kids/ScreenTimeLockedScreen.tsx')
    assert 'requestScreenTimeExtension' in lock
    assert 'Ask Parent for More Time' in lock
    parent = text('mobile_app/src/screens/parent/ParentScreens.tsx')
    assert 'ExtensionRequestQueue' in parent
    assert 'decideExtensionRequest' in parent
    admin = text('mobile_app/src/api/parentAdmin.ts')
    assert 'fetchPendingExtensionRequests' in admin
    assert 'decideExtensionRequest' in admin
