import os
import json
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
import pytest
from io import BytesIO
from unittest.mock import patch, MagicMock
from app import app
from mobile.api import _issue_token, _media_allowed, _resolve_parent_review
import services.media_processor as media_processor
from services import object_storage

@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c

def _parent_headers(user_id=101):
    token = _issue_token({"user_id": user_id, "role": "PARENT", "full_name": "Test Parent"})
    return {"Authorization": f"Bearer {token}"}

def _child_headers(user_id=202):
    token = _issue_token({"user_id": user_id, "role": "CHILD", "full_name": "Test Child"})
    return {"Authorization": f"Bearer {token}"}

# ============================================================================
# 3. V2 UPLOAD STATE MACHINE & IDEMPOTENCY
# ============================================================================

def test_v2_upload_complete_size_and_mime_validation(client):
    headers = _child_headers(202)
    session_data = {
        "upload_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
        "child_id": 202,
        "object_key": "uploads/r2/quarantine/202/pic.jpg",
        "media_type": "IMAGE",
        "kind": "POST",
        "expected_size_bytes": 1000,
        "mime_type": "image/jpeg",
        "status": "PENDING",
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
    }

    # 1. R2 object size mismatch
    with patch("mobile.api.fetch_one") as mock_fetch, \
         patch("services.object_storage.enabled", return_value=True), \
         patch("services.object_storage.head_object", return_value={"content_length": 500, "content_type": "image/jpeg"}), \
         patch("mobile.api.get_db_connection") as mock_conn:

        mock_cur = MagicMock()
        mock_cur.fetchone.side_effect = [
            session_data, # upload session row
            None, # existing post check
        ]
        mock_conn.return_value.cursor.return_value = mock_cur

        mock_fetch.side_effect = [
            {"user_id": 202, "role": "CHILD", "account_status": "ACTIVE", "age": 10, "is_approved": True}, # auth
        ]
        res = client.post(f"/api/mobile/v2/uploads/{session_data['upload_id']}/complete", headers=headers, json={})
        assert res.status_code == 400
        assert res.get_json()["error"] == "media_size_mismatch"

    # 2. R2 MIME type mismatch
    with patch("mobile.api.fetch_one") as mock_fetch, \
         patch("services.object_storage.enabled", return_value=True), \
         patch("services.object_storage.head_object", return_value={"content_length": 1000, "content_type": "text/html"}), \
         patch("mobile.api.get_db_connection") as mock_conn:

        mock_cur = MagicMock()
        mock_cur.fetchone.side_effect = [
            session_data, # upload session row
            None, # existing post check
        ]
        mock_conn.return_value.cursor.return_value = mock_cur

        mock_fetch.side_effect = [
            {"user_id": 202, "role": "CHILD", "account_status": "ACTIVE", "age": 10, "is_approved": True}, # auth
        ]
        res = client.post(f"/api/mobile/v2/uploads/{session_data['upload_id']}/complete", headers=headers, json={})
        assert res.status_code == 400
        assert res.get_json()["error"] == "media_mime_mismatch"

def test_v2_upload_complete_queue_spawn_failure_retryable_503(client):
    headers = _child_headers(202)
    session_data = {
        "upload_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
        "child_id": 202,
        "object_key": "uploads/r2/quarantine/202/pic.jpg",
        "media_type": "IMAGE",
        "kind": "POST",
        "expected_size_bytes": 1000,
        "mime_type": "image/jpeg",
        "status": "PENDING",
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
    }

    with patch("mobile.api.fetch_one") as mock_fetch, \
         patch("services.object_storage.enabled", return_value=True), \
         patch("services.object_storage.head_object", return_value={"content_length": 1000, "content_type": "image/jpeg"}), \
         patch("services.job_queue.enqueue_media_job", side_effect=RuntimeError("Modal queue unreachable")), \
         patch("mobile.api.get_db_connection") as mock_conn:

        mock_cur = MagicMock()
        mock_cur.fetchone.side_effect = [
            session_data, # upload session row
            None, # existing post check (None)
            {"post_id": 501}, # post insert RETURNING post_id
        ]
        mock_conn.return_value.cursor.return_value = mock_cur

        mock_fetch.side_effect = [
            {"user_id": 202, "role": "CHILD", "account_status": "ACTIVE", "age": 10, "is_approved": True}, # auth
        ]
        res = client.post(f"/api/mobile/v2/uploads/{session_data['upload_id']}/complete", headers=headers, json={})
        assert res.status_code == 503
        data = res.get_json()
        assert data["error"] == "job_dispatch_failed"
        assert data["retryable"] is True
        assert data["post_id"] == 501

def test_v2_upload_complete_idempotent_retry(client):
    headers = _child_headers(202)
    session_data = {
        "upload_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
        "child_id": 202,
        "object_key": "uploads/r2/quarantine/202/pic.jpg",
        "media_type": "IMAGE",
        "kind": "POST",
        "expected_size_bytes": 1000,
        "mime_type": "image/jpeg",
        "status": "CONSUMED",
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
    }

    with patch("mobile.api.fetch_one") as mock_fetch, \
         patch("services.object_storage.enabled", return_value=True), \
         patch("services.object_storage.head_object", return_value={"content_length": 1000, "content_type": "image/jpeg"}), \
         patch("mobile.api.get_db_connection") as mock_conn:

        mock_cur = MagicMock()
        mock_cur.fetchone.side_effect = [
            session_data,
            {"post_id": 501, "source_media_path": "uploads/r2/quarantine/202/pic.jpg", "processing_status": "PROCESSING", "processing_error": None},
        ]
        mock_conn.return_value.cursor.return_value = mock_cur

        mock_fetch.side_effect = [
            {"user_id": 202, "role": "CHILD", "account_status": "ACTIVE", "age": 10, "is_approved": True}, # auth
        ]
        res = client.post(f"/api/mobile/v2/uploads/{session_data['upload_id']}/complete", headers=headers, json={})
        assert res.status_code == 200
        data = res.get_json()
        assert data["ok"] is True
        assert data["post_id"] == 501
        assert data["status"] == "PROCESSING"
        assert data["idempotent"] is True

# ============================================================================
# 4. REVIEW LIFECYCLE & SANITIZATION FAIL-CLOSED
# ============================================================================

def test_media_allowed_blocks_quarantine_from_unauthorized_users():
    quarantine_ref = "uploads/r2/quarantine/202/pic.jpg"

    with patch("mobile.api.fetch_one") as mock_fetch:
        # 1. Post is in REVIEW / source_media_path is quarantine
        post_review = {
            "post_id": 501,
            "child_id": 202,
            "moderation_status": "REVIEW",
            "is_safe": False,
            "source_media_path": quarantine_ref,
            "media_path": quarantine_ref,
            "poster_path": None,
        }
        mock_fetch.return_value = post_review

        # Child viewer -> always blocked
        assert _media_allowed(303, "CHILD", quarantine_ref) is False

        # Parent who does NOT own child -> blocked
        with patch("mobile.api.owns", return_value=False):
            assert _media_allowed(102, "PARENT", quarantine_ref) is False

        # Parent who DOES own child -> allowed to preview
        with patch("mobile.api.owns", return_value=True):
            assert _media_allowed(101, "PARENT", quarantine_ref) is True

        # Admin -> allowed
        assert _media_allowed(999, "ADMIN", quarantine_ref) is True

    # 2. Post is BLOCKED -> strictly blocked for everyone
    with patch("mobile.api.fetch_one") as mock_fetch:
        mock_fetch.return_value = {
            "post_id": 502,
            "child_id": 202,
            "moderation_status": "BLOCKED",
            "is_safe": False,
            "source_media_path": quarantine_ref,
            "media_path": quarantine_ref,
            "poster_path": None,
        }
        assert _media_allowed(202, "CHILD", quarantine_ref) is False
        assert _media_allowed(101, "PARENT", quarantine_ref) is False
        assert _media_allowed(999, "ADMIN", quarantine_ref) is False

def test_sanitize_and_promote_media_fail_closed_on_corrupt_bytes():
    with patch("services.object_storage.download_file", side_effect=RuntimeError("Corrupt object data")):
        with pytest.raises(RuntimeError):
            media_processor.sanitize_and_promote_media(501, 202, "uploads/r2/quarantine/202/pic.jpg", "post", "IMAGE")

def test_resolve_parent_review_approval_promotes_media(client):
    headers = _parent_headers(101)
    event_id = 77
    post_id = 501

    with patch("mobile.api.get_db_connection") as mock_conn, \
         patch("mobile.api.owns", return_value=True), \
         patch("services.media_processor.sanitize_and_promote_media", return_value=("uploads/r2/published/202/clean.jpg", "uploads/r2/posters/202/clean.jpg")), \
         patch("services.media_processor._notify_approved_followers"), \
         patch("mobile.api.fetch_one", return_value={"user_id": 101, "role": "PARENT", "account_status": "ACTIVE"}):

        mock_cur = MagicMock()
        mock_cur.fetchone.side_effect = [
            {"event_id": event_id, "child_id": 202, "content_type": "IMAGE", "content_id": post_id, "decision": "REVIEW", "status": "OPEN"},
            {"post_id": post_id, "child_id": 202, "source_media_path": "uploads/r2/quarantine/202/pic.jpg", "media_type": "IMAGE"},
        ]
        mock_conn.return_value.cursor.return_value = mock_cur

        res = client.post(f"/api/mobile/v1/parent/safety/{event_id}", headers=headers, json={"action": "APPROVE"})
        assert res.status_code == 200
        assert res.get_json()["ok"] is True
        assert res.get_json()["result"] == "APPROVE"

def test_resolve_parent_review_sanitization_failure_fails_closed_to_blocked(client):
    headers = _parent_headers(101)
    event_id = 77
    post_id = 501

    with patch("mobile.api.get_db_connection") as mock_conn, \
         patch("mobile.api.owns", return_value=True), \
         patch("services.media_processor.sanitize_and_promote_media", side_effect=RuntimeError("FFmpeg transcode failed")), \
         patch("mobile.api.fetch_one", return_value={"user_id": 101, "role": "PARENT", "account_status": "ACTIVE"}):

        mock_cur = MagicMock()
        mock_cur.fetchone.side_effect = [
            {"event_id": event_id, "child_id": 202, "content_type": "IMAGE", "content_id": post_id, "decision": "REVIEW", "status": "OPEN"},
            {"post_id": post_id, "child_id": 202, "source_media_path": "uploads/r2/quarantine/202/pic.jpg", "media_type": "IMAGE"},
        ]
        mock_conn.return_value.cursor.return_value = mock_cur

        res = client.post(f"/api/mobile/v1/parent/safety/{event_id}", headers=headers, json={"action": "APPROVE"})
        assert res.status_code == 400
        assert res.get_json()["ok"] is False
        assert res.get_json()["result"] == "sanitization_failed"

def test_resolve_parent_review_block_deletes_quarantine(client):
    headers = _parent_headers(101)
    event_id = 77
    post_id = 501

    with patch("mobile.api.get_db_connection") as mock_conn, \
         patch("mobile.api.owns", return_value=True), \
         patch("services.media_processor.block_and_cleanup_quarantine") as mock_cleanup, \
         patch("mobile.api.fetch_one", return_value={"user_id": 101, "role": "PARENT", "account_status": "ACTIVE"}):

        mock_cur = MagicMock()
        mock_cur.fetchone.side_effect = [
            {"event_id": event_id, "child_id": 202, "content_type": "IMAGE", "content_id": post_id, "decision": "REVIEW", "status": "OPEN"},
            {"post_id": post_id, "child_id": 202, "source_media_path": "uploads/r2/quarantine/202/pic.jpg", "media_type": "IMAGE"},
        ]
        mock_conn.return_value.cursor.return_value = mock_cur

        res = client.post(f"/api/mobile/v1/parent/safety/{event_id}", headers=headers, json={"action": "BLOCK"})
        assert res.status_code == 200
        assert res.get_json()["ok"] is True
        assert res.get_json()["result"] == "BLOCK"
        mock_cleanup.assert_called_once_with(post_id, "uploads/r2/quarantine/202/pic.jpg")

