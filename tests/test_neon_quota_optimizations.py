"""Offline-only Neon quota tests. No DB calls or external services."""
from __future__ import annotations

import ast
import logging
import os
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def _module(path):
    return ast.parse((ROOT / path).read_text(encoding="utf-8"), filename=path)


def _source(path):
    return (ROOT / path).read_text(encoding="utf-8")


def _function(path, name, namespace):
    mod = _module(path)
    funcs = [f for f in mod.body if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)) and f.name == name]
    assert len(funcs) == 1, f"Missing or ambiguous {name}"
    fn = funcs[0]
    fn.decorator_list = []
    exec(compile(ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[])), path, "exec"), namespace)
    return namespace[name]


def _decorator_source(path, name):
    src = _source(path)
    idx = src.index(f"def {name}(")
    dec = src.rfind("@app.function(", 0, idx)
    assert dec != -1
    return src[dec:idx]


def test_neon_cron_cadence_and_pool_limits():
    modal = _source("modal_web.py")
    sweep = _decorator_source("modal_web.py", "password_reset_email_sweep")
    recovery = _decorator_source("modal_web.py", "recovery_sweep")
    assert 'schedule=modal.Cron("0 * * * *")' in sweep
    assert 'schedule=modal.Cron("*/30 * * * *")' in recovery
    assert 'schedule=modal.Cron("* * * * *")' not in modal
    assert 'schedule=modal.Cron("*/10 * * * *")' not in modal
    assert '"DB_POOL_MIN_CONNECTIONS": os.getenv("DB_POOL_MIN_CONNECTIONS", "1")' in modal
    assert '"DB_POOL_MAX_CONNECTIONS": os.getenv("DB_POOL_MAX_CONNECTIONS", "8")' in modal
    assert "every 30 minutes" in _source("services/recovery.py")


def test_immediate_otp_worker_retains_retry_and_expiry_guards():
    modal = _source("modal_web.py")
    auth = _source("auth/password_reset.py")
    worker = _decorator_source("modal_web.py", "dispatch_password_reset_email")
    assert "retries=modal.Retries(" in worker
    assert "max_retries=3" in worker
    assert "def dispatch_password_reset_email(reset_token: str):" in modal
    assert "batch_size=1, reset_token=reset_token, raise_on_failure=True" in modal
    assert "t.status = 'ACTIVE'" in auth
    assert "t.expires_at > NOW()" in auth
    assert "AND o.reset_token = %s" in auth


def test_event_driven_dispatch_only_in_production(monkeypatch):
    calls = []
    class Remote:
        def spawn(self, token):
            calls.append(("spawn", token))
    class Function:
        @staticmethod
        def from_name(app, name):
            calls.append(("lookup", app, name))
            return Remote()
    monkeypatch.setitem(sys.modules, "modal", SimpleNamespace(Function=Function))
    dispatcher = _function("auth/password_reset.py", "_dispatch_password_reset_email_async", {"os": os, "logging": logging})
    monkeypatch.setenv("LITTLENET_WEB_MODAL_APP", "littlemuse-web")
    monkeypatch.setenv("LITTLENET_ENV", "development")
    dispatcher("dev-token")
    assert calls == []
    monkeypatch.setenv("LITTLENET_ENV", "production")
    dispatcher("prod-token")
    assert calls == [("lookup", "littlemuse-web", "dispatch_password_reset_email"), ("spawn", "prod-token")]


def test_dispatch_fails_closed_without_exposing_errors(monkeypatch):
    class Function:
        @staticmethod
        def from_name(*args):
            raise RuntimeError("simulated outage")
    monkeypatch.setitem(sys.modules, "modal", SimpleNamespace(Function=Function))
    monkeypatch.setenv("LITTLENET_ENV", "production")
    dispatcher = _function("auth/password_reset.py", "_dispatch_password_reset_email_async", {"os": os, "logging": logging})
    assert dispatcher("dummy-token") is None


def test_production_password_reset_does_not_issue_create_table(monkeypatch):
    monkeypatch.setenv("LITTLENET_ENV", "production")
    def db_connection():
        raise AssertionError("production attempted DDL/DB connection in _ensure_table")
    f = _function("auth/password_reset.py", "_ensure_table", {"os": os, "get_db_connection": db_connection})
    assert f() is None


def test_outbox_query_is_token_scoped_and_active_only():
    class Cursor:
        def __init__(self): self.queries = []
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def execute(self, sql, params=()): self.queries.append((sql, params))
        def fetchall(self): return []
    class Connection:
        def __init__(self): self.cur = Cursor(); self.committed = 0; self.closed = 0
        def cursor(self): return self.cur
        def commit(self): self.committed += 1
        def rollback(self): raise AssertionError("rollback unnecessary")
        def close(self): self.closed += 1
    conn = Connection()
    namespace = {"reap_expired_reset_transactions": lambda: 0, "get_db_connection": lambda: conn}
    fn = _function("auth/password_reset.py", "process_password_reset_email_outbox", namespace)
    assert fn(batch_size=1, reset_token="token-123", raise_on_failure=True) == 0
    sql, params = conn.cur.queries[0]
    assert "o.reset_token = %s" in sql
    assert "t.status = 'ACTIVE'" in sql and "t.expires_at > NOW()" in sql
    assert "FOR UPDATE OF o SKIP LOCKED" in sql
    assert params == ("token-123", 1)
    assert conn.committed == 1 and conn.closed == 1


def test_retryable_transport_failures_raise_without_exposing_otp():
    class Cursor:
        def __init__(self): self.queries = []
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def execute(self, sql, params=()): self.queries.append((sql, params))
        def fetchall(self):
            return [{"outbox_id": 12, "recipient": "test@example.invalid", "subject": "Reset", "body_html": "ciphertext"}]
    class Connection:
        def __init__(self): self.cur = Cursor(); self.committed = 0; self.closed = 0
        def cursor(self): return self.cur
        def commit(self): self.committed += 1
        def rollback(self): raise AssertionError("rollback unnecessary")
        def close(self): self.closed += 1
    conn = Connection()
    namespace = {
        "reap_expired_reset_transactions": lambda: 0,
        "get_db_connection": lambda: conn,
        "decrypt_outbox_body": lambda v: v,
        "send_email": lambda *args: False,
    }
    fn = _function("auth/password_reset.py", "process_password_reset_email_outbox", namespace)
    try:
        fn(batch_size=1, reset_token="token-456", raise_on_failure=True)
    except RuntimeError as exc:
        assert "Password-reset email dispatch failed" in str(exc)
        assert "ciphertext" not in str(exc)
    else:
        raise AssertionError("Failed transport should trigger Modal retry")
    assert conn.committed == 1 and conn.closed == 1
    assert any("attempts = attempts + 1" in sql for sql, _ in conn.cur.queries)


def test_media_delete_outbox_is_reconciled_by_scheduled_recovery(monkeypatch):
    """Ensure the removed old 5-minute Modal job has a durable replacement."""
    from services import media_outbox, recovery
    calls = []
    monkeypatch.setattr(recovery, "run_recovery_sweep", lambda: {"stale_media_jobs": {"ok": True}})
    monkeypatch.setattr(media_outbox, "reconcile_pending_deletes", lambda limit: calls.append(limit) or {"checked": 2, "completed": 2, "failed": 0})
    worker = _function("modal_web.py", "recovery_sweep", {"os": SimpleNamespace(chdir=lambda path: None)})
    result = worker()
    assert calls == [50]
    assert result["stale_media_jobs"]["ok"] is True
    assert result["media_delete_outbox"]["completed"] == 2


def test_media_delete_outbox_error_does_not_stop_recovery(monkeypatch):
    from services import media_outbox, recovery
    monkeypatch.setattr(recovery, "run_recovery_sweep", lambda: {"stale_media_jobs": {"ok": True}})
    def unavailable(limit):
        raise RuntimeError("temporary database outage")
    monkeypatch.setattr(media_outbox, "reconcile_pending_deletes", unavailable)
    worker = _function("modal_web.py", "recovery_sweep", {"os": SimpleNamespace(chdir=lambda path: None)})
    result = worker()
    assert result["stale_media_jobs"]["ok"] is True
    assert result["media_delete_outbox"]["ok"] is False
    assert "temporary database outage" in result["media_delete_outbox"]["error"]
