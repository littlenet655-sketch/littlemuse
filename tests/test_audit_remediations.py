import json
from pathlib import Path
from flask import Blueprint, Flask
from unittest.mock import MagicMock
from mobile.api import register_mobile_api, _issue_token, _serializer, _AUTH_SALT

ROOT = Path(__file__).resolve().parents[1]


def _make_app():
    app = Flask(__name__)
    app.secret_key = "test-secret"
    bp = Blueprint("mobile_test", __name__)
    register_mobile_api(bp)
    app.register_blueprint(bp)
    return app


def test_cleartext_traffic_disabled_in_app_json():
    app_json = json.loads((ROOT / "mobile_app" / "app.json").read_text(encoding="utf-8"))
    assert app_json["expo"]["android"]["usesCleartextTraffic"] is False, "usesCleartextTraffic must be false for production safety"


def test_mobile_logout_revokes_token(monkeypatch):
    app = _make_app()
    user = {"user_id": 101, "role": "CHILD", "account_status": "ACTIVE", "full_name": "Child"}
    token = _issue_token(user, usage_session_key="session-key-1")

    revocations = []
    monkeypatch.setattr("mobile.api.fetch_one", lambda query, params=(): user if "FROM users" in query else None)
    monkeypatch.setattr("mobile.api.close_session", lambda key: None)
    monkeypatch.setattr("mobile.api.execute", lambda query, params=(): revocations.append(params))

    with app.test_client() as client:
        resp = client.post(
            "/api/mobile/v1/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert len(revocations) > 0
        assert revocations[0][1] == 101


def test_revoked_token_is_rejected(monkeypatch):
    app = _make_app()
    user = {"user_id": 101, "role": "CHILD", "account_status": "ACTIVE", "full_name": "Child"}
    token = _issue_token(user)

    monkeypatch.setattr("mobile.api._mobile_token_revoked", lambda token_value: True)
    monkeypatch.setattr("mobile.api.fetch_one", lambda query, params=(): user)

    with app.test_client() as client:
        resp = client.get(
            "/api/mobile/v1/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401
        data = resp.get_json()
        assert data["error"] == "token_revoked"


def test_v2_kids_heartbeat_normal_and_locked(monkeypatch):
    app = _make_app()
    user = {"user_id": 101, "role": "CHILD", "account_status": "ACTIVE", "full_name": "Child"}
    token = _issue_token(user)

    monkeypatch.setattr("mobile.api.fetch_one", lambda query, params=(): user if "FROM users" in query else None)
    monkeypatch.setattr("mobile.api._child_gate", lambda *args, **kwargs: None)
    monkeypatch.setattr("mobile.api.lock_state", lambda uid: (False, 45))
    monkeypatch.setattr("mobile.api.minutes_today", lambda uid: 15)

    with app.test_client() as client:
        resp = client.post(
            "/api/mobile/v2/kids/heartbeat",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["minutes_today"] == 15
        assert data["remaining_minutes"] == 45
        assert data["locked"] is False


def test_kids_profile_gated_during_quiet_hours(monkeypatch):
    app = _make_app()
    user = {"user_id": 101, "role": "CHILD", "account_status": "ACTIVE", "full_name": "Child"}
    token = _issue_token(user)

    monkeypatch.setattr("mobile.api.fetch_one", lambda query, params=(): user if "FROM users" in query else None)
    # Simulate child gate returning 423 quiet hours
    monkeypatch.setattr("mobile.api._child_gate", lambda *args, **kwargs: (app.response_class(
        response=json.dumps({"error": "quiet_hours", "gate": "quiet_hours"}),
        status=423,
        mimetype="application/json"
    )))

    with app.test_client() as client:
        resp = client.get(
            "/api/mobile/v1/kids/profile",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 423
        data = resp.get_json()
        assert data["error"] == "quiet_hours"


def test_upload_complete_rechecks_parent_controls(monkeypatch):
    app = _make_app()
    user = {"user_id": 101, "role": "CHILD", "account_status": "ACTIVE", "full_name": "Child"}
    token = _issue_token(user)

    monkeypatch.setattr("mobile.api.fetch_one", lambda query, params=(): user if "FROM users" in query else None)

    # Mock db connection cursor
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_cur.fetchone.return_value = {
        "upload_id": "up-123",
        "child_id": 101,
        "kind": "POST",
        "status": "INITIATED",
        "object_key": "uploads/101/up-123/source.jpg",
    }
    monkeypatch.setattr("mobile.api.get_db_connection", lambda: mock_conn)

    # Simulate parent disabled posting in controls
    monkeypatch.setattr(
        "mobile.api._child_gate",
        lambda feature: (
            app.response_class(
                response=json.dumps({"error": "disabled_by_parent", "feature": feature}),
                status=403,
                mimetype="application/json"
            ) if feature == "posting" else None
        ),
    )

    with app.test_client() as client:
        resp = client.post(
            "/api/mobile/v2/uploads/up-123/complete",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403
        data = resp.get_json()
        assert data["error"] == "disabled_by_parent"
        assert data["feature"] == "posting"


def test_session_version_invalidation(monkeypatch):
    app = _make_app()
    user = {"user_id": 101, "role": "CHILD", "account_status": "ACTIVE", "full_name": "Child", "session_version": 1}
    token = _issue_token(user)

    # Initial request with matching session_version succeeds
    monkeypatch.setattr("mobile.api.fetch_one", lambda query, params=(): user if "FROM users" in query else None)
    monkeypatch.setattr("mobile.api._child_gate", lambda feature=None: None)

    with app.test_client() as client:
        resp = client.get(
            "/api/mobile/v1/kids/profile",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    # User's session_version in database is incremented (e.g. on password reset)
    user_updated = dict(user, session_version=2)
    monkeypatch.setattr("mobile.api.fetch_one", lambda query, params=(): user_updated if "FROM users" in query else None)

    with app.test_client() as client:
        resp = client.get(
            "/api/mobile/v1/kids/profile",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401
        data = resp.get_json()
        assert data["error"] == "session_revoked"


def test_legacy_token_without_session_version_is_rejected(monkeypatch):
    app = _make_app()
    user = {"user_id": 101, "role": "CHILD", "account_status": "ACTIVE", "full_name": "Child", "session_version": 2}
    token = _serializer(_AUTH_SALT).dumps({"uid": 101, "role": "CHILD", "name": "Child"})
    monkeypatch.setattr("mobile.api.fetch_one", lambda query, params=(): None if "mobile_token_revocations" in query else user)

    with app.test_client() as client:
        resp = client.get("/api/mobile/v1/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401
        assert resp.get_json()["error"] == "session_revoked"


def test_impression_batch_does_not_count_rejected_session_items(monkeypatch):
    app = _make_app()
    user = {"user_id": 101, "role": "CHILD", "account_status": "ACTIVE", "full_name": "Child", "session_version": 1}
    token = _issue_token(user)
    monkeypatch.setattr("mobile.api.fetch_one", lambda query, params=(): user if "FROM users" in query else None)
    monkeypatch.setattr("mobile.api._child_gate", lambda feature=None: None)
    monkeypatch.setattr("services.curated_feed.record_feed_impression", lambda *args, **kwargs: False)

    with app.test_client() as client:
        resp = client.post(
            "/api/mobile/v2/kids/impressions/batch",
            headers={"Authorization": f"Bearer {token}"},
            json={"events": [{"session_id": "another-child-session", "source_type": "SOCIAL", "source_id": 55, "surface": "REELS"}]},
        )
        assert resp.status_code == 200
        assert resp.get_json()["processed"] == 1
        assert resp.get_json()["recorded"] == 0


def test_impression_batch_respects_existing_quiz_latch(monkeypatch):
    app = _make_app()
    user = {"user_id": 101, "role": "CHILD", "account_status": "ACTIVE", "full_name": "Child", "session_version": 1}
    token = _issue_token(user)
    recorded = []
    monkeypatch.setattr("mobile.api.fetch_one", lambda query, params=(): user if "FROM users" in query else None)
    monkeypatch.setattr("mobile.api._child_gate", lambda feature=None: None)
    monkeypatch.setattr(
        "mobile.api.feed_quiz_state",
        lambda child_id: {
            "required": True,
            "posts_seen": 5,
            "interval": 5,
            "next_quiz_threshold": 10,
        },
    )
    monkeypatch.setattr(
        "services.curated_feed.record_feed_impression",
        lambda *args, **kwargs: recorded.append((args, kwargs)) or True,
    )

    with app.test_client() as client:
        resp = client.post(
            "/api/mobile/v2/kids/impressions/batch",
            headers={"Authorization": f"Bearer {token}"},
            json={"events": [{"session_id": "session", "source_type": "SOCIAL", "source_id": 55, "surface": "FEED"}]},
        )
        assert resp.status_code == 428
        assert resp.get_json()["error"] == "quiz_required"
        assert recorded == []


def test_removed_face_login_endpoint_is_gone(monkeypatch):
    """Face login was removed 2026-09-22: the endpoint must not exist."""
    app = _make_app()
    user = {"user_id": 101, "role": "CHILD", "account_status": "ACTIVE", "username": "kid_neo", "email": "kid@example.com"}
    monkeypatch.setattr("mobile.api.fetch_one", lambda query, params=(): user if "FROM users" in query else None)

    with app.test_client() as client:
        resp = client.post(
            "/api/mobile/v1/auth/face-login",
            json={"identifier": "kid_neo", "mode": "kids"},
        )
        assert resp.status_code == 404


def test_story_view_checks_visibility(monkeypatch):
    app = _make_app()
    user = {"user_id": 101, "role": "CHILD", "account_status": "ACTIVE", "full_name": "Child", "session_version": 1}
    token = _issue_token(user)

    monkeypatch.setattr("mobile.api.fetch_one", lambda query, params=(): user if "FROM users" in query else None)
    monkeypatch.setattr("mobile.api._child_gate", lambda feature=None: None)

    # 1. Story is not visible / unauthorized
    import services.social
    monkeypatch.setattr(services.social, "story_visible_to", lambda uid, sid: False)

    with app.test_client() as client:
        resp = client.post(
            "/api/mobile/v2/kids/stories/555/view",
            headers={"Authorization": f"Bearer {token}"},
            json={"completion_ratio": 0.5},
        )
        assert resp.status_code == 404
        assert resp.get_json()["error"] == "story_not_found_or_forbidden"

    # 2. Story is visible
    monkeypatch.setattr(services.social, "story_visible_to", lambda uid, sid: True)
    monkeypatch.setattr("mobile.api.execute", lambda query, params=(), **kw: None)

    with app.test_client() as client:
        resp = client.post(
            "/api/mobile/v2/kids/stories/555/view",
            headers={"Authorization": f"Bearer {token}"},
            json={"completion_ratio": 0.5},
        )
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True
