"""Contract tests for the minimal GET /api/mobile/v1/me onboarding addition.

Face/biometric verification was removed from LittleNet on 2026-09-22.
CHILD responses now carry only the authoritative quiz gate state
(``{"quiz_required": bool}``). PARENT/ADMIN responses omit onboarding.

The mobile token revocation lookup is stubbed: it needs PostgreSQL, which
is orthogonal to the onboarding payload contract under test.
"""
from contextlib import ExitStack
from unittest.mock import patch

import pytest
from app import app
from mobile.api import _issue_token


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _headers(user_id, role):
    token = _issue_token({"user_id": user_id, "role": role})
    return {"Authorization": f"Bearer {token}"}


def _user_row(user_id, role):
    return {
        "user_id": user_id,
        "username": "test_user",
        "full_name": "Test User",
        "email": "test@example.com",
        "role": role,
        "age": 10 if role == "CHILD" else 35,
        "account_status": "ACTIVE",
    }


def _ctx(user_id, role, quiz_required=False, onboarding_quiz=False):
    """Patch stack for a /me request: auth user row, quiz gates, no revocation DB."""
    stack = ExitStack()
    stack.enter_context(
        patch(
            "mobile.api.fetch_one",
            side_effect=lambda query, params=None: _user_row(user_id, role) if "FROM users" in query else None,
        )
    )
    stack.enter_context(patch("mobile.api.get_child_profile", return_value={"child_id": user_id}))
    stack.enter_context(
        patch(
            "mobile.api.feed_quiz_state",
            return_value={"required": quiz_required, "posts_seen": 0, "interval": 4},
        )
    )
    stack.enter_context(patch("mobile.api.needs_onboarding_quiz", return_value=onboarding_quiz))
    stack.enter_context(patch("mobile.api._mobile_token_revoked", return_value=False))
    return stack


def test_me_unauthenticated(client):
    res = client.get("/api/mobile/v1/me")
    assert res.status_code == 401
    assert res.get_json()["error"] == "mobile_auth_required"


def test_me_child_no_quiz_gates_clear(client):
    with _ctx(202, "CHILD"):
        res = client.get("/api/mobile/v1/me", headers=_headers(202, "CHILD"))
    assert res.status_code == 200
    payload = res.get_json()
    assert payload["ok"] is True
    assert payload["onboarding"] == {"quiz_required": False}
    assert "face_required" not in payload["onboarding"]


def test_me_child_with_onboarding_quiz(client):
    with _ctx(202, "CHILD", onboarding_quiz=True):
        res = client.get("/api/mobile/v1/me", headers=_headers(202, "CHILD"))
    assert res.status_code == 200
    assert res.get_json()["onboarding"] == {"quiz_required": True}


def test_me_child_with_feed_quiz(client):
    with _ctx(202, "CHILD", quiz_required=True):
        res = client.get("/api/mobile/v1/me", headers=_headers(202, "CHILD"))
    assert res.status_code == 200
    assert res.get_json()["onboarding"] == {"quiz_required": True}


def test_me_parent_omits_onboarding(client):
    with _ctx(101, "PARENT"):
        res = client.get("/api/mobile/v1/me", headers=_headers(101, "PARENT"))
    assert res.status_code == 200
    assert "onboarding" not in res.get_json()


def test_me_admin_omits_onboarding(client):
    with _ctx(1, "ADMIN"):
        res = client.get("/api/mobile/v1/me", headers=_headers(1, "ADMIN"))
    assert res.status_code == 200
    assert "onboarding" not in res.get_json()
