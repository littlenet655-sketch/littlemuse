import concurrent.futures
import threading
import uuid
import pytest
from database.connection import execute, fetch_one
from app import create_app
from mobile.api import _issue_token, _resolve_parent_review


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_race_parent_review_double_terminal_resolution():
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
        battler = _thread_resolve(barrier, parent_id, event_id, decision)
        results.append(battler)


    def _thread_resolve(barrier, pid, eid, dec):
        barrier.wait()
        return _resolve_parent_review(pid, eid, dec)

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
    assert len(successes) == 1, f'Exactly 1 resolution must succeed, got {len(successes)}'
    
    ev_db = fetch_one("SELECT status FROM moderation_events WHERE event_id=%s", (event_id,))
    assert ev_db["status"] in ('RESOLVED', 'BLOCKED', 'APPROVED')
