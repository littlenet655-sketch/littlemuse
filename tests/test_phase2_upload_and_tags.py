"""Comprehensive test suite for Phase 2: Direct Upload, Manual Hashtags, and Background Processing."""
import json
import uuid
from pathlib import Path
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from app import create_app
from database.connection import execute, fetch_one, fetch_all
from mobile.api import _issue_token
from services.tag_service import validate_and_normalize_tags, save_post_tags, get_post_tags
from services.job_queue import LocalJobQueue, enqueue_media_job
from services.media_processor import process_media_job


@pytest.fixture
def app():
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def test_hashtag_validation_rules():
    # Empty / None
    tags, err = validate_and_normalize_tags(None)
    assert tags == [] and err is None

    # Normalization & strip leading #
    tags, err = validate_and_normalize_tags(["#Science", "space", "Drawing_101"])
    assert err is None
    assert tags == [("Science", "science"), ("space", "space"), ("Drawing_101", "drawing_101")]

    # Rejection of duplicates
    tags, err = validate_and_normalize_tags(["#Fun", "fun"])
    assert err == "duplicate_hashtag_fun"

    # Rejection of > 10 tags
    tags, err = validate_and_normalize_tags([f"tag_{i}" for i in range(11)])
    assert err == "max_10_hashtags_allowed"

    # Rejection of special characters
    tags, err = validate_and_normalize_tags(["hello@world"])
    assert err == "invalid_hashtag_characters"

    # Rejection of too long
    tags, err = validate_and_normalize_tags(["a" * 31])
    assert err == "hashtag_too_long"

    # Rejection of phone numbers in tags
    tags, err = validate_and_normalize_tags(["9876543210"])
    assert err == "hashtag_contains_phone_number"


def test_hashtag_pii_rejection():
    # Email pattern or PII
    tags, err = validate_and_normalize_tags(["callme_9876543210"])
    assert err == "hashtag_contains_phone_number"


def _setup_child_and_parent(child_id: int, username: str):
    execute(
        """INSERT INTO users(user_id, username, full_name, email, password_hash, role, age, dob, account_status)
           VALUES(990, 'testparent', 'Test Parent', 'parent990@test.com', 'scrypt:test', 'PARENT', NULL, NULL, 'ACTIVE')
           ON CONFLICT DO NOTHING"""
    )
    execute(
        """INSERT INTO users(user_id, username, full_name, email, password_hash, role, age, dob, account_status)
           VALUES(%s, %s, %s, %s, 'scrypt:test', 'CHILD', 10, '2014-01-01', 'ACTIVE')
           ON CONFLICT DO NOTHING""",
        (child_id, username, f"{username} Name", f"{username}@test.com"),
    )
    execute(
        """INSERT INTO parent_child_map(parent_id, child_id, parent_name, parent_email, approved)
           VALUES(990, %s, 'Test Parent', 'parent990@test.com', TRUE)
           ON CONFLICT DO NOTHING""",
        (child_id,),
    )
    execute(
        """INSERT INTO child_profiles(child_id, parent_id, full_name, age)
           VALUES(%s, 990, %s, 10)
           ON CONFLICT (child_id) DO UPDATE SET
             parent_id=EXCLUDED.parent_id,
             full_name=EXCLUDED.full_name,
             age=EXCLUDED.age""",
        (child_id, f"{username} Name"),
    )
    execute(
        """INSERT INTO parent_safety_settings(child_id, parent_id, safety_level)
           VALUES(%s, 990, 'STRICT')
           ON CONFLICT (child_id) DO UPDATE SET safety_level='STRICT'""",
        (child_id,),
    )
    execute(
        """INSERT INTO parent_control_settings(child_id, parent_id, allow_posting, allow_reels)
           VALUES(%s, 990, TRUE, TRUE)
           ON CONFLICT (child_id) DO UPDATE SET allow_posting=TRUE, allow_reels=TRUE""",
        (child_id,),
    )
    execute(
        """INSERT INTO child_quiz_progress(child_id, quiz_required)
           VALUES(%s, FALSE) ON CONFLICT DO NOTHING""",
        (child_id,),
    )


def test_hashtag_db_persistence_and_retrieval(app):
    with app.app_context():
        _setup_child_and_parent(991, "tagkid")
        post = execute(
            """INSERT INTO posts(child_id, media_type, caption, is_safe, moderation_status, processing_status)
               VALUES(991, 'IMAGE', 'Testing tags', TRUE, 'ALLOWED', 'ALLOWED') RETURNING post_id""",
            returning=True,
        )
        post_id = post["post_id"]

        tags, err = validate_and_normalize_tags(["#Art", "Painting", "Drawing"])
        assert err is None
        save_post_tags(post_id, tags)

        retrieved = get_post_tags(post_id)
        assert retrieved == ["Art", "Painting", "Drawing"]


def test_upload_session_creation(client, app):
    with app.app_context():
        _setup_child_and_parent(992, "uploadkid")

    token = _issue_token({"user_id": 992, "role": "CHILD"})
    headers = {"Authorization": f"Bearer {token}"}

    # Test size exceeded
    resp = client.post(
        "/api/mobile/v2/uploads/session",
        headers=headers,
        json={
            "kind": "post",
            "media_type": "IMAGE",
            "size_bytes": 25 * 1024 * 1024, # > 20MB limit for image
            "extension": "jpg",
            "mime_type": "image/jpeg",
        },
    )
    assert resp.status_code == 400
    assert resp.json["error"] == "file_size_exceeded"

    # Test invalid extension
    resp = client.post(
        "/api/mobile/v2/uploads/session",
        headers=headers,
        json={
            "kind": "post",
            "media_type": "IMAGE",
            "size_bytes": 1024,
            "extension": "exe",
            "mime_type": "application/x-msdownload",
        },
    )
    assert resp.status_code == 400
    assert resp.json["error"] == "unsupported_extension"

    # Successful image upload session
    resp = client.post(
        "/api/mobile/v2/uploads/session",
        headers=headers,
        json={
            "kind": "post",
            "media_type": "IMAGE",
            "size_bytes": 1024 * 500,
            "extension": "jpg",
            "mime_type": "image/jpeg",
        },
    )
    assert resp.status_code == 200
    data = resp.json
    assert data["ok"] is True
    assert "upload_id" in data
    assert "upload_url" in data
    assert f"uploads/r2/quarantine/992/{data['upload_id']}/source.jpg" == data["object_key"]

    upload_id = data["upload_id"]

    # Verify session recorded in DB
    session_row = fetch_one("SELECT * FROM upload_sessions WHERE upload_id=%s", (upload_id,))
    assert session_row is not None
    assert session_row["child_id"] == 992
    assert session_row["status"] == "PENDING"


def test_upload_complete_and_ownership_security(client, app):
    with app.app_context():
        # Upload completion is a gated child action. Provision both children
        # through the shared test helper so face enrollment, quiz state and
        # parent controls match a real eligible child.
        _setup_child_and_parent(993, "kid_a")
        _setup_child_and_parent(994, "kid_b")

        # Create session belonging to kid_a (993)
        u_id = str(uuid.uuid4())
        obj_key = f"uploads/r2/quarantine/993/{u_id}/source.mp4"
        execute(
            """INSERT INTO upload_sessions(upload_id, child_id, object_key, media_type, kind, expected_size_bytes, mime_type, extension, status, expires_at)
               VALUES(%s, 993, %s, 'VIDEO', 'REEL', 50000, 'video/mp4', 'mp4', 'PENDING', NOW() + INTERVAL '10 minutes')""",
            (u_id, obj_key),
        )

    # kid_b tries to finalize kid_a's upload -> 403
    token_b = _issue_token({"user_id": 994, "role": "CHILD"})
    resp = client.post(
        f"/api/mobile/v2/uploads/{u_id}/complete",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"caption": "Kid B claiming Kid A's upload"},
    )
    assert resp.status_code == 403
    assert resp.json["error"] == "forbidden_upload_owner_mismatch"

    # kid_a finalizes successfully
    token_a = _issue_token({"user_id": 993, "role": "CHILD"})
    with patch("services.job_queue.enqueue_media_job") as mock_enqueue:
        mock_enqueue.return_value = "job_123"
        resp = client.post(
            f"/api/mobile/v2/uploads/{u_id}/complete",
            headers={"Authorization": f"Bearer {token_a}"},
            json={
                "caption": "My awesome reel #Coding",
                "content_category": "Coding",
                "tags": ["Coding", "Tech"],
            },
        )
        assert resp.status_code == 200
        assert resp.json["ok"] is True
        assert resp.json["status"] == "PROCESSING"
        post_id = resp.json["post_id"]
        assert mock_enqueue.called

    # Check post in DB
    post = fetch_one("SELECT * FROM posts WHERE post_id=%s", (post_id,))
    assert post["processing_status"] == "PROCESSING"
    assert post["is_safe"] is False
    assert post["moderation_status"] == "PENDING"
    assert post["source_media_path"] == obj_key

    # Idempotency: second call returns same post
    resp_repeat = client.post(
        f"/api/mobile/v2/uploads/{u_id}/complete",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"caption": "My awesome reel"},
    )
    assert resp_repeat.status_code == 200
    assert resp_repeat.json["post_id"] == post_id
    assert resp_repeat.json["idempotent"] is True


def test_upload_complete_dispatch_failure_marks_uploaded_and_retryable(client, app):
    with app.app_context():
        _setup_child_and_parent(996, "kid_dispatch_err")
        u_id = str(uuid.uuid4())
        obj_key = f"uploads/r2/quarantine/996/{u_id}/source.mp4"
        execute(
            """INSERT INTO upload_sessions(upload_id, child_id, object_key, media_type, kind, expected_size_bytes, mime_type, extension, status, expires_at)
               VALUES(%s, 996, %s, 'VIDEO', 'REEL', 50000, 'video/mp4', 'mp4', 'PENDING', NOW() + INTERVAL '10 minutes')""",
            (u_id, obj_key),
        )

    token = _issue_token({"user_id": 996, "role": "CHILD"})
    with patch("services.job_queue.enqueue_media_job", side_effect=RuntimeError("Modal worker connection timeout")):
        resp = client.post(
            f"/api/mobile/v2/uploads/{u_id}/complete",
            headers={"Authorization": f"Bearer {token}"},
            json={"caption": "Dispatch test reel"},
        )
        assert resp.status_code == 503
        assert resp.json["ok"] is False
        assert resp.json["error"] == "job_dispatch_failed"
        assert resp.json["retryable"] is True
        post_id = resp.json["post_id"]

    # Verify post in DB is UPLOADED with dispatch_failed error
    post = fetch_one("SELECT * FROM posts WHERE post_id=%s", (post_id,))
    assert post["processing_status"] == "UPLOADED"
    assert "dispatch_failed" in (post["processing_error"] or "")

    # Now retry complete call with enqueue_media_job succeeding
    with patch("services.job_queue.enqueue_media_job", return_value="job_retry_996"):
        resp_retry = client.post(
            f"/api/mobile/v2/uploads/{u_id}/complete",
            headers={"Authorization": f"Bearer {token}"},
            json={"caption": "Dispatch test reel"},
        )
        assert resp_retry.status_code == 200
        assert resp_retry.json["ok"] is True
        assert resp_retry.json["status"] == "PROCESSING"
        assert resp_retry.json.get("retry_dispatched") is True

    # Verify post is now PROCESSING
    post_after = fetch_one("SELECT * FROM posts WHERE post_id=%s", (post_id,))
    assert post_after["processing_status"] == "PROCESSING"


def test_quarantine_not_feed_visible(app):
    from services.social import visible_posts

    with app.app_context():
        _setup_child_and_parent(995, "feedkid")

        # Insert a post in quarantine / processing
        quarantine_key = f"uploads/r2/quarantine/995/{uuid.uuid4().hex}/source.mp4"
        post = execute(
            """INSERT INTO posts(child_id, media_type, source_media_path, caption, is_safe, moderation_status, processing_status, content_category, is_story, is_reel)
               VALUES(995, 'VIDEO', %s, 'Secret quarantine', FALSE, 'PENDING', 'PROCESSING', 'Other', FALSE, FALSE)
               RETURNING post_id""",
            (quarantine_key,),
            returning=True,
        )
        pid = post["post_id"]

        # Check visible_posts for feedkid
        posts = visible_posts(995)
        pids = [p["post_id"] for p in posts]
        assert pid not in pids, "Quarantine pending post must never appear in child feed"


def test_media_processor_allow_review_block(app):
    with app.app_context():
        _setup_child_and_parent(996, "prockid")

        u1 = uuid.uuid4().hex
        u2 = uuid.uuid4().hex
        allow_key = f"uploads/r2/quarantine/996/{u1}/source.jpg"
        block_key = f"uploads/r2/quarantine/996/{u2}/source.jpg"

        import io
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (10, 10), color="blue").save(buf, format="JPEG")
        valid_jpg_bytes = buf.getvalue()

        allow_file = Path(allow_key)
        allow_file.parent.mkdir(parents=True, exist_ok=True)
        allow_file.write_bytes(valid_jpg_bytes)

        block_file = Path(block_key)
        block_file.parent.mkdir(parents=True, exist_ok=True)
        block_file.write_bytes(valid_jpg_bytes)

        try:
            # Case 1: ALLOW
            post_allow = execute(
                """INSERT INTO posts(child_id, media_type, source_media_path, caption, is_safe, moderation_status, processing_status, content_category)
                   VALUES(996, 'IMAGE', %s, 'Nice science drawing', FALSE, 'PENDING', 'UPLOADED', 'Science')
                   RETURNING post_id""",
                (allow_key,),
                returning=True,
            )
            pid_allow = post_allow["post_id"]

            with patch("services.media_processor.evaluate") as mock_eval:
                mock_eval.return_value = ({"adult_score": 0.01, "violence_score": 0.0, "risk_score": 5.0}, None)
                res = process_media_job(pid_allow, 996, allow_key, "post")
                assert res["status"] == "ALLOWED"

                updated = fetch_one("SELECT * FROM posts WHERE post_id=%s", (pid_allow,))
                assert updated["is_safe"] is True
                assert updated["moderation_status"] == "ALLOWED"
                assert updated["processing_status"] == "ALLOWED"

            # Case 2: BLOCK
            post_block = execute(
                """INSERT INTO posts(child_id, media_type, source_media_path, caption, is_safe, moderation_status, processing_status, content_category)
                   VALUES(996, 'IMAGE', %s, 'Bad content', FALSE, 'PENDING', 'UPLOADED', 'Other')
                   RETURNING post_id""",
                (block_key,),
                returning=True,
            )
            pid_block = post_block["post_id"]

            with patch("services.media_processor.evaluate") as mock_eval:
                mock_eval.return_value = ({"adult_score": 0.95, "violence_score": 0.0, "risk_score": 95.0}, None)
                res = process_media_job(pid_block, 996, block_key, "post")
                assert res["status"] == "BLOCKED"

                updated = fetch_one("SELECT * FROM posts WHERE post_id=%s", (pid_block,))
                assert updated["is_safe"] is False
                assert updated["moderation_status"] == "BLOCKED"
                assert updated["processing_status"] == "BLOCKED"
        finally:
            if allow_file.exists():
                allow_file.unlink()
            if block_file.exists():
                block_file.unlink()


def test_processing_status_endpoint(client, app):
    with app.app_context():
        _setup_child_and_parent(997, "statuskid")
        post = execute(
            """INSERT INTO posts(child_id, media_type, caption, is_safe, moderation_status, processing_status)
               VALUES(997, 'IMAGE', 'Testing status', TRUE, 'ALLOWED', 'ALLOWED') RETURNING post_id""",
            returning=True,
        )
        pid = post["post_id"]

    token = _issue_token({"user_id": 997, "role": "CHILD"})
    resp = client.get(f"/api/mobile/v2/posts/{pid}/processing-status", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json["ok"] is True
    assert resp.json["status"] == "ALLOWED"
    assert resp.json["stage"] == "ALLOWED"
