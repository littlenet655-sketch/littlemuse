"""Regression test: post-tag persistence must be atomic with post creation.

Defect: save_post_tags() ran AFTER conn.commit() on its own connection, so a
DB error inside tag persistence stranded a committed post with the upload
marked CONSUMED and moderation never dispatched (child stuck at
"Checking privately...").

Fix: tags are inserted on the view's own cursor BEFORE conn.commit(), so a tag
failure rolls back the post row and the CONSUMED mark together.

These tests drive the real POST /api/mobile/v2/uploads/<id>/complete view
with a fake DB connection that records the SQL/commit/rollback order. With
Flask TESTING=True the view's exception propagates (production returns 500).
"""
from __future__ import annotations

import pytest

import mobile.api as api
from mobile.api import _issue_token
from safety.policy import Decision


SESSION_ROW = {
    "upload_id": "tag-u1",
    "child_id": 7,
    "object_key": "uploads/r2/littlemuse/quarantine/7/tag-u1/source.jpg",
    "media_type": "IMAGE",
    "kind": "POST",
    "expected_size_bytes": 100,
    "mime_type": "image/jpeg",
    "extension": "jpg",
    "status": "PENDING",
    "expires_at": None,
}

USER_ROW = {
    "user_id": 7,
    "username": "tagkid",
    "full_name": "Tag Kid",
    "email": "tagkid@example.com",
    "role": "CHILD",
    "age": 10,
    "account_status": "ACTIVE",
    "session_version": 1,
}


class FakeCursor:
    def __init__(self, fail_on_tag=False):
        self.executed: list[tuple[str, tuple]] = []
        self.fail_on_tag = fail_on_tag

    def execute(self, sql, params=()):
        self.executed.append((sql, params))
        if self.fail_on_tag and "INSERT INTO post_tags" in sql:
            raise RuntimeError("simulated tag DB failure")

    def fetchone(self):
        sql = self.executed[-1][0]
        if "FROM upload_sessions" in sql:
            return dict(SESSION_ROW)
        if "FROM posts WHERE upload_id" in sql:
            return None
        if "INSERT INTO posts" in sql:
            return {"post_id": 101}
        return None

    def close(self):
        pass


class FakeConnection:
    def __init__(self, cursor, order_log):
        self._cursor = cursor
        self._order_log = order_log
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commits += 1
        self._order_log.append("commit")

    def rollback(self):
        self.rollbacks += 1
        self._order_log.append("rollback")

    def close(self):
        pass


@pytest.fixture
def rig(monkeypatch):
    """Fake-DB rig driving the real upload-complete view."""
    from app import create_app

    order_log: list[str] = []
    cursor = FakeCursor()
    conn = FakeConnection(cursor, order_log)

    monkeypatch.setattr(api, "get_db_connection", lambda: conn)
    monkeypatch.setattr(api, "_child_gate", lambda feature=None: None)
    monkeypatch.setattr(api, "effective_categories", lambda uid: {"Other"})
    monkeypatch.setattr(api, "scan_pii", lambda text: {"detected": False})
    monkeypatch.setattr(api, "_mobile_token_revoked", lambda token: False)
    monkeypatch.setattr(api, "fetch_one", lambda sql, params=(): dict(USER_ROW))
    monkeypatch.setattr(api, "feature_allowed", lambda uid, feature: True)

    from services import object_storage

    monkeypatch.setattr(object_storage, "enabled", lambda: True)
    monkeypatch.setattr(
        object_storage,
        "head_object",
        lambda ref: {"content_length": 100, "content_type": "image/jpeg", "etag": '"x"'},
    )

    import safety.text_service as ts
    import safety.policy as pol
    import safety.moderation_service as ms

    monkeypatch.setattr(ts, "check_text_deterministic", lambda text: {})
    monkeypatch.setattr(
        pol, "decide", lambda signals, level, threshold=None: Decision("ALLOW", 0.0, "test")
    )
    monkeypatch.setattr(ms, "safety_level", lambda child_id: "STANDARD")

    import services.job_queue as jq

    monkeypatch.setattr(jq, "enqueue_media_job", lambda *a, **k: "job-1")
    dispatched = []
    monkeypatch.setattr(api, "execute", lambda sql, params=(): dispatched.append((sql, params)))

    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()
    token = _issue_token({"user_id": 7, "role": "CHILD", "session_version": 1})
    headers = {"Authorization": f"Bearer {token}"}
    return client, headers, cursor, conn, order_log


def _complete(client, headers):
    return client.post(
        "/api/mobile/v2/uploads/tag-u1/complete",
        headers=headers,
        json={"caption": "", "tags": ["art"], "content_category": "Other"},
    )


def test_tag_db_failure_leaves_no_committed_post_and_upload_unconsumed(rig):
    client, headers, cursor, conn, order_log = rig
    cursor.fail_on_tag = True

    with pytest.raises(RuntimeError, match="simulated tag DB failure"):
        _complete(client, headers)

    # Nothing was committed: no post row, upload not consumed.
    assert conn.commits == 0
    assert conn.rollbacks >= 1
    assert "commit" not in order_log
    sqls = [sql for sql, _ in cursor.executed]
    assert any("INSERT INTO posts" in s for s in sqls)
    assert any("status='CONSUMED'" in s for s in sqls)
    assert any("INSERT INTO post_tags" in s for s in sqls)


def test_tags_persist_in_same_transaction_before_commit(rig):
    client, headers, cursor, conn, order_log = rig

    resp = _complete(client, headers)

    assert resp.status_code == 200
    assert resp.get_json()["post_id"] == 101
    assert conn.commits == 1
    tag_positions = [
        i for i, (sql, _) in enumerate(cursor.executed) if "INSERT INTO post_tags" in sql
    ]
    assert tag_positions, "expected tag inserts on the view's cursor"
    # The single commit happens after every tag insert: one transaction.
    assert order_log == ["commit"]
    assert len(tag_positions) == 1
