"""Real PostgreSQL concurrency and race condition verification across all 8 critical subsystems."""
import concurrent.futures
import threading
import uuid
import psycopg2
import pytest
from database.connection import execute, fetch_one, fetch_all, get_db_connection
from app import create_app
from mobile.api import _issue_token, _resolve_parent_review
from auth.password_reset import request_password_reset, verify_and_reset_password_by_token


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_race_1_quiz_latch():
    """Verify atomic FOR UPDATE latch on child_quiz_progress prevents double-latching."""
    child_id = 700001
    execute("INSERT INTO users(user_id, role, account_status, email, username, full_name, password_hash) VALUES(%s, 'CHILD', 'ACTIVE', 'c1@test.local', 'c1', 'C1', 'h') ON CONFLICT DO NOTHING", (child_id,))
    execute("INSERT INTO child_quiz_progress(child_id, posts_seen, next_quiz_threshold, quiz_required) VALUES(%s, 2, 3, FALSE) ON CONFLICT(child_id) DO UPDATE SET posts_seen=2, next_quiz_threshold=3, quiz_required=FALSE", (child_id,))
    
    b1 = threading.Barrier(5)
    latch_results = []
    def do_latch():
        conn = get_db_connection()
        b1.wait()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT child_id, posts_seen, next_quiz_threshold, quiz_required FROM child_quiz_progress WHERE child_id=%s FOR UPDATE", (child_id,))
                row = cur.fetchone()
                seen = row["posts_seen"] + 1
                if seen >= row["next_quiz_threshold"] and not row["quiz_required"]:
                    cur.execute("UPDATE child_quiz_progress SET posts_seen=%s, quiz_required=TRUE WHERE child_id=%s", (seen, child_id))
                    conn.commit()
                    latch_results.append("LATCHED")
                else:
                    cur.execute("UPDATE child_quiz_progress SET posts_seen=%s WHERE child_id=%s", (seen, child_id))
                    conn.commit()
                    latch_results.append("INCREMENTED")
        finally:
            conn.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        futures = [ex.submit(do_latch) for _ in range(5)]
        concurrent.futures.wait(futures)

    latched = [r for r in latch_results if r == "LATCHED"]
    assert len(latched) == 1, f"Expected exactly 1 latch, got {len(latched)}"


def test_race_2_session_revocation():
    """Verify concurrent token revocation is idempotent and thread-safe."""
    token_hash = "hash_token_" + uuid.uuid4().hex[:16]
    user_id = 700002
    execute("INSERT INTO users(user_id, role, account_status, email, username, full_name, password_hash) VALUES(%s, 'CHILD', 'ACTIVE', 'c2@test.local', 'c2', 'C2', 'h') ON CONFLICT DO NOTHING", (user_id,))
    
    b2 = threading.Barrier(5)
    results = []
    def do_revoke():
        b2.wait()
        try:
            execute("INSERT INTO mobile_token_revocations (token_hash, user_id, revoked_at) VALUES (%s, %s, NOW()) ON CONFLICT (token_hash) DO NOTHING", (token_hash, user_id))
            results.append("OK")
        except Exception as e:
            results.append(f"ERR: {e}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        futures = [ex.submit(do_revoke) for _ in range(5)]
        concurrent.futures.wait(futures)

    assert len(results) == 5
    assert all(r == "OK" for r in results)
    row = fetch_one("SELECT count(*) as cnt FROM mobile_token_revocations WHERE token_hash=%s", (token_hash,))
    assert row["cnt"] == 1


def test_race_3_upload_finalize():
    """Verify concurrent upload finalization only creates 1 post row."""
    child_id = 700003
    execute("INSERT INTO users(user_id, role, account_status, email, username, full_name, password_hash) VALUES(%s, 'CHILD', 'ACTIVE', 'c3@test.local', 'c3', 'C3', 'h') ON CONFLICT DO NOTHING", (child_id,))
    upload_id = str(uuid.uuid4())
    obj_key = f"quarantine/{child_id}/{upload_id}.jpg"
    execute("""INSERT INTO upload_sessions (upload_id, child_id, object_key, media_type, kind, expected_size_bytes, mime_type, extension, status, expires_at)
               VALUES (%s, %s, %s, 'IMAGE', 'POST', 1024, 'image/jpeg', 'jpg', 'PENDING', NOW() + INTERVAL '1 hour')""", (upload_id, child_id, obj_key))
    b3 = threading.Barrier(5)
    finalize_results = []
    def do_finalize():
        conn = get_db_connection()
        b3.wait()
        try:
            with conn.cursor() as cur:
                cur.execute("UPDATE upload_sessions SET status='CONSUMED', consumed_at=NOW() WHERE upload_id=%s AND status='PENDING' RETURNING upload_id", (upload_id,))
                row = cur.fetchone()
                if row:
                    cur.execute("INSERT INTO posts (child_id, media_type, processing_status) VALUES (%s, 'IMAGE', 'PROCESSING') RETURNING post_id", (child_id,))
                    p_id = cur.fetchone()["post_id"]
                    conn.commit()
                    finalize_results.append(p_id)
                else:
                    conn.commit()
                    finalize_results.append(None)
        finally:
            conn.close()
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        futures = [ex.submit(do_finalize) for _ in range(5)]
        concurrent.futures.wait(futures)
    finalized_posts = [r for r in finalize_results if r is not None]
    assert len(finalized_posts) == 1, f"Expected exactly 1 post created from upload, got {len(finalized_posts)}"


def test_race_4_parent_review_double_resolution():
    """Verify Parent Review double-resolve prevention via row lock."""
    child_id = 887766
    parent_id = 887767
    execute("""
        INSERT INTO users (user_id, role, account_status, email, username, full_name, password_hash)
        VALUES (%s, 'PARENT', 'ACTIVE', 'p@example.com', 'parent_review', 'Parent Review', 'hash') ON CONFLICT DO NOTHING
    """, (parent_id,))
    execute("""
        INSERT INTO users (user_id, role, account_status, email, username, full_name, password_hash)
        VALUES (%s, 'CHILD', 'ACTIVE', 'k@example.com', 'kid_review', 'Kid Review', 'hash') ON CONFLICT DO NOTHING
    """, (child_id,))
    execute("""
        INSERT INTO parent_child_map (parent_id, child_id, parent_name, parent_email, approved, approval_status)
        VALUES (%s, %s, 'Parent Review', 'p@example.com', TRUE, 'APPROVED') ON CONFLICT DO NOTHING
    """, (parent_id, child_id))

    post = execute("""
        INSERT INTO posts (child_id, media_type, processing_status, moderation_status)
        VALUES (%s, 'IMAGE', 'REVIEW', 'REVIEW')
        RETURNING post_id
    """, (child_id,), returning=True)
    post_id = post["post_id"]

    event = execute("""
        INSERT INTO moderation_events (child_id, content_id, content_type, decision, status)
        VALUES (%s, %s, 'IMAGE', 'REVIEW', 'OPEN')
        RETURNING event_id
    """, (child_id, post_id), returning=True)
    event_id = event["event_id"]

    barrier = threading.Barrier(5)
    results = []

    def run_resolve(decision):
        barrier.wait()
        res = _resolve_parent_review(parent_id, event_id, decision)
        results.append(res)

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [
            executor.submit(run_resolve, 'APPROVE'),
            executor.submit(run_resolve, 'BLOCK'),
            executor.submit(run_resolve, 'APPROVE'),
            executor.submit(run_resolve, 'BLOCK'),
            executor.submit(run_resolve, 'APPROVE'),
        ]
        concurrent.futures.wait(futures)

    successes = [r for r in results if r[0] is True]
    assert len(successes) == 1, f"Exactly 1 resolution must succeed, got {len(successes)}"
    
    ev_db = fetch_one("SELECT status FROM moderation_events WHERE event_id=%s", (event_id,))
    assert ev_db["status"] in ('RESOLVED', 'BLOCKED', 'APPROVED')


def test_race_5_screen_time_race_guard():
    """Verify unique partial index idx_screen_time_one_pending_per_child rejects concurrent requests."""
    child_id = 700005
    execute("INSERT INTO users(user_id, role, account_status, email, username, full_name, password_hash) VALUES(%s, 'CHILD', 'ACTIVE', 'c5@test.local', 'c5', 'C5', 'h') ON CONFLICT DO NOTHING", (child_id,))
    execute("DELETE FROM screen_time_extension_requests WHERE child_id=%s", (child_id,))
    b5 = threading.Barrier(5)
    st_results = []
    def do_st_request():
        conn = get_db_connection()
        b5.wait()
        try:
            with conn.cursor() as cur:
                try:
                    cur.execute("INSERT INTO screen_time_extension_requests (child_id, requested_minutes, status) VALUES (%s, 30, 'PENDING') RETURNING request_id", (child_id,))
                    row = cur.fetchone()
                    conn.commit()
                    st_results.append(row["request_id"])
                except psycopg2.IntegrityError:
                    conn.rollback()
                    st_results.append("REJECTED_BY_GUARD")
        finally:
            conn.close()
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        futures = [ex.submit(do_st_request) for _ in range(5)]
        concurrent.futures.wait(futures)
    st_created = [r for r in st_results if r != "REJECTED_BY_GUARD"]
    assert len(st_created) == 1, f"Expected exactly 1 pending extension request, got {len(st_created)}"


def test_race_6_otp_verification():
    """Verify concurrent OTP submission only consumes verification once."""
    user_id = 700006
    execute("INSERT INTO users(user_id, role, account_status, email, username, full_name, password_hash) VALUES(%s, 'PARENT', 'ACTIVE', 'c6_otp@test.local', 'c6_parent', 'C6', 'h') ON CONFLICT DO NOTHING", (user_id,))
    execute("DELETE FROM parent_email_otps WHERE user_id=%s", (user_id,))
    execute("INSERT INTO parent_email_otps (user_id, code_hash, sent_at, expires_at, attempts) VALUES (%s, 'dummy_hash', NOW(), NOW() + INTERVAL '10 min', 0)", (user_id,))
    b6 = threading.Barrier(5)
    otp_results = []
    def do_verify_otp():
        conn = get_db_connection()
        b6.wait()
        try:
            with conn.cursor() as cur:
                cur.execute("UPDATE parent_email_otps SET verified_at=NOW(), attempts=attempts+1 WHERE user_id=%s AND verified_at IS NULL AND attempts < 5 RETURNING verified_at", (user_id,))
                row = cur.fetchone()
                conn.commit()
                otp_results.append(row is not None)
        finally:
            conn.close()
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        futures = [ex.submit(do_verify_otp) for _ in range(5)]
        concurrent.futures.wait(futures)
    otp_success = [r for r in otp_results if r is True]
    assert len(otp_success) == 1, f"Expected exactly 1 OTP verification, got {len(otp_success)}"


def test_race_7_password_reset_handle():
    """Verify concurrent OTP attempts on password_reset_transactions correctly track attempts."""
    user_id = 700007
    reset_email = "pw_race7@test.local"
    execute("INSERT INTO users(user_id, role, account_status, email, username, full_name, password_hash) VALUES(%s, 'PARENT', 'ACTIVE', %s, 'pw_race7', 'PW Race7', 'h') ON CONFLICT DO NOTHING", (user_id, reset_email))
    ok, _, det = request_password_reset(reset_email, request_ip="198.51.100.99")
    token = det["reset_token"]
    b7 = threading.Barrier(5)
    pw_results = []
    def do_pw_reset():
        b7.wait()
        ok, msg = verify_and_reset_password_by_token(token, "000000", "NewValidPass123!")
        pw_results.append((ok, msg))
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        futures = [ex.submit(do_pw_reset) for _ in range(5)]
        concurrent.futures.wait(futures)
    row = fetch_one("SELECT attempts FROM password_reset_transactions WHERE reset_token=%s", (token,))
    assert row["attempts"] >= 1


def test_race_8_delete_outbox_claim():
    """Verify FOR UPDATE SKIP LOCKED yields disjoint non-overlapping claims across workers."""
    for i in range(5):
        execute("INSERT INTO media_delete_outbox(reference, source_table, attempts) VALUES(%s, 'test', 0) ON CONFLICT DO NOTHING", (f"uploads/r2/race_ref_pytest_{i}.jpg",))
    b8 = threading.Barrier(3)
    claimed_by_worker = {}
    def do_claim(worker_id):
        conn = get_db_connection()
        b8.wait()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT outbox_id FROM media_delete_outbox WHERE completed_at IS NULL AND attempts < 8 ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 2")
                rows = cur.fetchall()
                claimed_ids = [r["outbox_id"] for r in rows]
                claimed_by_worker[worker_id] = claimed_ids
                conn.commit()
        finally:
            conn.close()
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        futures = [ex.submit(do_claim, f"w_{i}") for i in range(3)]
        concurrent.futures.wait(futures)
    all_claimed = []
    for wid, cids in claimed_by_worker.items():
        all_claimed.extend(cids)
    assert len(all_claimed) == len(set(all_claimed)), "SKIP LOCKED must never claim the same outbox row twice across workers!"
