"""Red-team regression: approving a review event must never resurrect
already-BLOCKED content (H1 from the friendship/moderation audit).

Uses a fake DB cursor; no live Postgres required.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import mobile.api as mapi


class _FakeCursor:
    def __init__(self):
        self.statements = []
        self._result = None

    def execute(self, sql, params=None):
        q = " ".join(str(sql).split())
        self.statements.append((q, params))
        if "FROM moderation_events WHERE event_id" in q:
            self._result = [{
                "event_id": 5, "child_id": 7, "content_type": "MESSAGE",
                "content_id": 42, "decision": "REVIEW", "status": "OPEN",
            }]
        elif q.startswith("SELECT moderation_status FROM child_messages"):
            # The terminal-block guard query: content is already BLOCKED.
            self._result = [{"moderation_status": "BLOCKED"}]
        elif "FROM child_messages" in q and "FOR UPDATE" in q:
            self._result = [{
                "child_message_id": 42, "sender_child_id": 7,
                "receiver_child_id": 8, "message_type": "TEXT",
                "media_path": None,
            }]
        else:
            self._result = []

    def fetchone(self):
        return self._result[0] if self._result else None

    def fetchall(self):
        return list(self._result or [])


class _FakeConn:
    def __init__(self):
        self.cur = _FakeCursor()
        self.committed = False

    def cursor(self):
        return self.cur

    def commit(self):
        self.committed = True

    def rollback(self):
        pass

    def close(self):
        pass


def test_approve_does_not_resurrect_blocked_message(monkeypatch):
    conn = _FakeConn()
    monkeypatch.setattr(mapi, "get_db_connection", lambda: conn)
    monkeypatch.setattr(mapi, "owns", lambda _pid, _cid: True)
    monkeypatch.setattr(mapi, "notify", lambda *a, **k: None)

    ok, result = mapi._resolve_parent_review(101, 5, "APPROVE")

    assert ok is True
    assert result == "BLOCK", "APPROVE on already-BLOCKED content must downgrade to BLOCK"
    assert conn.committed

    updates = [(q, p) for q, p in conn.cur.statements if q.startswith("UPDATE child_messages SET moderation_status")]
    assert updates, "expected a moderation_status UPDATE on the message"
    # The status written must be BLOCKED, never ALLOWED.
    assert all(p[0] == "BLOCKED" for _, p in updates), updates
    assert not any(p[0] == "ALLOWED" for _, p in updates)

    reviews = [(q, p) for q, p in conn.cur.statements if q.startswith("INSERT INTO moderation_reviews")]
    assert reviews
    assert reviews[0][1][2] == "BLOCK"
    assert "already blocked" in (reviews[0][1][3] or "")


def test_report_target_rejects_blocked_message():
    """_validate_report_target must not mint REVIEW events for BLOCKED messages."""
    import mobile.stitch_api as sapi

    seen = {}

    def fake_fetch_one(sql, params=None):
        seen["sql"] = " ".join(str(sql).split())
        return None  # blocked or missing -> no row

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(sapi, "fetch_one", fake_fetch_one)
    try:
        assert sapi._validate_report_target(8, "MESSAGE", 42) is None
    finally:
        monkeypatch.undo()
    assert "moderation_status<>'BLOCKED'" in seen["sql"]
