"""Messaging safety: REVIEW/pending chat messages must never be delivered to the receiver.

Required state model:
  - REVIEW (pending) -> stored; visible to the SENDER as a pending state
    (moderation_status exposed); NOT returned by any receiver read path; no
    child notification; no unread.
  - ALLOW (review approved) -> delivered; receiver notified; shows as unread.
  - BLOCK -> never delivered; never notified.

Part 1 of this file runs anywhere (no DB, no Flask): it stubs the database and
social layers and asserts the receiver-side SQL contract of
childMessage.service.messages(), plus static guards on the send/review code.
Part 2 is the end-to-end lifecycle test against a disposable PostgreSQL,
following the repo's DISPOSABLE_DATABASE_URL harness (skipped when absent).
"""

import importlib
import os
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest

REPO_ROOT = Path(__file__).parents[1]


# ---------------------------------------------------------------------------
# Part 1: DB-free contract tests (stubs for database.connection/services.social)
# ---------------------------------------------------------------------------

@pytest.fixture
def message_service(monkeypatch):
    """Import childMessage.service with stubbed DB/social layers.

    Returns (service_module, calls) where `calls` records SQL and lets the test
    script fake rows for conversation lookup and message fetch.
    """
    calls = {"can_interact": True, "rows": [], "conv": None}

    db = types.ModuleType("database.connection")

    def fake_fetch_one(sql, params=None):
        calls["last_fetch_one_sql"] = sql
        return calls["conv"]

    def fake_fetch_all(sql, params=None):
        calls["last_fetch_all_sql"] = sql
        calls["last_fetch_all_params"] = params
        return list(calls["rows"])

    db.fetch_one = fake_fetch_one
    db.fetch_all = fake_fetch_all
    db.execute = lambda *a, **k: None
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


def _receiver_rows():
    return [
        {"child_message_id": 1, "moderation_status": "ALLOWED",
         "message_text": "hi", "sender_child_id": 7},
    ]


def test_receiver_fetch_query_excludes_non_allow_messages(message_service):
    """The receiver-side message query must restrict visibility to ALLOWED
    messages (plus the viewer's own rows, so the sender can see pending)."""
    svc, calls = message_service
    calls["conv"] = {"child1_id": 5, "child2_id": 7}
    calls["rows"] = _receiver_rows()
    rows = svc.messages(11, 7)  # viewer 7 is the receiver
    sql = calls["last_fetch_all_sql"]
    assert "m.moderation_status = 'ALLOWED'" in sql
    assert "m.sender_child_id = %s AND m.moderation_status = 'REVIEW'" in sql, (
        "receiver read path lost its moderation filter; REVIEW messages would "
        "be delivered as ordinary messages"
    )
    assert "m.is_deleted = FALSE" in sql
    assert rows == list(reversed(_receiver_rows()))


def test_sender_sees_own_review_message_as_pending(message_service):
    """The sender may see their own REVIEW message; the pending state must be
    exposed via moderation_status so clients can render 'pending'."""
    svc, calls = message_service
    calls["conv"] = {"child1_id": 5, "child2_id": 7}
    calls["rows"] = [
        {"child_message_id": 9, "moderation_status": "REVIEW",
         "message_text": "pending text", "sender_child_id": 5},
        {"child_message_id": 1, "moderation_status": "ALLOWED",
         "message_text": "hi", "sender_child_id": 7},
    ]
    rows = svc.messages(11, 5)  # viewer 5 is the sender
    pending = [r for r in rows if r["child_message_id"] == 9]
    assert pending and pending[0]["moderation_status"] == "REVIEW"


def test_read_path_returns_nothing_when_relationship_broken(message_service):
    """Block/mute/relationship state is enforced on the READ path, not just on
    send: with can_interact False no message rows are exposed at all."""
    svc, calls = message_service
    calls["conv"] = {"child1_id": 5, "child2_id": 7}
    calls["can_interact"] = False
    calls["rows"] = _receiver_rows()
    assert svc.messages(11, 7) == []
    assert svc.conversation(5, 7) is None


def test_send_and_list_paths_mark_and_snippet_only_allowed():
    """Static guards: the web send/list code must (a) notify the receiver only
    on ALLOW, and (b) compute last-message/unread and mark-seen from ALLOWED
    messages only."""
    src = (REPO_ROOT / "childMessage" / "routes.py").read_text(encoding="utf-8")
    # REVIEW branch notifies the parent only; the child notify() lives in the
    # ALLOW (else) branch.
    assert "if final_action=='REVIEW':parent_notify(" in src
    assert "else:notify(child_id,'MESSAGE'" in src
    # Conversation-list last message snippet ignores pending/review messages.
    assert "WHERE conversation_id = %s AND moderation_status = 'ALLOWED'" in src
    # Opening a chat marks only ALLOWED messages seen (no phantom unread flip).
    assert "AND receiver_child_id=%s AND moderation_status=\\'ALLOWED\\'" in src


def test_review_resolution_notifies_receiver_on_approve_and_converts_on_broken_link():
    """Static guards on mobile/api.py _resolve_parent_review: approving a
    REVIEW message must notify the receiver (delivery), while an approval
    requested after the pair was blocked/disconnected must be converted to a
    block, matching the web parent review path."""
    src = (REPO_ROOT / "mobile" / "api.py").read_text(encoding="utf-8")
    # Relationship-safe conversion of APPROVE -> BLOCK.
    assert "approval safely converted to block" in src
    assert "SELECT 1 FROM blocked_users WHERE (blocker_id=%s AND blocked_id=%s)" in src
    assert "approval_stage='ACTIVE'" in src
    # Receiver notification fires only for MESSAGE events resolved to APPROVE,
    # after the DB commit; BLOCKED messages are never notified.
    notify_guard = 'if event["content_type"] == "MESSAGE" and event.get("content_id") and effective == "APPROVE":'
    assert notify_guard in src
    assert src.index("conn.commit()") < src.index(notify_guard)
    assert 'notify(\n                    msg["receiver_child_id"],' in src


# ---------------------------------------------------------------------------
# Part 2: end-to-end lifecycle against a disposable PostgreSQL
# ---------------------------------------------------------------------------

def _disposable_url():
    p = Path(".env.disposable")
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if "DATABASE_URL" in line:
                return line.split("=", 1)[1].strip().strip("\"'")
    return os.getenv("DISPOSABLE_DATABASE_URL") or ""


def _require_live_db():
    url = _disposable_url()
    if not url:
        pytest.skip("DISPOSABLE_DATABASE_URL / .env.disposable not configured")
    hostname = (urlparse(url).hostname or "").lower()
    assert hostname and hostname not in {"localhost", "127.0.0.1"}, (
        "refusing to run messaging lifecycle test against a non-disposable database host"
    )
    return url


@pytest.fixture(scope="module")
def live_db():
    url = _require_live_db()
    from config import Config
    Config.DATABASE_URL = url
    import database.connection as db_conn
    with db_conn._pool_lock:
        if db_conn._pool and not db_conn._pool.closed:
            db_conn._pool.closeall()
        db_conn._pool = None
    yield url


def _login_as(client, uid):
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["role"] = "CHILD"


def _mk_review_decision(monkeypatch):
    """Force the moderation pipeline in childMessage.routes to REVIEW."""
    import childMessage.routes as routes
    from safety.policy import Decision
    monkeypatch.setattr(
        routes, "evaluate",
        lambda uid, ct, text: ({"test": True}, Decision("REVIEW", 50.0, "test forced review")),
    )
    import safety.pii_service as pii
    monkeypatch.setattr(
        pii, "scan_pii",
        lambda text: {"detected": False, "policy_action": "ALLOW", "categories": []},
    )
    import services.ai as ai_mod
    stub = SimpleNamespace(
        evaluate_chat_safety=lambda recent, a, b, text: SimpleNamespace(
            action="ALLOW", risk_score=0.0, reason_code="test_ok", primary_category="none"
        )
    )
    monkeypatch.setattr(ai_mod, "get_ai_client", lambda: stub)


def _ensure_pair(sender, receiver):
    from database.connection import execute
    execute(
        """INSERT INTO followers(child_id, following_child_id, approved, approval_stage)
           VALUES (%s,%s,TRUE,'ACTIVE') ON CONFLICT (child_id,following_child_id)
           DO UPDATE SET approved=TRUE, approval_stage='ACTIVE'""",
        (sender, receiver),
    )


def test_review_message_lifecycle_end_to_end(monkeypatch, live_db):
    """Full lifecycle: REVIEW send -> hidden from receiver -> approve -> visible
    + notified -> BLOCK variant never delivered."""
    from app import app
    from database.connection import execute, fetch_one
    from childMessage.service import conversation, messages
    from mobile.api import _resolve_parent_review

    app.config["TESTING"] = True
    client = app.test_client()

    me = fetch_one("SELECT user_id FROM users WHERE role='CHILD' AND account_status='ACTIVE' ORDER BY user_id LIMIT 1")
    other = fetch_one(
        "SELECT user_id FROM users WHERE role='CHILD' AND account_status='ACTIVE' AND user_id<>%s ORDER BY user_id LIMIT 1",
        (me["user_id"],),
    )
    assert me and other, "lifecycle test needs two active CHILD fixtures"
    s, r = me["user_id"], other["user_id"]
    _ensure_pair(s, r)
    from database.connection import execute as _exec
    for _uid in (s, r):
        _exec(
            "INSERT INTO child_quiz_progress(child_id, quiz_required) VALUES(%s, FALSE) "
            "ON CONFLICT (child_id) DO UPDATE SET quiz_required=FALSE",
            (_uid,),
        )

    tag = f"lifecycle-{os.getpid()}"
    _mk_review_decision(monkeypatch)

    notif_before = (fetch_one(
        "SELECT COUNT(*) n FROM notifications WHERE user_id=%s AND notification_type='MESSAGE'", (r,)
    ) or {"n": 0})["n"]

    # 1. Sender posts a message that the (mocked) moderator flags for REVIEW.
    _login_as(client, s)
    resp = client.post(f"/send-message/{r}/", data={"message_text": f"pending hello {tag}"})
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    assert resp.get_json()["status"] == "REVIEW"

    cid = conversation(s, r)
    row = fetch_one(
        "SELECT child_message_id, moderation_status FROM child_messages "
        "WHERE conversation_id=%s AND message_text=%s",
        (cid, f"pending hello {tag}"),
    )
    assert row and row["moderation_status"] == "REVIEW"
    mid = row["child_message_id"]

    # 2. Receiver fetch must NOT include the REVIEW message (no ordinary delivery).
    assert not [m for m in messages(cid, r) if m["child_message_id"] == mid]
    _login_as(client, r)
    api_rows = client.get(f"/api/chat/{s}/messages/").get_json()
    assert not [m for m in api_rows if m.get("message_text") == f"pending hello {tag}"]

    # 3. Sender sees it as pending.
    sender_rows = [m for m in messages(cid, s) if m["child_message_id"] == mid]
    assert sender_rows and sender_rows[0]["moderation_status"] == "REVIEW"

    # 4. No notification / unread for the undelivered REVIEW message.
    notif_after = (fetch_one(
        "SELECT COUNT(*) n FROM notifications WHERE user_id=%s AND notification_type='MESSAGE'", (r,)
    ) or {"n": 0})["n"]
    assert notif_after == notif_before
    last = fetch_one(
        "SELECT message_text FROM child_messages WHERE conversation_id=%s "
        "AND moderation_status='ALLOWED' ORDER BY sent_at DESC LIMIT 1", (cid,)
    )
    assert not last or last["message_text"] != f"pending hello {tag}"

    # 5. Parent review approves -> receiver notified and message becomes visible.
    ev = execute(
        "INSERT INTO moderation_events(child_id, content_type, content_id, decision, status) "
        "VALUES (%s,'MESSAGE',%s,'REVIEW','OPEN') RETURNING event_id",
        (s, mid), returning=True,
    )
    ok, result = _resolve_parent_review(r, ev["event_id"], "APPROVE", is_admin=True)
    assert ok and result == "APPROVE"
    assert fetch_one(
        "SELECT moderation_status m FROM child_messages WHERE child_message_id=%s", (mid,)
    )["m"] == "ALLOWED"
    assert [m for m in messages(cid, r) if m["child_message_id"] == mid]
    notif_final = (fetch_one(
        "SELECT COUNT(*) n FROM notifications WHERE user_id=%s AND notification_type='MESSAGE'", (r,)
    ) or {"n": 0})["n"]
    assert notif_final == notif_before + 1

    # 6. BLOCK variant: a second REVIEW message resolved to BLOCK is never delivered.
    resp2 = client.post(f"/send-message/{r}/", data={"message_text": f"blocked hello {tag}"})
    assert resp2.get_json()["status"] == "REVIEW"
    row2 = fetch_one(
        "SELECT child_message_id FROM child_messages WHERE conversation_id=%s AND message_text=%s",
        (cid, f"blocked hello {tag}"),
    )
    mid2 = row2["child_message_id"]
    ev2 = execute(
        "INSERT INTO moderation_events(child_id, content_type, content_id, decision, status) "
        "VALUES (%s,'MESSAGE',%s,'REVIEW','OPEN') RETURNING event_id",
        (s, mid2), returning=True,
    )
    ok2, result2 = _resolve_parent_review(r, ev2["event_id"], "BLOCK", is_admin=True)
    assert ok2 and result2 == "BLOCK"
    assert fetch_one(
        "SELECT moderation_status m FROM child_messages WHERE child_message_id=%s", (mid2,)
    )["m"] == "BLOCKED"
    assert not [m for m in messages(cid, r) if m["child_message_id"] == mid2]
    # The sender's own blocked message is still visible to the sender (they know
    # they sent it), but it is never delivered to the receiver.
    assert [m for m in messages(cid, s) if m["child_message_id"] == mid2]
    notif_block = (fetch_one(
        "SELECT COUNT(*) n FROM notifications WHERE user_id=%s AND notification_type='MESSAGE'", (r,)
    ) or {"n": 0})["n"]
    assert notif_block == notif_final  # no new notification on block

    # Cleanup test rows.
    execute("DELETE FROM child_messages WHERE child_message_id IN (%s,%s)", (mid, mid2))
    execute("DELETE FROM moderation_events WHERE event_id IN (%s,%s)", (ev["event_id"], ev2["event_id"]))
    execute(
        "DELETE FROM notifications WHERE user_id=%s AND notification_type='MESSAGE' AND created_at > NOW() - INTERVAL '1 hour'",
        (r,),
    )


def test_review_approval_converts_to_block_when_pair_disconnected(monkeypatch, live_db):
    """If the pair is blocked between send and review, an APPROVE request must
    be converted to BLOCK (fail-closed), matching the web parent review path."""
    from database.connection import execute, fetch_one
    from mobile.api import _resolve_parent_review

    me = fetch_one("SELECT user_id FROM users WHERE role='CHILD' AND account_status='ACTIVE' ORDER BY user_id LIMIT 1")
    other = fetch_one(
        "SELECT user_id FROM users WHERE role='CHILD' AND account_status='ACTIVE' AND user_id<>%s ORDER BY user_id LIMIT 1",
        (me["user_id"],),
    )
    assert me and other
    s, r = me["user_id"], other["user_id"]
    _ensure_pair(s, r)

    tag = f"convert-{os.getpid()}"
    mid = execute(
        """INSERT INTO child_messages(conversation_id, sender_child_id, receiver_child_id,
                                      message_type, message_text, moderation_status)
           SELECT conversation_id, %s, %s, 'TEXT', %s, 'REVIEW' FROM child_conversations
           WHERE (child1_id=%s AND child2_id=%s) OR (child1_id=%s AND child2_id=%s)
           LIMIT 1 RETURNING child_message_id""",
        (s, r, f"convert me {tag}", min(s, r), max(s, r), min(s, r), max(s, r)),
        returning=True,
    )
    if not mid:
        from childMessage.service import conversation as conv_fn
        cid = conv_fn(s, r)
        mid = execute(
            "INSERT INTO child_messages(conversation_id,sender_child_id,receiver_child_id,"
            "message_type,message_text,moderation_status) VALUES(%s,%s,%s,'TEXT',%s,'REVIEW') "
            "RETURNING child_message_id",
            (cid, s, r, f"convert me {tag}"), returning=True,
        )
    mid = mid["child_message_id"]
    ev = execute(
        "INSERT INTO moderation_events(child_id, content_type, content_id, decision, status) "
        "VALUES (%s,'MESSAGE',%s,'REVIEW','OPEN') RETURNING event_id",
        (s, mid), returning=True,
    )

    # Break the relationship before the review lands.
    execute(
        "INSERT INTO blocked_users(blocker_id, blocked_id) VALUES (%s,%s) "
        "ON CONFLICT (blocker_id, blocked_id) DO NOTHING",
        (r, s),
    )
    try:
        ok, result = _resolve_parent_review(r, ev["event_id"], "APPROVE", is_admin=True)
        assert ok and result == "BLOCK", "approval must convert to block when pair is blocked"
        assert fetch_one(
            "SELECT moderation_status m FROM child_messages WHERE child_message_id=%s", (mid,)
        )["m"] == "BLOCKED"
    finally:
        execute("DELETE FROM blocked_users WHERE blocker_id=%s AND blocked_id=%s", (r, s))
        execute("DELETE FROM child_messages WHERE child_message_id=%s", (mid,))
        execute("DELETE FROM moderation_events WHERE event_id=%s", (ev["event_id"],))
