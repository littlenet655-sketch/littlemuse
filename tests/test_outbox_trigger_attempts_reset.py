"""Real PostgreSQL trigger re-enqueue must reset exhausted/completed outbox rows.

Python ENQUEUE_DELETE_SQL is covered separately. This suite fires the live
post and child_messages DELETE triggers after migration
20261002120000_outbox_trigger_attempts_reset.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NEW_MIGRATION = ROOT / "db/migrations/20261002120000_outbox_trigger_attempts_reset.sql"
HISTORICAL = ROOT / "db/migrations/20260907150000_final_runtime_invariants.sql"


def test_outbox_trigger_migration_exists_and_does_not_edit_history():
    files = sorted((ROOT / "db/migrations").glob("*.sql"))
    assert len(files) >= 43
    assert NEW_MIGRATION.is_file()
    new = NEW_MIGRATION.read_text(encoding="utf-8")
    hist = HISTORICAL.read_text(encoding="utf-8")
    assert "-- migrate:up" in new and "-- migrate:down" in new
    assert "THEN 0 ELSE media_delete_outbox.attempts" in new
    assert "attempts >= 8" in new
    assert "CREATE OR REPLACE FUNCTION littlenet_queue_post_media_delete()" in new
    assert "CREATE OR REPLACE FUNCTION littlenet_queue_message_media_delete()" in new
    # Historical file stays the original conflict clause (no attempts CASE).
    assert "ON CONFLICT(reference) DO UPDATE SET completed_at=NULL,last_error=NULL;" in hist
    assert "THEN 0 ELSE media_delete_outbox.attempts" not in hist


@pytest.mark.skipif(not os.getenv("DISPOSABLE_DATABASE_URL"), reason="Disposable PostgreSQL URL not configured")
def test_post_and_message_delete_triggers_reset_exhausted_and_completed_rows():
    import psycopg2
    from psycopg2.extras import RealDictCursor

    from database.connection import _database_timezone

    conn = psycopg2.connect(
        os.environ["DISPOSABLE_DATABASE_URL"],
        cursor_factory=RealDictCursor,
        connect_timeout=15,
        options=f"-c timezone={_database_timezone()}",
    )
    conn.autocommit = True
    cur = conn.cursor()
    suffix = uuid.uuid4().hex[:10]
    refs = {
        "post8": f"uploads/r2/test/trigger-post-8-{suffix}.mp4",
        "post4": f"uploads/r2/test/trigger-post-4-{suffix}.mp4",
        "postc": f"uploads/r2/test/trigger-post-c-{suffix}.mp4",
        "msg8": f"uploads/r2/test/trigger-msg-8-{suffix}.mp4",
        "msg4": f"uploads/r2/test/trigger-msg-4-{suffix}.mp4",
        "msgc": f"uploads/r2/test/trigger-msg-c-{suffix}.mp4",
    }
    user_ids = []
    post_ids = []
    message_ids = []
    try:
        def _child(name):
            cur.execute(
                """INSERT INTO users (username, full_name, email, password_hash, role, account_status)
                   VALUES (%s, %s, %s, 'test_hash', 'CHILD', 'ACTIVE')
                   RETURNING user_id""",
                (name, name, f"{name}@example.com"),
            )
            uid = cur.fetchone()["user_id"]
            user_ids.append(uid)
            cur.execute(
                "INSERT INTO child_profiles (child_id, full_name, age) VALUES (%s, %s, 10)",
                (uid, name),
            )
            return uid

        child_a = _child(f"trig_a_{suffix}")
        child_b = _child(f"trig_b_{suffix}")
        low, high = (child_a, child_b) if child_a < child_b else (child_b, child_a)
        cur.execute(
            "INSERT INTO child_conversations (child1_id, child2_id) VALUES (%s, %s) RETURNING conversation_id",
            (low, high),
        )
        conversation_id = cur.fetchone()["conversation_id"]

        def _post(ref):
            cur.execute(
                """INSERT INTO posts (child_id, media_type, media_path, caption, moderation_status, processing_status, is_safe)
                   VALUES (%s, 'VIDEO', %s, 'trigger fixture', 'ALLOWED', 'ALLOWED', TRUE)
                   RETURNING post_id""",
                (child_a, ref),
            )
            pid = cur.fetchone()["post_id"]
            post_ids.append(pid)
            return pid

        def _message(ref):
            cur.execute(
                """INSERT INTO child_messages
                     (conversation_id, sender_child_id, receiver_child_id, message_type, media_path, moderation_status)
                   VALUES (%s, %s, %s, 'VIDEO', %s, 'ALLOWED')
                   RETURNING child_message_id""",
                (conversation_id, child_a, child_b, ref),
            )
            mid = cur.fetchone()["child_message_id"]
            message_ids.append(mid)
            return mid

        def _seed(ref, attempts, completed=False):
            cur.execute(
                """INSERT INTO media_delete_outbox(reference, source_table, source_id, attempts, last_error)
                   VALUES (%s, 'compensation', NULL, %s, 'seed')""",
                (ref, attempts),
            )
            if completed:
                cur.execute(
                    "UPDATE media_delete_outbox SET completed_at=NOW() WHERE reference=%s",
                    (ref,),
                )

        def _row(ref):
            cur.execute(
                "SELECT attempts, completed_at, last_error FROM media_delete_outbox WHERE reference=%s",
                (ref,),
            )
            return cur.fetchone()

        def _pending(ref):
            cur.execute(
                """SELECT attempts FROM media_delete_outbox
                   WHERE reference=%s AND completed_at IS NULL AND attempts < 8""",
                (ref,),
            )
            return cur.fetchone()

        _seed(refs["post8"], 8)
        _seed(refs["post4"], 4)
        _seed(refs["postc"], 3, completed=True)
        _seed(refs["msg8"], 8)
        _seed(refs["msg4"], 4)
        _seed(refs["msgc"], 3, completed=True)

        post8 = _post(refs["post8"])
        post4 = _post(refs["post4"])
        postc = _post(refs["postc"])
        msg8 = _message(refs["msg8"])
        msg4 = _message(refs["msg4"])
        msgc = _message(refs["msgc"])

        cur.execute("SELECT pg_get_functiondef('littlenet_queue_post_media_delete()'::regprocedure)")
        post_fn = cur.fetchone()["pg_get_functiondef"]
        cur.execute("SELECT pg_get_functiondef('littlenet_queue_message_media_delete()'::regprocedure)")
        msg_fn = cur.fetchone()["pg_get_functiondef"]
        assert "THEN 0" in post_fn and "attempts >= 8" in post_fn
        assert "THEN 0" in msg_fn and "attempts >= 8" in msg_fn

        cur.execute("DELETE FROM posts WHERE post_id=%s", (post8,))
        cur.execute("DELETE FROM posts WHERE post_id=%s", (post4,))
        cur.execute("DELETE FROM posts WHERE post_id=%s", (postc,))
        cur.execute("DELETE FROM child_messages WHERE child_message_id=%s", (msg8,))
        cur.execute("DELETE FROM child_messages WHERE child_message_id=%s", (msg4,))
        cur.execute("DELETE FROM child_messages WHERE child_message_id=%s", (msgc,))

        assert _row(refs["post8"])["attempts"] == 0
        assert _row(refs["post8"])["completed_at"] is None
        assert _row(refs["post4"])["attempts"] == 4
        assert _row(refs["postc"])["attempts"] == 0
        assert _row(refs["postc"])["completed_at"] is None
        assert _row(refs["msg8"])["attempts"] == 0
        assert _row(refs["msg4"])["attempts"] == 4
        assert _row(refs["msgc"])["attempts"] == 0
        assert _pending(refs["post8"])["attempts"] == 0
        assert _pending(refs["msg8"])["attempts"] == 0

        for ref in (refs["post8"], refs["msg8"]):
            cur.execute("UPDATE media_delete_outbox SET attempts=8 WHERE reference=%s", (ref,))
            assert _pending(ref) is None
    finally:
        for mid in message_ids:
            cur.execute("DELETE FROM child_messages WHERE child_message_id=%s", (mid,))
        for pid in post_ids:
            cur.execute("DELETE FROM posts WHERE post_id=%s", (pid,))
        cur.execute("DELETE FROM media_delete_outbox WHERE reference LIKE %s", (f"uploads/r2/test/trigger-%{suffix}.mp4",))
        for uid in user_ids:
            cur.execute("DELETE FROM users WHERE user_id=%s", (uid,))
        conn.close()
