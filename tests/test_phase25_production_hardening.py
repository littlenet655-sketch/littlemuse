"""
Phase 2.5 Production-Hardening Test Suite
==========================================
Verifies all security guards added in Phase 2.5:

1. mock-PUT disabled in production (HTTPS base URL or ENABLE_MOCK_PUT not set)
2. mock-PUT allowed only in dev (ENABLE_MOCK_PUT=1 + HTTP base URL)
3. Upload session expiry enforced at /complete
4. Cross-user session theft blocked (403)
5. Malformed / oversized payloads rejected at /session
6. Unsupported extensions / MIME types rejected at /session
7. File-size validation per media_type + kind
8. Idempotent /complete returns same post_id
9. Quarantined posts never appear in child feed
"""

import json
import os
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest

from app import create_app
from database.connection import execute, fetch_one
from mobile.api import _issue_token


# ────────────────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def app():
    a = create_app()
    a.config["TESTING"] = True
    return a


@pytest.fixture(scope="module")
def client(app):
    return app.test_client()


def _ensure_child(child_id: int, username: str) -> None:
    execute(
        """INSERT INTO users(user_id, username, full_name, email, password_hash, role, age, dob, account_status)
           VALUES(9900, 'harden_parent', 'Hardening Parent', 'hardparent@test.com', 'scrypt:x', 'PARENT', NULL, NULL, 'ACTIVE')
           ON CONFLICT DO NOTHING"""
    )
    execute(
        """INSERT INTO users(user_id, username, full_name, email, password_hash, role, age, dob, account_status)
           VALUES(%s, %s, %s, %s, 'scrypt:x', 'CHILD', 10, '2014-01-01', 'ACTIVE')
           ON CONFLICT DO NOTHING""",
        (child_id, username, f"{username} Name", f"{username}@test.com"),
    )
    execute(
        """INSERT INTO parent_child_map(parent_id, child_id, parent_name, parent_email, approved)
           VALUES(9900, %s, 'Hardening Parent', 'hardparent@test.com', TRUE)
           ON CONFLICT DO NOTHING""",
        (child_id,),
    )
    execute(
        """INSERT INTO child_profiles(child_id, parent_id, full_name, age)
           VALUES(%s, 9900, %s, 10)
           ON CONFLICT (child_id) DO UPDATE SET
             parent_id=EXCLUDED.parent_id,
             full_name=EXCLUDED.full_name,
             age=EXCLUDED.age""",
        (child_id, f"{username} Name"),
    )
    execute(
        """INSERT INTO parent_safety_settings(child_id, parent_id, safety_level)
           VALUES(%s, 9900, 'STRICT') ON CONFLICT (child_id) DO UPDATE SET safety_level='STRICT'""",
        (child_id,),
    )
    execute(
        """INSERT INTO parent_control_settings(child_id, parent_id, allow_posting, allow_reels)
           VALUES(%s, 9900, TRUE, TRUE) ON CONFLICT (child_id) DO UPDATE SET allow_posting=TRUE, allow_reels=TRUE""",
        (child_id,),
    )
    execute(
        "INSERT INTO child_quiz_progress(child_id, quiz_required) VALUES(%s, FALSE) ON CONFLICT DO NOTHING",
        (child_id,),
    )


def _make_session(child_id: int, status: str = "PENDING", expired: bool = False) -> str:
    u_id = str(uuid.uuid4())
    obj_key = f"uploads/r2/quarantine/{child_id}/{u_id}/source.jpg"
    expires_at = (
        datetime.utcnow() - timedelta(minutes=1)
        if expired
        else datetime.utcnow() + timedelta(minutes=15)
    )
    execute(
        """INSERT INTO upload_sessions(upload_id, child_id, object_key, media_type, kind,
               expected_size_bytes, mime_type, extension, status, expires_at)
           VALUES(%s, %s, %s, 'IMAGE', 'POST', 1024, 'image/jpeg', 'jpg', %s, %s)""",
        (u_id, child_id, obj_key, status, expires_at),
    )
    return u_id


# ────────────────────────────────────────────────────────────────────────────
# 1. mock-PUT production guard
# ────────────────────────────────────────────────────────────────────────────

def test_mock_put_disabled_in_production(client, app):
    """mock-PUT must return 404 when BASE_URL is https:// (production)."""
    with app.app_context():
        _ensure_child(9901, "hkid_01")
        u_id = _make_session(9901)

    with patch("config.Config._PRODUCTION", True), \
         patch.dict(os.environ, {"ENABLE_MOCK_PUT": "0"}):
        resp = client.put(
            f"/api/mobile/v2/uploads/mock-put/{u_id}",
            data=b"fake_bytes",
            content_type="image/jpeg",
        )
    assert resp.status_code == 404
    assert resp.json.get("error") == "not_found"


def test_mock_put_disabled_when_env_not_set(client, app):
    """mock-PUT returns 404 even on HTTP when ENABLE_MOCK_PUT is not '1'."""
    with app.app_context():
        _ensure_child(9902, "hkid_02")
        u_id = _make_session(9902)

    with patch("config.Config._PRODUCTION", False), \
         patch.dict(os.environ, {"ENABLE_MOCK_PUT": "0"}):
        resp = client.put(
            f"/api/mobile/v2/uploads/mock-put/{u_id}",
            data=b"fake_bytes",
            content_type="image/jpeg",
        )
    assert resp.status_code == 404


def test_mock_put_unknown_session_returns_404(client, app):
    """mock-PUT for a non-existent upload_id returns 404 (session_not_found)."""
    nonexistent_uuid = "00000000-0000-0000-0000-000000000999"
    with patch("config.Config._PRODUCTION", False), \
         patch.dict(os.environ, {"ENABLE_MOCK_PUT": "1"}):
        resp = client.put(
            f"/api/mobile/v2/uploads/mock-put/{nonexistent_uuid}",
            data=b"data",
            content_type="image/jpeg",
        )
    assert resp.status_code == 404


# ────────────────────────────────────────────────────────────────────────────
# 2. Upload session creation – edge cases
# ────────────────────────────────────────────────────────────────────────────

def test_session_rejects_oversized_image(client, app):
    """POST /session: image > 20 MB must be rejected."""
    with app.app_context():
        _ensure_child(9904, "hkid_04")
    token = _issue_token({"user_id": 9904, "role": "CHILD"})

    resp = client.post(
        "/api/mobile/v2/uploads/session",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "kind": "post",
            "media_type": "IMAGE",
            "size_bytes": 21 * 1024 * 1024,
            "extension": "jpg",
            "mime_type": "image/jpeg",
        },
    )
    assert resp.status_code == 400
    assert resp.json["error"] == "file_size_exceeded"


def test_session_rejects_bad_extension(client, app):
    """POST /session: non-image/video extension must be rejected."""
    with app.app_context():
        _ensure_child(9905, "hkid_05")
    token = _issue_token({"user_id": 9905, "role": "CHILD"})

    for bad_ext, bad_mime in [
        ("exe", "application/x-msdownload"),
        ("sh", "text/x-sh"),
        ("pdf", "application/pdf"),
    ]:
        resp = client.post(
            "/api/mobile/v2/uploads/session",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "kind": "post",
                "media_type": "IMAGE",
                "size_bytes": 1024,
                "extension": bad_ext,
                "mime_type": bad_mime,
            },
        )
        assert resp.status_code == 400, f"Expected 400 for extension={bad_ext}"
        assert resp.json["error"] in ("unsupported_extension", "unsupported_mime_type")


def test_session_rejects_zero_size(client, app):
    """POST /session: size_bytes = 0 must be rejected."""
    with app.app_context():
        _ensure_child(9906, "hkid_06")
    token = _issue_token({"user_id": 9906, "role": "CHILD"})

    resp = client.post(
        "/api/mobile/v2/uploads/session",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "kind": "post",
            "media_type": "IMAGE",
            "size_bytes": 0,
            "extension": "jpg",
            "mime_type": "image/jpeg",
        },
    )
    assert resp.status_code == 400
    assert resp.json["error"] in ("file_size_required", "file_size_exceeded", "invalid_file_size")


def test_session_success_returns_object_key_structure(client, app):
    """Successful session creation returns object_key in quarantine namespace."""
    with app.app_context():
        _ensure_child(9907, "hkid_07")
    token = _issue_token({"user_id": 9907, "role": "CHILD"})

    resp = client.post(
        "/api/mobile/v2/uploads/session",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "kind": "post",
            "media_type": "IMAGE",
            "size_bytes": 500_000,
            "extension": "jpg",
            "mime_type": "image/jpeg",
        },
    )
    assert resp.status_code == 200
    data = resp.json
    assert data["ok"] is True
    assert data["object_key"].startswith("uploads/r2/quarantine/9907/")
    assert data["object_key"].endswith("/source.jpg")
    assert "upload_id" in data
    assert "upload_url" in data
    assert "expires_at" in data


# ────────────────────────────────────────────────────────────────────────────
# 3. Upload complete – security edge cases
# ────────────────────────────────────────────────────────────────────────────

def test_complete_rejects_expired_session(client, app):
    """POST /complete on an expired session must return 400."""
    with app.app_context():
        _ensure_child(9908, "hkid_08")
        u_id = _make_session(9908, expired=True)

    token = _issue_token({"user_id": 9908, "role": "CHILD"})
    resp = client.post(
        f"/api/mobile/v2/uploads/{u_id}/complete",
        headers={"Authorization": f"Bearer {token}"},
        json={"caption": "Late upload"},
    )
    assert resp.status_code == 400
    assert resp.json.get("error") in ("upload_session_expired", "session_expired")


def test_complete_rejects_cross_user_theft(client, app):
    """Kid B must not finalize Kid A's upload session."""
    with app.app_context():
        _ensure_child(9909, "hkid_09")
        _ensure_child(9910, "hkid_10")
        u_id = _make_session(9909)

    token_b = _issue_token({"user_id": 9910, "role": "CHILD"})
    resp = client.post(
        f"/api/mobile/v2/uploads/{u_id}/complete",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"caption": "Stealing"},
    )
    assert resp.status_code == 403
    assert resp.json["error"] == "forbidden_upload_owner_mismatch"


def test_complete_idempotency(client, app):
    """Calling /complete twice returns the same post_id without creating duplicates."""
    with app.app_context():
        _ensure_child(9911, "hkid_11")
        u_id = _make_session(9911)

    token = _issue_token({"user_id": 9911, "role": "CHILD"})

    with patch("services.job_queue.enqueue_media_job") as mock_q, \
         patch("services.object_storage.head_object", return_value={"content_length": 1024, "content_type": "image/jpeg"}):
        mock_q.return_value = "job_x"
        resp1 = client.post(
            f"/api/mobile/v2/uploads/{u_id}/complete",
            headers={"Authorization": f"Bearer {token}"},
            json={"caption": "First complete"},
        )
    assert resp1.status_code == 200
    post_id = resp1.json["post_id"]

    resp2 = client.post(
        f"/api/mobile/v2/uploads/{u_id}/complete",
        headers={"Authorization": f"Bearer {token}"},
        json={"caption": "Duplicate complete"},
    )
    assert resp2.status_code == 200
    assert resp2.json["post_id"] == post_id
    assert resp2.json.get("idempotent") is True


def test_complete_unknown_session_returns_404(client, app):
    """POST /complete on a nonexistent upload_id must return 404."""
    with app.app_context():
        _ensure_child(9912, "hkid_12")
    token = _issue_token({"user_id": 9912, "role": "CHILD"})
    nonexistent_uuid = "00000000-0000-0000-0000-000000000998"
    resp = client.post(
        f"/api/mobile/v2/uploads/{nonexistent_uuid}/complete",
        headers={"Authorization": f"Bearer {token}"},
        json={"caption": "ghost"},
    )
    assert resp.status_code == 404
    assert "not_found" in resp.json.get("error", "")


# ────────────────────────────────────────────────────────────────────────────
# 4. Quarantine isolation
# ────────────────────────────────────────────────────────────────────────────

def test_quarantined_post_not_in_feed(app):
    """A PROCESSING post must never appear in the child's feed."""
    from services.social import visible_posts

    with app.app_context():
        _ensure_child(9913, "hkid_13")
        q_key = f"uploads/r2/quarantine/9913/{uuid.uuid4().hex}/source.jpg"
        row = execute(
            """INSERT INTO posts(child_id, media_type, source_media_path, caption,
                   is_safe, moderation_status, processing_status, content_category)
               VALUES(9913, 'IMAGE', %s,
                   'Hidden quarantine post', FALSE, 'PENDING', 'PROCESSING', 'Other')
               RETURNING post_id""",
            (q_key,),
            returning=True,
        )
        pid = row["post_id"]
        posts = visible_posts(9913)
        pids = [p["post_id"] for p in posts]
        assert pid not in pids, "PROCESSING post must not appear in child feed"


def test_processing_status_endpoint_correct_stages(client, app):
    """GET /posts/<id>/processing-status returns correct stage for all terminal states."""
    with app.app_context():
        _ensure_child(9914, "hkid_14")

    token = _issue_token({"user_id": 9914, "role": "CHILD"})

    for proc_status in ("ALLOWED", "BLOCKED"):
        with app.app_context():
            row = execute(
                """INSERT INTO posts(child_id, media_type, caption, is_safe, moderation_status, processing_status)
                   VALUES(9914, 'IMAGE', %s, %s, %s, %s) RETURNING post_id""",
                (
                    f"test_{proc_status}",
                    proc_status == "ALLOWED",
                    proc_status,
                    proc_status,
                ),
                returning=True,
            )
            pid = row["post_id"]

        resp = client.get(
            f"/api/mobile/v2/posts/{pid}/processing-status",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, f"Expected 200 for {proc_status}"
        assert resp.json["ok"] is True
        assert resp.json["stage"] == proc_status


# ────────────────────────────────────────────────────────────────────────────
# 5. Unauthenticated access is blocked
# ────────────────────────────────────────────────────────────────────────────

def test_session_endpoint_requires_auth(client):
    resp = client.post(
        "/api/mobile/v2/uploads/session",
        json={"kind": "post", "media_type": "IMAGE", "size_bytes": 1024, "extension": "jpg"},
    )
    assert resp.status_code == 401


def test_complete_endpoint_requires_auth(client):
    resp = client.post(
        "/api/mobile/v2/uploads/some-id/complete",
        json={"caption": "no auth"},
    )
    assert resp.status_code == 401


def test_processing_status_requires_auth(client):
    resp = client.get("/api/mobile/v2/posts/1/processing-status")
    assert resp.status_code == 401


# ────────────────────────────────────────────────────────────────────────────
# 6. Direct upload unavailable & fallback contract
# ────────────────────────────────────────────────────────────────────────────

def test_direct_upload_unavailable_returns_503_with_fallback_in_dev(client, app):
    with app.app_context():
        _ensure_child(9915, "hkid_15")
    token = _issue_token({"user_id": 9915, "role": "CHILD"})

    with patch("config.Config._PRODUCTION", False), \
         patch.dict(os.environ, {"DIRECT_UPLOAD_UNAVAILABLE": "1"}, clear=False):
        resp = client.post(
            "/api/mobile/v2/uploads/session",
            headers={"Authorization": f"Bearer {token}"},
            json={"kind": "post", "media_type": "IMAGE", "size_bytes": 1024, "extension": "jpg"},
        )
        assert resp.status_code == 503
        data = resp.get_json()
        assert data["error"] == "direct_upload_unavailable"
        assert data["fallback_allowed"] is True


def test_direct_upload_unavailable_forbids_fallback_in_prod(client, app):
    with app.app_context():
        _ensure_child(9916, "hkid_16")
    token = _issue_token({"user_id": 9916, "role": "CHILD"})

    with patch("config.Config._PRODUCTION", True), \
         patch.dict(os.environ, {"DIRECT_UPLOAD_UNAVAILABLE": "1"}, clear=False):
        resp = client.post(
            "/api/mobile/v2/uploads/session",
            headers={"Authorization": f"Bearer {token}"},
            json={"kind": "post", "media_type": "IMAGE", "size_bytes": 1024, "extension": "jpg"},
        )
        assert resp.status_code == 503
        data = resp.get_json()
        assert data["error"] == "direct_upload_unavailable"
        assert data["fallback_allowed"] is False

