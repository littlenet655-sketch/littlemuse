import os
import re
import json
import uuid
from pathlib import Path
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import pytest
import psycopg2
from psycopg2.extras import RealDictCursor

from app import app
from mobile.api import _issue_token, _resolve_parent_review
from services import media_processor
from services.job_queue import enqueue_media_job
from config import Config


def _get_disposable_url():
    p = Path(".env.disposable")
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if "DATABASE_URL" in line:
                return line.split("=", 1)[1].strip().strip('"\'')
    return os.getenv("DISPOSABLE_DATABASE_URL") or os.getenv("DATABASE_URL")


DISPOSABLE_URL = _get_disposable_url()
pytestmark = pytest.mark.skipif(not DISPOSABLE_URL, reason="Disposable PostgreSQL URL not configured")


@pytest.fixture(scope="session", autouse=True)
def configure_disposable_db():
    Config.DATABASE_URL = DISPOSABLE_URL
    import database.connection as db_conn
    # Reset thread pool
    with db_conn._pool_lock:
        if db_conn._pool and not db_conn._pool.closed:
            db_conn._pool.closeall()
        db_conn._pool = None


@pytest.fixture
def db():
    conn = psycopg2.connect(DISPOSABLE_URL, cursor_factory=RealDictCursor)
    conn.autocommit = True
    yield conn
    conn.close()


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _random_user(db, role="CHILD"):
    suffix = uuid.uuid4().hex[:8]
    username = f"user_{suffix}"
    email = f"{username}@example.com"
    cur = db.cursor()
    cur.execute(
        """INSERT INTO users (username, full_name, email, password_hash, role, account_status)
           VALUES (%s, %s, %s, 'test_hash', %s, 'ACTIVE')
           RETURNING user_id, username, email, role, account_status""",
        (username, username, email, role),
    )
    user = cur.fetchone()
    if role == "CHILD":
        cur.execute(
            "INSERT INTO child_profiles (child_id, full_name, age) VALUES (%s, %s, 10)",
            (user["user_id"], username),
        )
    return user


def _auth_headers(user):
    token = _issue_token({"user_id": user["user_id"], "role": user["role"], "full_name": user["username"]})
    return {"Authorization": f"Bearer {token}"}


# ============================================================================
# 3. CONCURRENT /COMPLETE CALLS (EXACTLY ONE POST AND ONE LOGICAL JOB)
# ============================================================================

def test_concurrent_upload_complete_produces_exactly_one_post(client, db):
    user = _random_user(db, "CHILD")
    uid = user["user_id"]
    headers = _auth_headers(user)
    cur = db.cursor()


    upload_id = str(uuid.uuid4())
    object_key = f"uploads/r2/quarantine/{uid}/{upload_id}.jpg"
    cur.execute(
        """INSERT INTO upload_sessions(upload_id, child_id, object_key, media_type, kind, expected_size_bytes, mime_type, extension, status, expires_at)
           VALUES(%s, %s, %s, 'IMAGE', 'POST', 1000, 'image/jpeg', 'jpg', 'UPLOADED', NOW() + INTERVAL '1 hour')""",
        (upload_id, uid, object_key),
    )

    dispatched_jobs = []

    def fake_enqueue(post_id, child_id, key, kind):
        job_id = f"modal_job_{uuid.uuid4().hex[:8]}"
        dispatched_jobs.append(job_id)
        return job_id

    with patch("services.object_storage.enabled", return_value=True), \
         patch("services.object_storage.head_object", return_value={"content_length": 1000, "content_type": "image/jpeg"}), \
         patch("services.job_queue.enqueue_media_job", side_effect=fake_enqueue):

        def call_complete():
            with app.test_client() as c:
                return c.post(f"/api/mobile/v2/uploads/{upload_id}/complete", headers=headers, json={"caption": "Two simultaneous calls"})

        with ThreadPoolExecutor(max_workers=2) as executor:
            future1 = executor.submit(call_complete)
            future2 = executor.submit(call_complete)
            res1 = future1.result()
            res2 = future2.result()

        assert res1.status_code == 200
        assert res2.status_code == 200
        data1 = res1.get_json()
        data2 = res2.get_json()

        assert data1["ok"] is True
        assert data2["ok"] is True
        # Both must return the identical post_id
        assert data1["post_id"] == data2["post_id"]
        post_id = data1["post_id"]

        # Exactly ONE post row in DB
        cur.execute("SELECT COUNT(*) as cnt FROM posts WHERE upload_id=%s", (upload_id,))
        assert cur.fetchone()["cnt"] == 1

        # Exactly ONE upload_session marked CONSUMED
        cur.execute("SELECT status FROM upload_sessions WHERE upload_id=%s", (upload_id,))
        assert cur.fetchone()["status"] == "CONSUMED"

        # Exactly ONE logical job dispatched
        assert len(dispatched_jobs) == 1


# ============================================================================
# 4. DISPATCH FAILURE + RETRYABILITY
# ============================================================================

def test_dispatch_failure_and_idempotent_retry(client, db):
    user = _random_user(db, "CHILD")
    uid = user["user_id"]
    headers = _auth_headers(user)
    cur = db.cursor()


    upload_id = str(uuid.uuid4())
    object_key = f"uploads/r2/quarantine/{uid}/{upload_id}.jpg"
    cur.execute(
        """INSERT INTO upload_sessions(upload_id, child_id, object_key, media_type, kind, expected_size_bytes, mime_type, extension, status, expires_at)
           VALUES(%s, %s, %s, 'IMAGE', 'POST', 1000, 'image/jpeg', 'jpg', 'UPLOADED', NOW() + INTERVAL '1 hour')""",
        (upload_id, uid, object_key),
    )

    # 1. Initial attempt fails Modal spawn
    with patch("services.object_storage.enabled", return_value=True), \
         patch("services.object_storage.head_object", return_value={"content_length": 1000, "content_type": "image/jpeg"}), \
         patch("services.job_queue.enqueue_media_job", side_effect=RuntimeError("Modal capacity exhausted")):

        res = client.post(f"/api/mobile/v2/uploads/{upload_id}/complete", headers=headers, json={"caption": "Spawn failure test"})
        assert res.status_code == 503
        data = res.get_json()
        assert data["ok"] is False
        assert data["error"] == "job_dispatch_failed"
        assert data["retryable"] is True
        post_id = data["post_id"]

    # Verify DB post is UPLOADED with dispatch_failed error
    cur.execute("SELECT processing_status, processing_error FROM posts WHERE post_id=%s", (post_id,))
    p_row = cur.fetchone()
    assert p_row["processing_status"] == "UPLOADED"
    assert "dispatch_failed" in p_row["processing_error"]

    # 2. Retry succeeds
    with patch("services.object_storage.enabled", return_value=True), \
         patch("services.job_queue.enqueue_media_job", return_value="modal_retry_123"):

        retry_res = client.post(f"/api/mobile/v2/uploads/{upload_id}/complete", headers=headers, json={})
        assert retry_res.status_code == 200
        retry_data = retry_res.get_json()
        assert retry_data["ok"] is True
        assert retry_data["post_id"] == post_id
        assert retry_data["status"] == "PROCESSING"

    # Verify DB post is now PROCESSING
    cur.execute("SELECT processing_status, job_id, processing_error FROM posts WHERE post_id=%s", (post_id,))
    p_updated = cur.fetchone()
    assert p_updated["processing_status"] == "PROCESSING"
    assert p_updated["job_id"] == "modal_retry_123"
    assert p_updated["processing_error"] is None


# ============================================================================
# 5. BOUNDED REDRIVE & TERMINAL FAILURE
# ============================================================================

def test_bounded_redrive_terminates_at_max_attempts(db):
    user = _random_user(db, "CHILD")
    uid = user["user_id"]
    cur = db.cursor()
    src_key = f"uploads/r2/quarantine/{uuid.uuid4().hex}.jpg"

    cur.execute(
        """INSERT INTO posts(child_id, media_type, source_media_path, caption, processing_status, processing_attempts, max_processing_attempts, last_attempt_at)
           VALUES(%s, 'IMAGE', %s, 'Redrive test', 'PROCESSING', 2, 3, NOW() - INTERVAL '10 minutes')
           RETURNING post_id""",
        (uid, src_key),
    )
    post_id = cur.fetchone()["post_id"]

    # Attempt 3 (within limit) -> redrives
    with patch("services.job_queue.enqueue_media_job", return_value="job_attempt_3"):
        res = media_processor.redrive_media_job(post_id)
        assert res["ok"] is True
        assert res["attempts"] == 3

    # Attempt 4 (exceeds max_attempts of 3) -> terminates to FAILED
    res4 = media_processor.redrive_media_job(post_id)
    assert res4["ok"] is False
    assert res4["error"] == "max_attempts_exceeded"
    assert res4["status"] == "FAILED"

    cur.execute("SELECT processing_status, processing_error FROM posts WHERE post_id=%s", (post_id,))
    p = cur.fetchone()
    assert p["processing_status"] == "FAILED"
    assert p["processing_error"] == "max_attempts_exceeded"


def test_reap_stale_jobs_marks_exceeded_attempts_as_failed(db):
    user = _random_user(db, "CHILD")
    uid = user["user_id"]
    cur = db.cursor()
    src_key = f"uploads/r2/quarantine/{uuid.uuid4().hex}.jpg"

    cur.execute(
        """INSERT INTO posts(child_id, media_type, source_media_path, caption, processing_status,
                             processing_attempts, max_processing_attempts, created_at, processing_started_at)
           VALUES(%s, 'IMAGE', %s, 'Stale reaper test', 'PROCESSING',
                  3, 3, NOW() - INTERVAL '1 hour', NOW() - INTERVAL '1 hour')
           RETURNING post_id""",
        (uid, src_key),
    )
    post_id = cur.fetchone()["post_id"]

    res = media_processor.reap_stale_media_jobs(stale_seconds=300)
    assert res["ok"] is True
    failed_ids = [f["post_id"] for f in res.get("failed", [])]
    assert post_id in failed_ids

    cur.execute("SELECT processing_status, processing_error FROM posts WHERE post_id=%s", (post_id,))
    p = cur.fetchone()
    assert p["processing_status"] == "FAILED"
    assert "max_attempts_exceeded" in p["processing_error"]


# ============================================================================
# 6. REVIEW LIFECYCLE: APPROVE & BLOCK ORDERING
# ============================================================================

def test_real_db_review_approval_lifecycle(db):
    parent = _random_user(db, "PARENT")
    child = _random_user(db, "CHILD")
    pid = parent["user_id"]
    cid = child["user_id"]
    cur = db.cursor()

    # Map parent to child
    cur.execute(
        """INSERT INTO parent_child_map(parent_id, child_id, parent_name, parent_email, approved, approval_status)
           VALUES(%s, %s, %s, %s, TRUE, 'APPROVED')""",
        (pid, cid, parent["username"], parent["email"]),
    )

    src_key = f"uploads/r2/quarantine/{uuid.uuid4().hex}.jpg"
    cur.execute(
        """INSERT INTO posts(child_id, media_type, source_media_path, caption, moderation_status, processing_status, is_safe)
           VALUES(%s, 'IMAGE', %s, 'Please approve', 'REVIEW', 'REVIEW', FALSE)
           RETURNING post_id""",
        (cid, src_key),
    )
    post_id = cur.fetchone()["post_id"]

    cur.execute(
        """INSERT INTO moderation_events(child_id, content_type, content_id, decision, status)
           VALUES(%s, 'IMAGE', %s, 'REVIEW', 'OPEN')
           RETURNING event_id""",
        (cid, post_id),
    )
    event_id = cur.fetchone()["event_id"]

    notifications_sent = []
    quarantine_cleaned = []

    def fake_notify(p_id, c_id, kind):
        notifications_sent.append(p_id)

    def fake_cleanup(p_id, key):
        quarantine_cleaned.append(key)
        return True

    with patch("services.media_processor.sanitize_and_promote_media", return_value=("uploads/r2/posts/clean.jpg", None)), \
         patch("services.media_processor._notify_approved_followers", side_effect=fake_notify), \
         patch("services.media_processor.block_and_cleanup_quarantine", side_effect=fake_cleanup):

        ok, result = _resolve_parent_review(pid, event_id, "APPROVE")
        assert ok is True
        assert result == "APPROVE"

    # Post must be ALLOWED in DB
    cur.execute("SELECT moderation_status, processing_status, is_safe, media_path FROM posts WHERE post_id=%s", (post_id,))
    post = cur.fetchone()
    assert post["moderation_status"] == "ALLOWED"
    assert post["processing_status"] == "ALLOWED"
    assert post["is_safe"] is True
    assert post["media_path"] == "uploads/r2/posts/clean.jpg"

    # Event resolved
    cur.execute("SELECT status FROM moderation_events WHERE event_id=%s", (event_id,))
    assert cur.fetchone()["status"] == "RESOLVED"

    # Review recorded
    cur.execute("SELECT action FROM moderation_reviews WHERE event_id=%s", (event_id,))
    assert cur.fetchone()["action"] == "APPROVE"

    # Post-commit hooks fired
    assert post_id in notifications_sent
    assert src_key in quarantine_cleaned


def test_real_db_review_block_lifecycle(db):
    parent = _random_user(db, "PARENT")
    child = _random_user(db, "CHILD")
    pid = parent["user_id"]
    cid = child["user_id"]
    cur = db.cursor()

    cur.execute(
        """INSERT INTO parent_child_map(parent_id, child_id, parent_name, parent_email, approved, approval_status)
           VALUES(%s, %s, %s, %s, TRUE, 'APPROVED')""",
        (pid, cid, parent["username"], parent["email"]),
    )

    src_key = f"uploads/r2/quarantine/{uuid.uuid4().hex}.jpg"
    cur.execute(
        """INSERT INTO posts(child_id, media_type, source_media_path, caption, moderation_status, processing_status, is_safe)
           VALUES(%s, 'IMAGE', %s, 'Dangerous', 'REVIEW', 'REVIEW', FALSE)
           RETURNING post_id""",
        (cid, src_key),
    )
    post_id = cur.fetchone()["post_id"]

    cur.execute(
        """INSERT INTO moderation_events(child_id, content_type, content_id, decision, status)
           VALUES(%s, 'IMAGE', %s, 'REVIEW', 'OPEN')
           RETURNING event_id""",
        (cid, post_id),
    )
    event_id = cur.fetchone()["event_id"]

    quarantine_cleaned = []

    def fake_cleanup(p_id, key):
        quarantine_cleaned.append(key)
        return True

    with patch("services.media_processor.block_and_cleanup_quarantine", side_effect=fake_cleanup):
        ok, result = _resolve_parent_review(pid, event_id, "BLOCK")
        assert ok is True
        assert result == "BLOCK"

    # Post must be BLOCKED in DB with media_path NULL
    cur.execute("SELECT moderation_status, processing_status, is_safe, media_path FROM posts WHERE post_id=%s", (post_id,))
    post = cur.fetchone()
    assert post["moderation_status"] == "BLOCKED"
    assert post["processing_status"] == "BLOCKED"
    assert post["is_safe"] is False
    assert post["media_path"] is None

    # Event resolved
    cur.execute("SELECT status FROM moderation_events WHERE event_id=%s", (event_id,))
    assert cur.fetchone()["status"] == "RESOLVED"

    # Quarantine cleanup called after DB commit
    assert src_key in quarantine_cleaned


# ============================================================================
# 7. CLEANUP FAILURE ENQUEUES TO OUTBOX
# ============================================================================

def test_quarantine_cleanup_failure_enqueues_to_media_outbox(db):
    user = _random_user(db, "CHILD")
    uid = user["user_id"]
    cur = db.cursor()
    bad_key = f"uploads/r2/quarantine/{uuid.uuid4().hex}.jpg"

    cur.execute(
        """INSERT INTO posts(child_id, media_type, source_media_path, caption, moderation_status, processing_status)
           VALUES(%s, 'IMAGE', %s, 'Cleanup fail', 'BLOCKED', 'BLOCKED')
           RETURNING post_id""",
        (uid, bad_key),
    )
    post_id = cur.fetchone()["post_id"]

    outbox_entries = []

    def fake_enqueue_delete(key, table, row_id):
        outbox_entries.append({"key": key, "table": table, "id": row_id})

    with patch("services.object_storage.enabled", return_value=True), \
         patch("services.object_storage.delete_reference", side_effect=RuntimeError("R2 500 internal error")), \
         patch("services.media_outbox.enqueue_delete", side_effect=fake_enqueue_delete):

        cleaned = media_processor.block_and_cleanup_quarantine(post_id, bad_key)
        assert cleaned is False
        assert len(outbox_entries) == 1
        assert outbox_entries[0]["key"] == bad_key
        assert outbox_entries[0]["id"] == post_id


# ============================================================================
# 8. ATOMIC WORKER CLAIM & CONCURRENCY VALIDATION
# ============================================================================

def test_concurrency_two_workers_one_post_results_in_exactly_one_processing_owner(db):
    """Proves two concurrent Modal workers for the same post result in exactly one processing owner."""
    import time
    import io
    from PIL import Image
    from safety.policy import Decision

    user = _random_user(db, "CHILD")
    uid = user["user_id"]
    cur = db.cursor()
    src_key = f"uploads/r2/quarantine/{uuid.uuid4().hex}.jpg"

    buf = io.BytesIO()
    Image.new("RGB", (10, 10), color="blue").save(buf, format="JPEG")
    valid_jpg = buf.getvalue()
    local_file = Path(src_key)
    local_file.parent.mkdir(parents=True, exist_ok=True)
    local_file.write_bytes(valid_jpg)

    try:
        cur.execute(
            """INSERT INTO posts(child_id, media_type, source_media_path, caption, processing_status,
                                 processing_attempts, max_processing_attempts, is_safe, moderation_status)
               VALUES(%s, 'IMAGE', %s, 'Two workers test', 'PROCESSING', 1, 3, FALSE, 'PENDING')
               RETURNING post_id""",
            (uid, src_key),
        )
        post_id = cur.fetchone()["post_id"]

        mock_decision = Decision(action="ALLOW", risk=0.0, reason="clean_content")
        notify_calls = []

        def fake_notify(p_id, c_id, kind):
            notify_calls.append((p_id, c_id))

        with patch("services.media_processor.evaluate", return_value=({"adult_score": 0.0, "violence_score": 0.0, "risk_score": 0.0}, None)) as mock_eval, \
             patch("services.media_processor.object_storage.enabled", return_value=False), \
             patch("services.media_processor.block_and_cleanup_quarantine", return_value=True), \
             patch("services.media_processor._notify_approved_followers", side_effect=fake_notify):

            def run_worker():
                return media_processor.process_media_job(post_id, uid, src_key, "POST")

            with ThreadPoolExecutor(max_workers=2) as executor:
                fut1 = executor.submit(run_worker)
                fut2 = executor.submit(run_worker)
                res1 = fut1.result()
                res2 = fut2.result()

        # Verify results
        assert res1.get("ok") is True
        assert res2.get("ok") is True

        winner = res1 if not res1.get("already_claimed") else res2
        loser = res2 if winner is res1 else res1

        # Exactly one winner processed the media
        assert winner.get("status") == "ALLOWED"
        assert winner.get("already_claimed") is not True

        # Exactly one loser exited idempotently
        assert loser.get("already_claimed") is True
        assert loser.get("idempotent") is True

        # Exactly one worker owns moderation. The versioned moderation cache may
        # satisfy either/both signals, so model evaluation can be 0-2 calls but
        # must never duplicate work across the losing worker.
        assert mock_eval.call_count <= 2
        assert len(notify_calls) == 1

        # In DB, post is ALLOWED with cleared lease
        cur.execute("SELECT processing_status, moderation_status, is_safe, media_path, processing_lease_token FROM posts WHERE post_id=%s", (post_id,))
        p = cur.fetchone()
        assert p["processing_status"] == "ALLOWED"
        assert p["moderation_status"] == "ALLOWED"
        assert p["is_safe"] is True
        assert p["media_path"] is not None
        assert p["processing_lease_token"] is None
    finally:
        local_file.unlink(missing_ok=True)


def test_concurrency_simultaneous_reaper_and_redrive_creates_one_logical_attempt(db):
    """Proves simultaneous reaper and redrive calls create exactly one logical attempt."""
    user = _random_user(db, "CHILD")
    uid = user["user_id"]
    cur = db.cursor()
    src_key = f"uploads/r2/quarantine/{uuid.uuid4().hex}.jpg"

    # Insert a stale post whose lease has expired
    cur.execute(
        """INSERT INTO posts(child_id, media_type, source_media_path, caption, processing_status,
                             processing_attempts, max_processing_attempts, created_at, processing_started_at,
                             last_attempt_at, processing_lease_token, processing_lease_expires_at)
           VALUES(%s, 'IMAGE', %s, 'Reaper vs redrive test', 'PROCESSING',
                  1, 3, NOW() - INTERVAL '15 minutes', NOW() - INTERVAL '15 minutes',
                  NOW() - INTERVAL '15 minutes', 'expired_lease_token', NOW() - INTERVAL '5 minutes')
           RETURNING post_id""",
        (uid, src_key),
    )
    post_id = cur.fetchone()["post_id"]

    dispatched_jobs = []

    def fake_enqueue(p_id, c_id, key, kind, lease_token=None):
        job_id = f"job_{uuid.uuid4().hex[:8]}"
        dispatched_jobs.append((p_id, lease_token))
        return job_id

    with patch("services.job_queue.enqueue_media_job", side_effect=fake_enqueue):
        def run_reaper():
            return media_processor.reap_stale_media_jobs(stale_seconds=300)

        def run_redrive():
            return media_processor.redrive_media_job(post_id)

        with ThreadPoolExecutor(max_workers=2) as executor:
            fut_reap = executor.submit(run_reaper)
            fut_redrive = executor.submit(run_redrive)
            res_reap = fut_reap.result()
            res_redrive = fut_redrive.result()

    # Exactly ONE dispatch occurred for this post across both concurrent operations
    post_dispatches = [job for job in dispatched_jobs if job[0] == post_id]
    assert len(post_dispatches) == 1

    # In DB, processing_attempts was incremented exactly ONCE (from 1 to 2, not 3)
    cur.execute("SELECT processing_attempts, processing_lease_token, processing_lease_expires_at FROM posts WHERE post_id=%s", (post_id,))
    p = cur.fetchone()
    assert p["processing_attempts"] == 2
    assert p["processing_lease_token"] is not None
    assert p["processing_lease_token"] == post_dispatches[0][1]


def test_concurrency_crash_retry_remains_recoverable(db):
    """Proves crash/retry remains recoverable: an expired lease from a crashed worker can be claimed."""
    import io
    from PIL import Image
    from safety.policy import Decision

    user = _random_user(db, "CHILD")
    uid = user["user_id"]
    cur = db.cursor()
    src_key = f"uploads/r2/quarantine/{uuid.uuid4().hex}.jpg"

    buf = io.BytesIO()
    Image.new("RGB", (10, 10), color="green").save(buf, format="JPEG")
    valid_jpg = buf.getvalue()
    local_file = Path(src_key)
    local_file.parent.mkdir(parents=True, exist_ok=True)
    local_file.write_bytes(valid_jpg)

    try:
        # Simulate crashed worker that left an expired lease
        crashed_token = "crashed_worker_lease_999"
        cur.execute(
            """INSERT INTO posts(child_id, media_type, source_media_path, caption, processing_status,
                                 processing_attempts, max_processing_attempts, processing_started_at,
                                 last_attempt_at, processing_lease_token, processing_lease_expires_at,
                                 is_safe, moderation_status)
               VALUES(%s, 'IMAGE', %s, 'Crashed worker recovery', 'PROCESSING',
                      1, 3, NOW() - INTERVAL '10 minutes',
                      NOW() - INTERVAL '10 minutes', %s, NOW() - INTERVAL '1 minute',
                      FALSE, 'PENDING')
               RETURNING post_id""",
            (uid, src_key, crashed_token),
        )
        post_id = cur.fetchone()["post_id"]

        # Redrive or new worker claims the expired lease
        acquired, new_token, post_data = media_processor.claim_media_job_lease(post_id)
        assert acquired is True
        assert new_token is not None
        assert new_token != crashed_token

        # Verify DB reflects the new lease
        cur.execute("SELECT processing_lease_token, processing_attempts FROM posts WHERE post_id=%s", (post_id,))
        p = cur.fetchone()
        assert p["processing_lease_token"] == new_token
        assert p["processing_attempts"] == 2

        # Worker executes with new lease token to completion
        with patch("services.media_processor.evaluate", return_value=({"adult_score": 0.0, "violence_score": 0.0, "risk_score": 0.0}, None)), \
             patch("services.media_processor.block_and_cleanup_quarantine", return_value=True), \
             patch("services.media_processor._notify_approved_followers", return_value=None):

            res = media_processor.process_media_job(post_id, uid, src_key, "POST", lease_token=new_token)
            assert res.get("ok") is True
            assert res.get("status") == "ALLOWED"

        cur.execute("SELECT processing_status, media_path, processing_lease_token FROM posts WHERE post_id=%s", (post_id,))
        p_final = cur.fetchone()
        assert p_final["processing_status"] == "ALLOWED"
        assert p_final["media_path"] is not None
        assert "_media.jpg" in p_final["media_path"]
        assert p_final["processing_lease_token"] is None
    finally:
        local_file.unlink(missing_ok=True)


def test_terminal_states_never_reprocessed(db):
    """Proves terminal states (ALLOWED, BLOCKED, FAILED) are never claimed or reprocessed."""
    user = _random_user(db, "CHILD")
    uid = user["user_id"]
    cur = db.cursor()

    for term_status in ("ALLOWED", "BLOCKED", "FAILED"):
        mod_status = "BLOCKED" if term_status == "FAILED" else term_status
        src_key = f"uploads/r2/quarantine/{uuid.uuid4().hex}.jpg"
        cur.execute(
            """INSERT INTO posts(child_id, media_type, source_media_path, caption, processing_status,
                                 processing_attempts, max_processing_attempts, moderation_status,
                                 is_safe, created_at, processing_started_at)
               VALUES(%s, 'IMAGE', %s, 'Terminal test', %s,
                      2, 3, %s,
                      %s, NOW() - INTERVAL '1 hour', NOW() - INTERVAL '1 hour')
               RETURNING post_id""",
            (uid, src_key, term_status, mod_status, term_status == "ALLOWED"),
        )
        post_id = cur.fetchone()["post_id"]

        # 1. claim_media_job_lease must reject terminal state
        acquired, token, _ = media_processor.claim_media_job_lease(post_id)
        assert acquired is False
        assert token is None

        # 2. redrive_media_job must not reprocess or spawn terminal state
        redrive_res = media_processor.redrive_media_job(post_id)
        if term_status in ("ALLOWED", "BLOCKED"):
            assert redrive_res["ok"] is True
            assert redrive_res.get("idempotent") is True
            assert redrive_res["status"] == term_status
        else:
            assert redrive_res["ok"] is False
            assert redrive_res["status"] == "FAILED"

        # 3. process_media_job must exit immediately without running AI
        with patch("services.media_processor.evaluate") as mock_eval:
            proc_res = media_processor.process_media_job(post_id, uid, src_key, "POST")
            if term_status == "FAILED":
                assert proc_res["ok"] is False
                assert proc_res["status"] == "FAILED"
                assert proc_res.get("idempotent") is True
            else:
                assert proc_res["ok"] is True
                assert proc_res["status"] == term_status
                assert proc_res.get("idempotent") is True
            assert not mock_eval.called

        # 4. Status in DB must remain strictly unchanged
        cur.execute("SELECT processing_status, processing_attempts FROM posts WHERE post_id=%s", (post_id,))
        p = cur.fetchone()
        assert p["processing_status"] == term_status
        assert p["processing_attempts"] == 2

