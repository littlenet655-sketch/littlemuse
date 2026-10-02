"""Concurrency and race condition tests for LittleNet media upload completion."""
import concurrent.futures
import uuid
from unittest.mock import patch

import pytest
from app import create_app
from database.connection import execute, fetch_all, fetch_one
from mobile.api import _issue_token


@pytest.fixture
def app():
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def test_concurrent_upload_complete_never_duplicates_posts(client, app):
    """Prove that concurrent completion requests for the exact same upload_session
    never create duplicate posts, and all threads receive the exact same post_id."""
    with app.app_context():
        execute(
            """INSERT INTO users(user_id, username, full_name, email, password_hash, role, age, dob, account_status)
               VALUES(9988, 'kid_concurrency', 'Kid Concurrent', 'concurrent@test.com', 'scrypt:test', 'CHILD', 10, '2014-01-01', 'ACTIVE')
               ON CONFLICT (user_id) DO NOTHING"""
        )
        u_id = str(uuid.uuid4())
        obj_key = f"uploads/r2/quarantine/9988/{u_id}/source.mp4"
        execute(
            """INSERT INTO upload_sessions(upload_id, child_id, object_key, media_type, kind, expected_size_bytes, mime_type, extension, status, expires_at)
               VALUES(%s, 9988, %s, 'VIDEO', 'REEL', 50000, 'video/mp4', 'mp4', 'PENDING', NOW() + INTERVAL '10 minutes')
               ON CONFLICT (upload_id) DO NOTHING""",
            (u_id, obj_key),
        )

    token = _issue_token({"user_id": 9988, "role": "CHILD"})

    def make_request(idx: int):
        # We need a new client context per thread
        with app.test_client() as thread_client:
            return thread_client.post(
                f"/api/mobile/v2/uploads/{u_id}/complete",
                headers={"Authorization": f"Bearer {token}"},
                json={"caption": f"Concurrency test attempt #{idx}", "content_category": "Coding"},
            )

    with patch("mobile.api._child_gate", return_value=None), \
         patch("services.object_storage.head_object", return_value={"content_length": 50000, "content_type": "video/mp4"}), \
         patch("services.job_queue.enqueue_media_job", return_value="job_conc_123"):
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_request, i) for i in range(5)]
            responses = [f.result() for f in futures]

    # All responses must be successful 200 OK
    status_codes = [r.status_code for r in responses]
    assert all(code == 200 for code in status_codes), f"Unexpected status codes: {status_codes}"

    # All responses must agree on the exact same post_id
    post_ids = [r.json.get("post_id") for r in responses]
    assert len(set(post_ids)) == 1, f"Concurrent requests returned multiple post IDs: {post_ids}"
    assert post_ids[0] is not None

    # Exactly ONE post must exist in the database with this upload_id / source_media_path
    with app.app_context():
        matching_posts = fetch_all("SELECT post_id, source_media_path FROM posts WHERE upload_id=%s", (u_id,))
        assert len(matching_posts) == 1, f"Expected exactly 1 post, found {len(matching_posts)}"

        session = fetch_one("SELECT status FROM upload_sessions WHERE upload_id=%s", (u_id,))
        assert session["status"] == "CONSUMED"
