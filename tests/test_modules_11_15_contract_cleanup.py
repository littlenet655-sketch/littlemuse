from io import BytesIO
from unittest.mock import MagicMock, patch
import pytest
from app import app
from mobile.api import _issue_token


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


def test_create_post_v1_sync_route_retired(client):
    # Integration hardening: POST /api/mobile/v1/kids/posts was a synchronous
    # multipart upload-through-Flask route that bypassed the v2
    # session -> R2 quarantine -> background moderation pipeline
    # (AGENTS.md rules 6/7). It now returns 410 directing callers to v2.
    headers = _child_headers(202)
    with patch("mobile.api.fetch_one", return_value={"user_id": 202, "role": "CHILD", "account_status": "ACTIVE"}):
        res = client.post(
            "/api/mobile/v1/kids/posts",
            headers=headers,
            data={
                "caption": "My exciting robotics project",
                "content_category": "Science",
                "audience_age_group": "12-14",
            },
        )
        assert res.status_code == 410
        assert res.get_json()["error"] == "deprecated_use_v2_upload"
        assert res.get_json()["use"] == "/api/mobile/v2/uploads/session"


def test_child_cannot_mutate_parent_controls(client):
    headers = _child_headers(202)
    with patch("mobile.api.fetch_one", return_value={"user_id": 202, "role": "CHILD", "account_status": "ACTIVE"}):
        # Child trying to update controls endpoint
        res = client.put(
            "/api/mobile/v1/parent/controls/202",
            headers=headers,
            json={"allow_reels": True, "daily_screen_time_minutes": 180},
        )
        assert res.status_code == 403
        assert res.get_json()["error"] == "role_forbidden"

        # Child trying to mutate read-only /kids/settings endpoint
        res_settings = client.put(
            "/api/mobile/v1/kids/settings",
            headers=headers,
            json={"daily_limit": 180},
        )
        assert res_settings.status_code == 405  # Method Not Allowed


def test_like_toggle_behavior(client):
    headers = _child_headers(202)
    with patch("mobile.api.fetch_one") as mock_fetch, \
         patch("mobile.api.execute") as mock_exec, \
         patch("mobile.api._child_gate", return_value=None), \
         patch("mobile.api.post_visible_to", return_value={"child_id": 202, "post_id": 10}), \
         patch("mobile.api.can_interact", return_value=True):
        
        # 1st call: not yet liked -> inserts like -> liked=True
        mock_fetch.side_effect = [
            {"user_id": 202, "role": "CHILD", "account_status": "ACTIVE"},  # auth
            None,  # SELECT 1 FROM likes -> not liked
            {"n": 1},  # COUNT(*) likes -> 1
        ]
        res1 = client.post("/api/mobile/v1/kids/posts/10/like", headers=headers)
        assert res1.status_code == 200
        assert res1.get_json()["ok"] is True
        assert res1.get_json()["liked"] is True
        assert res1.get_json()["likes"] == 1

        # 2nd call: already liked -> deletes like -> liked=False
        mock_fetch.side_effect = [
            {"user_id": 202, "role": "CHILD", "account_status": "ACTIVE"},  # auth
            {"1": 1},  # SELECT 1 FROM likes -> already liked
            {"n": 0},  # COUNT(*) likes -> 0
        ]
        res2 = client.post("/api/mobile/v1/kids/posts/10/like", headers=headers)
        assert res2.status_code == 200
        assert res2.get_json()["ok"] is True
        assert res2.get_json()["liked"] is False
        assert res2.get_json()["likes"] == 0


def test_comments_moderation_filter(client):
    headers = _child_headers(202)
    with patch("mobile.api.fetch_one", return_value={"user_id": 202, "role": "CHILD", "account_status": "ACTIVE"}), \
         patch("mobile.api.fetch_all") as mock_fetch_all, \
         patch("mobile.api._child_gate", return_value=None), \
         patch("mobile.api.post_visible_to", return_value={"post_id": 10, "child_id": 202}):

        # GET comments returns only ALLOWED comments
        mock_fetch_all.return_value = [
            {
                "comment_id": 1,
                "post_id": 10,
                "child_id": 303,
                "comment_text": "Great work on the robot!",
                "moderation_status": "ALLOWED",
                "created_at": "2026-09-09T00:00:00",
                "full_name": "Friend Kid",
                "username": "friend_kid",
                "profile_picture": None,
            }
        ]
        res = client.get("/api/mobile/v1/kids/posts/10/comments", headers=headers)
        assert res.status_code == 200
        data = res.get_json()
        assert len(data["comments"]) == 1
        assert data["comments"][0]["comment_text"] == "Great work on the robot!"

        # Posting comment with phone number PII is rejected
        res_pii = client.post(
            "/api/mobile/v1/kids/posts/10/comment",
            headers=headers,
            json={"text": "Call me at 555-123-4567 right now"},
        )
        assert res_pii.status_code == 400
        assert res_pii.get_json()["error"] == "contact_sharing_blocked"


def test_chat_approved_connection_enforced(client):
    headers = _child_headers(202)
    with patch("mobile.api.fetch_one", return_value={"user_id": 202, "role": "CHILD", "account_status": "ACTIVE"}), \
         patch("mobile.api._child_gate", return_value=None), \
         patch("mobile.api.conversation", return_value=None):
        # Peer without approved connection has no conversation
        res = client.get("/api/mobile/v1/kids/chat/999", headers=headers)
        assert res.status_code == 403
        assert res.get_json()["error"] == "approved_connection_required"


def test_profile_supported_fields_persisted(client):
    headers = _child_headers(202)
    mock_decision = MagicMock(action="ALLOW")
    with patch("mobile.api.fetch_one", return_value={"user_id": 202, "role": "CHILD", "account_status": "ACTIVE"}), \
         patch("mobile.api._child_gate", return_value=None), \
         patch("mobile.api.get_child_profile", return_value={"child_id": 202, "full_name": "Test Child"}), \
         patch("mobile.api.evaluate", return_value=({}, mock_decision)), \
         patch("mobile.api.create_child_profile") as mock_create, \
         patch("mobile.api.replace_profile_tags") as mock_tags, \
         patch("mobile.api.parent_notify"), \
         patch("mobile.api.counts", return_value={"posts": 2, "followers": 1, "following": 1}), \
         patch("mobile.api.visible_profile_posts", return_value=[]), \
         patch("mobile.api.controls_for_child", return_value={}), \
         patch("mobile.api.minutes_today", return_value=15):

        res = client.put(
            "/api/mobile/v1/kids/profile",
            headers=headers,
            json={
                "bio": "Building AI models and drawing planets!",
                "skills": ["Python", "Robotics"],
                "interests": ["Astronomy", "Math"],
                "ambitions": ["AI Researcher"],
            },
        )
        assert res.status_code == 200
        assert res.get_json()["ok"] is True
        mock_create.assert_called_once()
        mock_tags.assert_called_once_with(202, ["Python", "Robotics"], ["Astronomy", "Math"], ["AI Researcher"])


def test_profile_parent_managed_fields_rejected(client):
    # c4c5414: children cannot edit discovery identity fields (school_name,
    # location, current_class, date_of_birth) — those are parent-managed.
    headers = _child_headers(202)
    with patch("mobile.api.fetch_one", return_value={"user_id": 202, "role": "CHILD", "account_status": "ACTIVE"}), \
         patch("mobile.api._child_gate", return_value=None), \
         patch("mobile.api.get_child_profile", return_value={"child_id": 202, "full_name": "Test Child"}), \
         patch("mobile.api.create_child_profile") as mock_create:
        for field, value in (
            ("school_name", "Starlight Academy"),
            ("current_class", "Grade 6"),
            ("location", "Bengaluru"),
            ("date_of_birth", "2015-01-01"),
        ):
            res = client.put(
                "/api/mobile/v1/kids/profile",
                headers=headers,
                json={field: value},
            )
            assert res.status_code == 400, field
            assert res.get_json()["error"] == "profile_field_parent_managed", field
        mock_create.assert_not_called()
