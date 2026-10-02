"""Mock-only login throttle fixtures (the DB-backed suite is tests/test_login_throttle.py)."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from auth import login_throttle as lt
from auth import service as svc

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)


class _Cur:
    def __init__(self, row):
        self.row, self.writes = row, []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        q = " ".join(sql.split())
        if q.startswith("INSERT INTO login_throttle"):
            self.writes.append(params)

    def fetchone(self):
        return self.row


class _Conn:
    def __init__(self, row=None):
        self.cur = _Cur(row)

    def cursor(self):
        return self.cur

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def _fail(monkeypatch, row):
    monkeypatch.setattr(lt, "_now", lambda: NOW)
    conn = _Conn(row)
    monkeypatch.setattr(lt, "get_db_connection", lambda: conn)
    lt.record_failure(1)
    return conn.cur.writes[-1]  # (uid, attempts, first, last, locked_until)


def test_fifth_failure_in_window_locks_for_15_minutes(monkeypatch):
    row = {"failed_attempts": 4, "first_failed_at": NOW - timedelta(minutes=5), "locked_until": None}
    w = _fail(monkeypatch, row)
    assert w[1] == 5 and w[4] == NOW + lt.LOCKOUT


def test_fourth_failure_does_not_lock(monkeypatch):
    row = {"failed_attempts": 3, "first_failed_at": NOW - timedelta(minutes=5), "locked_until": None}
    assert _fail(monkeypatch, row)[4] is None


def test_failures_outside_window_restart_count(monkeypatch):
    row = {"failed_attempts": 4, "first_failed_at": NOW - timedelta(minutes=16), "locked_until": None}
    w = _fail(monkeypatch, row)
    assert w[1] == 1 and w[4] is None


def test_attempts_during_lockout_do_not_extend_it(monkeypatch):
    until = NOW + timedelta(minutes=3)
    row = {"failed_attempts": 5, "first_failed_at": NOW - timedelta(minutes=5), "locked_until": until}
    assert _fail(monkeypatch, row)[4] == until


def test_is_locked_reads_lock_and_fails_closed(monkeypatch):
    monkeypatch.setattr(lt, "_now", lambda: NOW)
    monkeypatch.setattr(lt, "get_db_connection", lambda: _Conn({"locked_until": NOW + timedelta(minutes=1)}))
    assert lt.is_locked(1) is True
    monkeypatch.setattr(lt, "get_db_connection", lambda: _Conn({"locked_until": NOW - timedelta(minutes=1)}))
    assert lt.is_locked(1) is False
    monkeypatch.setattr(lt, "get_db_connection", lambda: _Conn(None))
    assert lt.is_locked(1) is False
    monkeypatch.setattr(lt, "get_db_connection", lambda: None)
    assert lt.is_locked(1) is True

    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(lt, "get_db_connection", boom)
    with pytest.raises(RuntimeError):
        lt.is_locked(1)  # connection failure itself propagates; cursor errors are caught below

    class _Bad(_Conn):
        def cursor(self):
            raise RuntimeError("cursor failed")

    monkeypatch.setattr(lt, "get_db_connection", lambda: _Bad())
    assert lt.is_locked(1) is True


def _login_env(monkeypatch, locked=False, pw_ok=True, status="ACTIVE"):
    events = []
    row = {"user_id": 3, "password_hash": "h", "account_status": status, "role": "CHILD"}
    monkeypatch.setattr(svc, "fetch_one", lambda *a, **k: row)
    monkeypatch.setattr(svc.login_throttle, "is_locked", lambda uid: locked)
    monkeypatch.setattr(svc.login_throttle, "record_failure", lambda uid: events.append("fail"))
    monkeypatch.setattr(svc.login_throttle, "clear", lambda uid: events.append("clear"))
    checks = []
    monkeypatch.setattr(svc, "check_password", lambda p, h: checks.append(p) or pw_ok)
    return row, events, checks


def test_locked_account_rejected_before_password_check_and_not_extended(monkeypatch):
    _, events, checks = _login_env(monkeypatch, locked=True)
    assert svc.login_user("kid", "right-password") is None
    assert checks == [] and events == []


def test_wrong_password_records_failure(monkeypatch):
    _, events, _ = _login_env(monkeypatch, pw_ok=False)
    assert svc.login_user("kid", "nope") is None
    assert events == ["fail"]


def test_success_clears_throttle(monkeypatch):
    row, events, _ = _login_env(monkeypatch)
    assert svc.login_user("kid", "ok") is row
    assert events == ["clear"]


def test_every_password_login_surface_uses_login_user():
    mobile = (ROOT / "mobile" / "api.py").read_text(encoding="utf-8")
    assert "user = login_user(identifier, password)" in mobile
    for rel in ("auth/routes.py", "auth/api.py"):
        assert "login_user(" in (ROOT / rel).read_text(encoding="utf-8")
    assert (ROOT / "auth" / "routes.py").read_text(encoding="utf-8").count("login_user(") >= 2  # web login + admin login
