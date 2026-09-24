from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app import app
from mobile.api import _issue_token
from services.audit import log as audit_log


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


def headers(user_id=101, role="PARENT"):
    token = _issue_token({"user_id": user_id, "role": role, "full_name": f"Test {role.title()}"})
    return {"Authorization": f"Bearer {token}"}


def active_user(user_id=101, role="PARENT"):
    return {
        "user_id": user_id,
        "username": f"test_{role.lower()}",
        "full_name": f"Test {role.title()}",
        "email": f"{role.lower()}@test.invalid",
        "role": role,
        "age": None,
        "account_status": "ACTIVE",
    }


def test_audit_log_serializes_database_datetime_values():
    with patch("services.audit.execute") as execute:
        audit_log(202, "PARENT_CONTROLS_UPDATED", {"quiet_start": datetime(2026, 9, 13, 21, 0)})
    assert '"quiet_start": "2026-09-13 21:00:00"' in execute.call_args.args[1][2]


def test_parent_safety_queue_uses_canonical_approved_ownership(client):
    with patch("mobile.api.fetch_one", return_value=active_user()), patch("mobile.api.fetch_all", return_value=[]) as fetch_all:
        response = client.get("/api/mobile/v1/parent/safety", headers=headers())
    assert response.status_code == 200
    sql, params = fetch_all.call_args.args
    assert "m.approved=TRUE" in sql
    assert "m.approval_status='APPROVED'" in sql
    assert "m.parent_id=%s OR m.verified_parent_id=%s" in sql
    assert params == (101, 101, 101)


def test_parent_review_reports_cross_parent_denial_as_forbidden(client):
    with patch("mobile.api.fetch_one", return_value=active_user()), patch("mobile.api._resolve_parent_review", return_value=(False, "forbidden")):
        response = client.post("/api/mobile/v1/parent/safety/91", headers=headers(), json={"action": "APPROVE"})
    assert response.status_code == 403
    assert response.get_json() == {"ok": False, "result": "forbidden"}


def test_parent_review_queue_returns_authorized_quarantine_url_not_storage_reference(client):
    event = {"event_id": 8, "child_id": 202, "full_name": "Owned Child", "content_type": "IMAGE", "content_id": 44, "decision": "REVIEW", "status": "OPEN"}
    preview = {"media_type": "IMAGE", "media_path": None, "source_media_path": "uploads/r2/quarantine/owned.jpg", "poster_path": None, "caption": "Review me"}
    with patch("mobile.api.fetch_one", side_effect=[active_user(), preview]), \
         patch("mobile.api.fetch_all", return_value=[event]), \
         patch("mobile.api._asset_url", return_value="https://signed.invalid/owned"):
        response = client.get("/api/mobile/v1/parent/safety", headers=headers())
    assert response.status_code == 200
    payload = response.get_json()["events"][0]["preview"]
    assert payload["media_url"] == "https://signed.invalid/owned"
    assert "media_path" not in payload and "source_media_path" not in payload


def test_parent_control_update_is_validated_and_notifies_child(client):
    controls = {
        "allow_reels": False,
        "allow_stories": True,
        "allow_messaging": False,
        "allow_posting": True,
        "allow_discover": True,
        "quiet_hours_enabled": True,
        "quiet_start": "21:00",
        "quiet_end": "07:00",
        "educational_only_feed": True,
        "allowed_categories": ["Science"],
    }
    with patch("mobile.api.fetch_one", side_effect=[active_user(), None, {"quiz_pacing_policy": "FREQUENT"}]), \
         patch("mobile.api.owns", return_value=True), \
         patch("mobile.api.controls_for_child", return_value=controls), \
         patch("mobile.api.save_controls", return_value=controls) as save, \
         patch("mobile.api.log") as log, patch("mobile.api.notify") as notify:
        response = client.put("/api/mobile/v1/parent/controls/202", headers=headers(), json=controls)
    assert response.status_code == 200
    assert save.call_count == 1
    log.assert_called_once()
    notify.assert_called_once()

    with patch("mobile.api.fetch_one", return_value=active_user()), patch("mobile.api.owns", return_value=True):
        invalid = client.put("/api/mobile/v1/parent/controls/202", headers=headers(), json={"allow_reels": "false"})
    assert invalid.status_code == 400
    assert invalid.get_json()["error"] == "invalid_controls"


def test_parent_notification_read_and_activity_ownership(client):
    rows = [{"notification_id": 1, "is_read": True}]
    with patch("mobile.api.fetch_one", return_value=active_user()), patch("mobile.api.execute") as execute, patch("mobile.api.fetch_all", return_value=rows):
        response = client.post("/api/mobile/v1/parent/notifications", headers=headers(), json={})
    assert response.status_code == 200
    assert response.get_json()["notifications"][0]["is_read"] is True
    assert "parent_id=%s" in execute.call_args.args[0]

    with patch("mobile.api.fetch_one", return_value=active_user()), patch("mobile.api.owns", return_value=False), patch("mobile.api.fetch_all") as fetch_all:
        denied = client.get("/api/mobile/v1/parent/activity/999", headers=headers())
    assert denied.status_code == 404
    fetch_all.assert_not_called()


def test_parent_follow_action_requires_an_actionable_owned_row(client):
    with patch("mobile.api.fetch_one", return_value=active_user()), patch("mobile.api.owns", return_value=True), patch("mobile.api.execute_count", return_value=0):
        missing = client.post("/api/mobile/v1/parent/follow-requests/action", headers=headers(), json={"child_id": 202, "target_id": 303, "action": "approve"})
    assert missing.status_code == 404

    with patch("mobile.api.fetch_one", return_value=active_user()), patch("mobile.api.owns", return_value=True), patch("mobile.api.execute_count", return_value=1) as update, patch("mobile.api.log"):
        accepted = client.post("/api/mobile/v1/parent/follow-requests/action", headers=headers(), json={"child_id": 202, "target_id": 303, "action": "approve"})
    assert accepted.status_code == 200
    assert "approval_stage IN ('REQUESTED','RECEIVER_PARENT_PENDING')" in update.call_args.args[0]


def test_admin_routes_reject_parent_role(client):
    with patch("mobile.api.fetch_one", return_value=active_user()):
        response = client.get("/api/mobile/v1/admin/reviews", headers=headers())
    assert response.status_code == 403
    assert response.get_json()["error"] == "role_forbidden"


def test_admin_queue_is_bounded_to_open_review_events(client):
    with patch("mobile.api.fetch_one", return_value=active_user(1, "ADMIN")), patch("mobile.api.fetch_all", return_value=[]) as fetch_all:
        response = client.get("/api/mobile/v1/admin/reviews", headers=headers(1, "ADMIN"))
    assert response.status_code == 200
    sql = fetch_all.call_args.args[0]
    assert "decision='REVIEW'" in sql and "status='OPEN'" in sql and "LIMIT 100" in sql


def test_admin_review_detail_returns_authorized_url_not_storage_reference(client):
    event = {"event_id": 7, "child_id": 202, "content_type": "IMAGE", "content_id": 33, "decision": "REVIEW", "status": "OPEN"}
    preview = {"media_type": "IMAGE", "media_path": None, "source_media_path": "uploads/r2/quarantine/private.jpg", "poster_path": None, "caption": "Review me", "moderation_status": "REVIEW"}
    with patch("mobile.api.fetch_one", return_value=active_user(1, "ADMIN")), \
         patch("mobile.admin_api.fetch_one", side_effect=[event, preview]), \
         patch("mobile.admin_api._asset_url", return_value="https://signed.invalid/review"):
        response = client.get("/api/mobile/v1/admin/reviews/7", headers=headers(1, "ADMIN"))
    assert response.status_code == 200
    payload = response.get_json()["preview"]
    assert payload["media_url"] == "https://signed.invalid/review"
    assert "media_path" not in payload and "source_media_path" not in payload


def test_admin_final_action_uses_authoritative_review_transition(client):
    event = {"event_id": 7, "child_id": 202, "content_type": "IMAGE", "content_id": 33, "decision": "REVIEW", "status": "OPEN"}
    with patch("mobile.api.fetch_one", return_value=active_user(1, "ADMIN")), \
         patch("mobile.admin_api.fetch_one", return_value=event), \
         patch("mobile.admin_api._resolve_parent_review", return_value=(True, "APPROVE")) as resolve:
        response = client.post("/api/mobile/v1/admin/reviews/7", headers=headers(1, "ADMIN"), json={"action": "APPROVE", "notes": "Safe"})
    assert response.status_code == 200
    assert response.get_json()["status"] == "RESOLVED"
    resolve.assert_called_once_with(1, 7, "APPROVE", is_admin=True, notes="Safe")


def test_admin_user_status_is_audited_and_admin_targets_are_protected(client):
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.return_value = {"role": "CHILD", "account_status": "ACTIVE"}
    with patch("mobile.api.fetch_one", return_value=active_user(1, "ADMIN")), patch("mobile.admin_api.get_db_connection", return_value=conn):
        response = client.post("/api/mobile/v1/admin/users/202/status", headers=headers(1, "ADMIN"), json={"status": "SUSPENDED"})
    assert response.status_code == 200
    statements = [call.args[0] for call in cursor.execute.call_args_list]
    assert any("role<>'ADMIN'" in statement for statement in statements)
    assert any("INSERT INTO admin_audit_logs" in statement for statement in statements)
    conn.commit.assert_called_once()


def test_admin_audit_uses_dedicated_safe_log_contract(client):
    with patch("mobile.api.fetch_one", return_value=active_user(1, "ADMIN")), patch("mobile.admin_api.fetch_all", return_value=[]) as fetch_all:
        response = client.get("/api/mobile/v1/admin/audit", headers=headers(1, "ADMIN"))
    assert response.status_code == 200
    sql = fetch_all.call_args.args[0]
    assert "admin_audit_logs" in sql
    assert "activity_logs" not in sql
    assert "LIMIT 100" in sql
