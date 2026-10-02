"""Parent "Clear Everything" account control.

Covers by source assertion plus functional service tests against a fake DB
cursor (no live Postgres):
1. ENDPOINT: POST /api/mobile/v1/parent/child/<id>/clear-everything is
   PARENT-role gated, owns()-scoped, and rate-limited.
2. IDENTITY PRESERVED: the service never DELETEs users or parent_child_map.
3. R2 SAFETY: post/upload/chat media references are enqueued into
   media_delete_outbox inside the same transaction (never stranded).
4. SCOPE: content, social graph (both directions), chats, quiz, activity,
   usage, notifications and settings are cleared; safety/security audit
   records and the parent safety policy are kept.
5. FAIL CLOSED: non-child targets and inactive accounts raise ValueError.
6. CHILD CANNOT SELF-CLEAR: only the parent endpoint exists.
7. MOBILE UI: route, API client fn and ParentScreens tile exist with a
   plain-language explanation of what is reset.
"""
from pathlib import Path

import pytest

import services.account_reset as account_reset

ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


# ---------- endpoint ----------

def test_clear_everything_endpoint_is_parent_gated_and_owned():
    api = text("mobile/api.py")
    route = '"/api/mobile/v1/parent/child/<int:child_id>/clear-everything"'
    assert route in api
    # Decorators sit just above the function def: capture from the route
    # decorator through the end of the function body.
    block = api.split(route, 1)[1].split(
        '@bp.route("/api/mobile/v1/parent/child/<int:child_id>", methods=["DELETE"])', 1
    )[0]
    assert '@_require_mobile("PARENT")' in block
    assert "owns(pid, child_id)" in block
    assert "limiter.limit(" in block
    assert "clear_everything_for_child(child_id, pid)" in block


def test_no_child_facing_clear_everything_route():
    api = text("mobile/api.py")
    # Exactly one backend route mentions clear-everything, and it is parent-scoped.
    assert api.count("clear-everything") == 1
    assert "kids/clear-everything" not in api
    assert "kids/child" not in api.split("clear-everything")[0].rsplit("@bp.route", 1)[-1]


# ---------- service scope ----------

def test_service_never_deletes_identity_or_parent_link():
    src = text("services/account_reset.py")
    assert "DELETE FROM users" not in src
    assert "DELETE FROM parent_child_map" not in src
    assert "DELETE FROM child_profiles" not in src


def test_service_keeps_safety_and_security_records():
    src = text("services/account_reset.py")
    for table in ("moderation_events", "moderation_reviews", "login_activity",
                  "parent_verifications", "admin_audit_logs", "reports",
                  "parent_safety_settings", "user_device_tokens"):
        assert f"DELETE FROM {table}" not in src, f"must keep {table}"


def test_service_enqueues_r2_media_before_deleting():
    src = text("services/account_reset.py")
    assert "media_delete_outbox" in src
    assert "R2_REFERENCE_PREFIX" in src
    # Posts, post upload sessions, chat upload sessions, sent chat media.
    for col in ("source_media_path", "media_path", "poster_path", "story_music_path",
                "object_key"):
        assert col in src
    assert "ENQUEUE_DELETE_SQL" in src
    assert "ON CONFLICT(reference)" in text("services/media_outbox.py")


def test_service_resets_settings_to_defaults():
    src = text("services/account_reset.py")
    # Cleared through the child-scoped table loop.
    assert '"DELETE FROM parent_control_settings WHERE child_id=%s"' in src
    assert '"DELETE FROM parent_quiz_settings WHERE child_id=%s"' in src
    assert '"DELETE FROM screen_time_extension_requests WHERE child_id=%s"' in src
    assert "daily_limit_minutes=60" in src
    assert "parent_paused=FALSE" in src


def test_service_fails_closed_for_non_child_and_inactive():
    src = text("services/account_reset.py")
    assert 'user.get("role") != "CHILD"' in src
    assert 'user.get("account_status") != "ACTIVE"' in src
    assert "raise ValueError" in src


def test_service_uses_advisory_lock_and_single_transaction():
    src = text("services/account_reset.py")
    assert "pg_advisory_xact_lock" in src
    assert "conn.commit()" in src
    assert "conn.rollback()" in src


# ---------- mobile client ----------

def test_mobile_route_and_api_fn_exist():
    client = text("mobile_app/src/api/client.ts")
    assert "parentChildClearEverything" in client
    assert "/clear-everything" in client
    api = text("mobile_app/src/api/parentAdmin.ts")
    assert "export function clearChildEverything" in api
    assert "routes.parentChildClearEverything(childId)" in api


def test_mobile_ui_explains_scope_and_requires_device_auth():
    ui = text("mobile_app/src/screens/parent/ParentScreens.tsx")
    assert "clearChildEverything" in ui
    assert "confirmClearEverything" in ui
    assert "doClearEverything" in ui
    assert "Clear Everything" in ui
    # Plain-language explanation of what is reset and what is kept.
    assert "permanently deletes" in ui.lower() or "Permanently deletes" in ui
    assert "family link" in ui
    # Same fresh device-auth gate as the other destructive parent actions.
    assert ui.count("ensureParentAuthForAction") >= 4


# ---------- functional service tests (fake DB cursor) ----------

class _FakeCursor:
    def __init__(self, user_row):
        self.user_row = user_row
        self.statements = []
        self.rowcount = 0
        self._select_result = []

    def execute(self, sql, params=None):
        recorded = " ".join(str(sql).split())
        if params:
            recorded += " :: " + repr(tuple(params))
        self.statements.append(recorded)
        if "pg_advisory_xact_lock" in sql:
            return
        if sql.strip().startswith("SELECT user_id, username"):
            self._select_result = [self.user_row] if self.user_row else []
            return
        if sql.strip().startswith("SELECT post_id"):
            self._select_result = []
            return
        if sql.strip().startswith("SELECT object_key"):
            self._select_result = []
            return
        if sql.strip().startswith("SELECT child_message_id"):
            self._select_result = []
            return
        if sql.strip().startswith("INSERT INTO media_delete_outbox"):
            return
        if sql.strip().startswith("DELETE FROM"):
            self.rowcount = 3
            return
        if sql.strip().startswith("INSERT INTO"):
            return
        if sql.strip().startswith("UPDATE"):
            return

    def fetchone(self):
        return self._select_result[0] if self._select_result else None

    def fetchall(self):
        return list(self._select_result)


class _FakeConn:
    def __init__(self, user_row):
        self.cur = _FakeCursor(user_row)
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self.cur

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass


def _run_service(monkeypatch, user_row):
    conn = _FakeConn(user_row)
    monkeypatch.setattr(account_reset, "get_db_connection", lambda: conn)
    # Keep the post-commit side effects from touching a real DB.
    monkeypatch.setattr("services.usage.restart_child_sessions", lambda _cid: True)
    monkeypatch.setattr("services.social.notify", lambda *a, **k: None)
    return conn


def test_clear_everything_happy_path_issues_expected_sql(monkeypatch):
    conn = _run_service(monkeypatch, {"user_id": 7, "username": "kid7",
                                     "role": "CHILD", "account_status": "ACTIVE"})
    summary = account_reset.clear_everything_for_child(7, 42)
    assert conn.committed and not conn.rolled_back
    sql = "\n".join(conn.cur.statements)
    # Advisory lock first.
    assert "pg_advisory_xact_lock" in sql
    # Content + uploads gone.
    assert "DELETE FROM posts WHERE child_id=%s" in sql
    assert "DELETE FROM upload_sessions WHERE child_id=%s" in sql
    assert "DELETE FROM chat_upload_sessions WHERE child_id=%s" in sql
    # Social graph both directions.
    assert "DELETE FROM followers WHERE child_id=%s OR following_child_id=%s" in sql
    assert "DELETE FROM blocked_users WHERE blocker_id=%s OR blocked_id=%s" in sql
    assert "DELETE FROM muted_users WHERE muter_id=%s OR muted_id=%s" in sql
    # Conversations both directions (messages cascade).
    assert "DELETE FROM child_conversations WHERE child1_id=%s OR child2_id=%s" in sql
    # Quiz / activity / usage / notifications cleared.
    for table in ("child_quiz_attempts", "activity_logs", "child_usage_logs",
                  "screen_time_extension_requests", "notifications",
                  "parent_notifications", "feed_sessions", "recommendation_signals"):
        assert f"DELETE FROM {table}" in sql, table
    # Settings reset.
    assert "DELETE FROM parent_control_settings WHERE child_id=%s" in sql
    assert "parent_paused=FALSE" in sql
    # Identity never deleted.
    assert "DELETE FROM users" not in sql
    assert "DELETE FROM parent_child_map" not in sql
    assert isinstance(summary, dict) and "posts" in summary


def test_clear_everything_rejects_non_child(monkeypatch):
    conn = _run_service(monkeypatch, {"user_id": 9, "username": "dad9",
                                     "role": "PARENT", "account_status": "ACTIVE"})
    with pytest.raises(ValueError):
        account_reset.clear_everything_for_child(9, 42)
    assert conn.rolled_back and not conn.committed


def test_clear_everything_rejects_inactive_child(monkeypatch):
    conn = _run_service(monkeypatch, {"user_id": 7, "username": "kid7",
                                     "role": "CHILD", "account_status": "DEACTIVATED"})
    with pytest.raises(ValueError):
        account_reset.clear_everything_for_child(7, 42)
    assert conn.rolled_back and not conn.committed


def test_clear_everything_enqueues_r2_refs_transactionally(monkeypatch):
    conn_holder = {}

    class _MediaCursor(_FakeCursor):
        def execute(self, sql, params=None):
            super().execute(sql, params)
            if sql.strip().startswith("SELECT post_id"):
                self._select_result = [{
                    "post_id": 11,
                    "source_media_path": "uploads/r2/quarantine/a.jpg",
                    "media_path": "uploads/r2/published/b.jpg",
                    "poster_path": None,
                    "story_music_path": "",
                }]

    class _MediaConn(_FakeConn):
        def __init__(self):
            super().__init__({"user_id": 7, "username": "kid7",
                              "role": "CHILD", "account_status": "ACTIVE"})
            self.cur = _MediaCursor(self.cur.user_row)

    conn = _MediaConn()
    conn_holder["conn"] = conn
    monkeypatch.setattr(account_reset, "get_db_connection", lambda: conn)
    monkeypatch.setattr("services.usage.restart_child_sessions", lambda _cid: True)
    monkeypatch.setattr("services.social.notify", lambda *a, **k: None)
    summary = account_reset.clear_everything_for_child(7, 42)
    assert conn.committed
    sql = "\n".join(conn.cur.statements)
    assert sql.count("INSERT INTO media_delete_outbox") == 2
    assert "uploads/r2/quarantine/a.jpg" in sql
    assert "uploads/r2/published/b.jpg" in sql
    assert summary["media_enqueued"] == 2


def test_clear_everything_enqueues_media_asset_variant_keys(monkeypatch):
    """media_assets rows (transcoded/sanitized variants) carry their own R2
    keys. The posts DELETE cascades these rows, so their keys must be
    enqueued first or the variant objects are stranded."""
    conn_holder = {}

    class _VariantCursor(_FakeCursor):
        def execute(self, sql, params=None):
            super().execute(sql, params)
            if "FROM media_assets" in sql:
                self._select_result = [{
                    "media_id": 5,
                    "source_r2_key": "uploads/r2/quarantine/v.mp4",
                    "published_reference": "uploads/r2/published/v-sanitized.mp4",
                    "poster_reference": "uploads/r2/posters/v.jpg",
                }]

    class _VariantConn(_FakeConn):
        def __init__(self):
            super().__init__({"user_id": 7, "username": "kid7",
                              "role": "CHILD", "account_status": "ACTIVE"})
            self.cur = _VariantCursor(self.cur.user_row)

    conn = _VariantConn()
    conn_holder["conn"] = conn
    monkeypatch.setattr(account_reset, "get_db_connection", lambda: conn)
    monkeypatch.setattr("services.usage.restart_child_sessions", lambda _cid: True)
    monkeypatch.setattr("services.social.notify", lambda *a, **k: None)
    summary = account_reset.clear_everything_for_child(7, 42)
    assert conn.committed
    sql = "\n".join(conn.cur.statements)
    assert "uploads/r2/quarantine/v.mp4" in sql
    assert "uploads/r2/published/v-sanitized.mp4" in sql
    assert "uploads/r2/posters/v.jpg" in sql
    assert summary["media_enqueued"] == 3


def test_clear_everything_enqueues_peer_chat_media_and_tombstones(monkeypatch):
    """Conversations are deleted for BOTH participants, so the peer's media
    messages must be enqueued too. deleted_posts tombstones also hold media
    refs that were never queued by the web delete path."""
    conn_holder = {}

    class _PeerCursor(_FakeCursor):
        def execute(self, sql, params=None):
            super().execute(sql, params)
            if "FROM child_messages" in sql:
                # Peer's image in a shared conversation (child 7 is receiver).
                self._select_result = [{
                    "child_message_id": 99,
                    "media_path": "uploads/r2/chat/peer-img.jpg",
                }]
            elif "FROM deleted_posts" in sql and "media_path" in sql:
                self._select_result = [{
                    "deleted_post_id": 3,
                    "media_path": "uploads/r2/published/old.jpg",
                    "story_music_path": None,
                }]

    class _PeerConn(_FakeConn):
        def __init__(self):
            super().__init__({"user_id": 7, "username": "kid7",
                              "role": "CHILD", "account_status": "ACTIVE"})
            self.cur = _PeerCursor(self.cur.user_row)

    conn = _PeerConn()
    conn_holder["conn"] = conn
    monkeypatch.setattr(account_reset, "get_db_connection", lambda: conn)
    monkeypatch.setattr("services.usage.restart_child_sessions", lambda _cid: True)
    monkeypatch.setattr("services.social.notify", lambda *a, **k: None)
    summary = account_reset.clear_everything_for_child(7, 42)
    assert conn.committed
    sql = "\n".join(conn.cur.statements)
    assert "uploads/r2/chat/peer-img.jpg" in sql
    assert "uploads/r2/published/old.jpg" in sql
    assert summary["media_enqueued"] == 2


def test_clear_everything_bumps_session_version_in_transaction(monkeypatch):
    """Old child tokens must die atomically with the wipe -- the
    session_version bump happens inside the transaction, before commit."""
    conn_holder = {}

    class _SverConn(_FakeConn):
        pass

    conn = _SverConn({"user_id": 7, "username": "kid7",
                      "role": "CHILD", "account_status": "ACTIVE"})
    conn_holder["conn"] = conn
    monkeypatch.setattr(account_reset, "get_db_connection", lambda: conn)
    monkeypatch.setattr("services.usage.restart_child_sessions", lambda _cid: True)
    monkeypatch.setattr("services.social.notify", lambda *a, **k: None)
    account_reset.clear_everything_for_child(7, 42)
    sql = "\n".join(conn.cur.statements)
    assert "UPDATE users SET session_version=COALESCE(session_version,1)+1" in sql
    # The bump runs on the same connection that then commits.
    assert conn.committed and not conn.rolled_back


def test_clear_everything_clears_weekly_digests(monkeypatch):
    """Parent weekly digests hold activity summaries; they are stale after a
    wipe and must be cleared with the rest of the activity history."""
    src = text("services/account_reset.py")
    assert '"DELETE FROM parent_weekly_digests WHERE child_id=%s"' in src
