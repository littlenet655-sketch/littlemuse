"""Real-time chat v1: after_id polling + typing heartbeats.

DB-free contract tests (stubbed database/social layers):
- messages(after_id=...) must add a "newer than" filter without weakening the
  existing moderation/visibility filters.
- set_typing must upsert a heartbeat row; is_peer_typing must apply a
  server-side TTL and never trust the client.
- analytics.capture must be a silent no-op when PostHog is not configured.
Static guards on mobile/api.py: the typing endpoint must require an approved
connection and be rate limited.
"""

import importlib
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[1]


@pytest.fixture
def message_service(monkeypatch):
    calls = {"can_interact": True, "rows": [], "conv": None, "executed": []}

    db = types.ModuleType("database.connection")

    def fake_fetch_one(sql, params=None):
        calls["last_fetch_one_sql"] = sql
        calls["last_fetch_one_params"] = params
        # chat_typing lookup returns a row only when the test arms one
        if "chat_typing" in sql:
            return calls.get("typing_row")
        return calls["conv"]

    def fake_fetch_all(sql, params=None):
        calls["last_fetch_all_sql"] = sql
        calls["last_fetch_all_params"] = params
        return list(calls["rows"])

    def fake_execute(sql, params=None, **kwargs):
        calls["executed"].append((sql, params))
        return None

    db.fetch_one = fake_fetch_one
    db.fetch_all = fake_fetch_all
    db.execute = fake_execute
    db_pkg = types.ModuleType("database")
    db_pkg.connection = db

    social = types.ModuleType("services.social")
    social.can_interact = lambda a, b: calls["can_interact"]
    services_pkg = types.ModuleType("services")
    services_pkg.social = social

    monkeypatch.setitem(sys.modules, "database.connection", db)
    monkeypatch.setitem(sys.modules, "database", db_pkg)
    monkeypatch.setitem(sys.modules, "services.social", social)
    monkeypatch.setitem(sys.modules, "services", services_pkg)
    sys.modules.pop("childMessage.service", None)
    sys.modules.pop("childMessage", None)
    svc = importlib.import_module("childMessage.service")
    return svc, calls


def test_messages_after_id_adds_newer_than_filter(message_service):
    svc, calls = message_service
    calls["conv"] = {"child1_id": 5, "child2_id": 7}
    calls["rows"] = [{"child_message_id": 42, "moderation_status": "ALLOWED",
                      "message_text": "new", "sender_child_id": 7}]
    rows = svc.messages(11, 7, after_id=40)
    sql = calls["last_fetch_all_sql"]
    params = calls["last_fetch_all_params"]
    assert "m.child_message_id > %s::bigint" in sql
    assert 40 in params
    # Existing guards must survive: moderation filter + soft-delete + paging.
    assert "m.moderation_status = 'ALLOWED'" in sql
    assert "m.sender_child_id = %s AND m.moderation_status = 'REVIEW'" in sql
    assert "m.is_deleted = FALSE" in sql
    assert "m.child_message_id < %s::bigint" in sql
    assert rows[0]["child_message_id"] == 42


def test_messages_after_id_none_keeps_full_history(message_service):
    svc, calls = message_service
    calls["conv"] = {"child1_id": 5, "child2_id": 7}
    svc.messages(11, 7)
    params = calls["last_fetch_all_params"]
    # NULL after_id disables the newer-than filter (IS NULL branch).
    assert params[4] is None and params[5] is None


def test_set_typing_upserts_heartbeat(message_service):
    svc, calls = message_service
    svc.set_typing(11, 5)
    upserts = [s for s, _ in calls["executed"] if "chat_typing" in s and "INSERT" in s]
    assert upserts, "set_typing must write a heartbeat row"
    assert "ON CONFLICT (conversation_id, user_id)" in upserts[0]
    assert (11, 5) in [p for _, p in calls["executed"] if p == (11, 5)]


def test_is_peer_typing_applies_server_side_ttl(message_service):
    svc, calls = message_service
    calls["typing_row"] = {"1": 1}
    assert svc.is_peer_typing(11, 5) is True
    sql = calls["last_fetch_one_sql"]
    assert "chat_typing" in sql
    assert "updated_at > NOW()" in sql
    assert "user_id != %s" in sql  # never reports your own heartbeat back
    calls["typing_row"] = None
    assert svc.is_peer_typing(11, 5) is False


def test_typing_ttl_is_short(message_service):
    svc, _ = message_service
    assert 1 <= svc.TYPING_TTL_SECONDS <= 30


def test_analytics_capture_is_noop_without_key():
    import services.analytics as analytics

    assert analytics.is_enabled() is False
    # Must never raise, with or without properties.
    analytics.capture(123, "message_sent", {"status": "ALLOW"})
    analytics.capture(123, "post_created")
    analytics.flush()


def test_typing_endpoint_requires_approved_connection():
    src = (REPO_ROOT / "mobile" / "api.py").read_text()
    start = src.index('/kids/chat/<int:peer_id>/typing')
    block = src[start:start + 1200]
    assert "approved_connection_required" in block
    assert "20 per minute" in src[max(0, start - 300):start + 200]
    assert "set_typing(cid, uid)" in block


def test_chat_get_supports_after_id_and_typing_flag():
    src = (REPO_ROOT / "mobile" / "api.py").read_text()
    assert 'request.args.get("after_id", type=int)' in src
    assert "peer_typing=is_peer_typing(cid, uid)" in src
