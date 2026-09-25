"""Liked/saved activity logging for parent Activity History.

Covers:
- like/unlike on social posts writes POST_LIKED / POST_UNLIKED with metadata only
- save/unsave on social posts writes POST_SAVED / POST_UNSAVED
- like/save on curated reels writes CURATED_LIKED / CURATED_SAVED (and UNLIKE/UNSAVE)
- parent activity endpoint exposes liked_saved for the own child and keeps the
  parent-owns-child gate (404 for another parent's child)
- _liked_saved_snapshot keeps the latest state per target (unlike removes the item)
"""
from datetime import datetime
from unittest.mock import patch

import pytest

from app import app
from mobile.api import _issue_token, _liked_saved_snapshot

CHILD_ID = 202
PARENT_ID = 101
POST_ID = 5
CURATED_ID = 7


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


def child_headers(user_id=CHILD_ID):
    token = _issue_token(
        {
            "user_id": user_id,
            "username": "kid",
            "full_name": "Kid",
            "role": "CHILD",
            "account_status": "ACTIVE",
            "session_version": 1,
        }
    )
    return {"Authorization": f"Bearer {token}"}


def parent_headers(user_id=PARENT_ID):
    token = _issue_token(
        {
            "user_id": user_id,
            "username": "ptest",
            "full_name": "Test Parent",
            "role": "PARENT",
            "account_status": "ACTIVE",
            "session_version": 1,
        }
    )
    return {"Authorization": f"Bearer {token}"}


def child_user_row(user_id=CHILD_ID):
    return {
        "user_id": user_id,
        "username": "kid",
        "full_name": "Kid",
        "email": "kid@test.invalid",
        "role": "CHILD",
        "account_status": "ACTIVE",
        "session_version": 1,
    }


def parent_user_row(user_id=PARENT_ID):
    return {
        "user_id": user_id,
        "username": "ptest",
        "full_name": "Test Parent",
        "email": "parent@test.invalid",
        "role": "PARENT",
        "account_status": "ACTIVE",
        "session_version": 1,
    }


def test_like_and_unlike_log_rows(client):
    """Like writes POST_LIKED; unlike writes POST_UNLIKED. Metadata only, child from session."""
    state = {"liked": False}
    calls = []

    def fetch_one_router(sql, params=()):
        if "FROM users WHERE user_id" in sql:
            return child_user_row()
        if "COUNT(*)" in sql:
            return {"n": 1 if state["liked"] else 0}
        if "FROM likes WHERE post_id" in sql:
            return {"1": 1} if state["liked"] else None
        return None

    def fake_log(child_id, activity_type, data=None):
        calls.append((child_id, activity_type, data or {}))

    patches = [
        patch("mobile.api._child_gate", return_value=None),
        patch("mobile.api.post_visible_to", return_value={"post_id": POST_ID, "child_id": 303}),
        patch("mobile.api.can_interact", return_value=True),
    ]
    with patch("mobile.api._mobile_token_revoked", return_value=False), \
         patch("mobile.api.fetch_one", side_effect=fetch_one_router), \
         patch("mobile.api.execute", return_value=None), \
         patch("mobile.api.log", side_effect=fake_log), \
         patch("mobile.api.record_signal"), \
         patch("mobile.api.notify"), \
         patch("mobile.api._child_gate", return_value=None), \
         patch("mobile.api.post_visible_to", return_value={"post_id": POST_ID, "child_id": 303}), \
         patch("mobile.api.can_interact", return_value=True):
        like = client.post(f"/api/mobile/v1/kids/posts/{POST_ID}/like", headers=child_headers())
        assert like.status_code == 200 and like.get_json()["liked"] is True
        state["liked"] = True
        unlike = client.post(f"/api/mobile/v1/kids/posts/{POST_ID}/like", headers=child_headers())
        assert unlike.status_code == 200 and unlike.get_json()["liked"] is False

    assert calls[0] == (CHILD_ID, "POST_LIKED", {"target_type": "POST", "target_id": POST_ID})
    assert calls[1] == (CHILD_ID, "POST_UNLIKED", {"target_type": "POST", "target_id": POST_ID})
    # metadata only: no captions, no media bytes; child comes from the session
    for logged_child, _atype, data in calls:
        assert set(data.keys()) == {"target_type", "target_id"}
        assert logged_child == CHILD_ID


def test_save_and_unsave_log_rows(client):
    state = {"saved": False}
    calls = []

    def fetch_one_router(sql, params=()):
        if "FROM users WHERE user_id" in sql:
            return child_user_row()
        if "FROM saved_posts" in sql:
            return {"1": 1} if state["saved"] else None
        return None

    def fake_log(child_id, activity_type, data=None):
        calls.append((child_id, activity_type, data or {}))

    with patch("mobile.api._mobile_token_revoked", return_value=False), \
         patch("mobile.api.fetch_one", side_effect=fetch_one_router), \
         patch("mobile.api.execute", return_value=None), \
         patch("mobile.api.log", side_effect=fake_log), \
         patch("mobile.api.record_signal"), \
         patch("mobile.api._child_gate", return_value=None), \
         patch("mobile.api.post_visible_to", return_value={"post_id": POST_ID, "child_id": 303}):
        save = client.post(f"/api/mobile/v1/kids/posts/{POST_ID}/save", headers=child_headers())
        assert save.status_code == 200 and save.get_json()["saved"] is True
        state["saved"] = True
        unsave = client.post(f"/api/mobile/v1/kids/posts/{POST_ID}/save", headers=child_headers())
        assert unsave.status_code == 200 and unsave.get_json()["saved"] is False

    assert calls[0] == (CHILD_ID, "POST_SAVED", {"target_type": "POST", "target_id": POST_ID})
    assert calls[1] == (CHILD_ID, "POST_UNSAVED", {"target_type": "POST", "target_id": POST_ID})


def test_curated_like_and_save_log_rows(client):
    calls = []

    def fetch_one_router(sql, params=()):
        if "FROM users WHERE user_id" in sql:
            return child_user_row()
        if "FROM content_reactions" in sql or "FROM content_saves" in sql:
            return None
        return {"n": 0}

    def fake_log(child_id, activity_type, data=None):
        calls.append((child_id, activity_type, data or {}))

    with patch("mobile.api._mobile_token_revoked", return_value=False), \
         patch("mobile.api.fetch_one", side_effect=fetch_one_router), \
         patch("mobile.api.execute", return_value=None), \
         patch("mobile.api.log", side_effect=fake_log), \
         patch("mobile.api.record_signal"), \
         patch("mobile.api._child_gate", return_value=None), \
         patch("mobile.api.curated_item_visible_to", return_value=True):
        like = client.post(
            f"/api/mobile/v2/kids/content/CURATED/{CURATED_ID}/like", headers=child_headers()
        )
        assert like.status_code == 200 and like.get_json()["liked"] is True
        save = client.post(
            f"/api/mobile/v2/kids/content/CURATED/{CURATED_ID}/save", headers=child_headers()
        )
        assert save.status_code == 200 and save.get_json()["saved"] is True

    assert calls[0] == (CHILD_ID, "CURATED_LIKED", {"target_type": "CURATED", "target_id": CURATED_ID})
    assert calls[1] == (CHILD_ID, "CURATED_SAVED", {"target_type": "CURATED", "target_id": CURATED_ID})


def test_curated_unlike_and_unsave_log_rows(client):
    calls = []

    def fetch_one_router(sql, params=()):
        if "FROM users WHERE user_id" in sql:
            return child_user_row()
        if "COUNT(*)" in sql:
            return {"n": 0}
        if "FROM content_reactions" in sql or "FROM content_saves" in sql:
            return {"1": 1}
        return None

    def fake_log(child_id, activity_type, data=None):
        calls.append((child_id, activity_type, data or {}))

    with patch("mobile.api._mobile_token_revoked", return_value=False), \
         patch("mobile.api.fetch_one", side_effect=fetch_one_router), \
         patch("mobile.api.execute", return_value=None), \
         patch("mobile.api.log", side_effect=fake_log), \
         patch("mobile.api.record_signal"), \
         patch("mobile.api._child_gate", return_value=None), \
         patch("mobile.api.curated_item_visible_to", return_value=True):
        unlike = client.post(
            f"/api/mobile/v2/kids/content/CURATED/{CURATED_ID}/like", headers=child_headers()
        )
        assert unlike.status_code == 200 and unlike.get_json()["liked"] is False
        unsave = client.post(
            f"/api/mobile/v2/kids/content/CURATED/{CURATED_ID}/save", headers=child_headers()
        )
        assert unsave.status_code == 200 and unsave.get_json()["saved"] is False

    assert calls[0] == (CHILD_ID, "CURATED_UNLIKED", {"target_type": "CURATED", "target_id": CURATED_ID})
    assert calls[1] == (CHILD_ID, "CURATED_UNSAVED", {"target_type": "CURATED", "target_id": CURATED_ID})


def test_parent_activity_gate_blocks_other_parents_child(client):
    with patch("mobile.api._mobile_token_revoked", return_value=False), \
         patch("mobile.api.fetch_one", return_value=parent_user_row()), \
         patch("mobile.api.owns", return_value=False), \
         patch("mobile.api.fetch_all") as spy:
        denied = client.get("/api/mobile/v1/parent/activity/999", headers=parent_headers())
    assert denied.status_code == 404
    spy.assert_not_called()


def test_parent_activity_returns_liked_saved_for_own_child(client):
    snapshot = [
        {
            "log_id": 9,
            "activity_type": "POST_LIKED",
            "action": "liked",
            "target_type": "POST",
            "target_id": POST_ID,
            "target_label": "Post by @friend",
            "created_at": "2026-09-25T10:00:00",
        },
        {
            "log_id": 10,
            "activity_type": "CURATED_SAVED",
            "action": "saved",
            "target_type": "CURATED",
            "target_id": CURATED_ID,
            "target_label": "Ocean Wonders",
            "created_at": "2026-09-25T11:00:00",
        },
    ]
    with patch("mobile.api._mobile_token_revoked", return_value=False), \
         patch("mobile.api.fetch_one", return_value=parent_user_row()), \
         patch("mobile.api.owns", return_value=True), \
         patch("mobile.api.fetch_all", return_value=[]), \
         patch("mobile.api._liked_saved_snapshot", return_value=snapshot):
        response = client.get(f"/api/mobile/v1/parent/activity/{CHILD_ID}", headers=parent_headers())
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["liked_saved"] == snapshot
    # existing shape untouched
    assert "events" in payload and "recent_chat_partners" in payload


def test_liked_saved_snapshot_keeps_latest_state_per_target():
    rows = [
        {
            "log_id": 1,
            "activity_type": "POST_LIKED",
            "activity_data": {"target_type": "POST", "target_id": POST_ID},
            "created_at": datetime(2026, 9, 25, 9, 0),
        },
        {
            "log_id": 2,
            "activity_type": "POST_UNLIKED",
            "activity_data": {"target_type": "POST", "target_id": POST_ID},
            "created_at": datetime(2026, 9, 25, 10, 0),
        },
        {
            "log_id": 3,
            "activity_type": "CURATED_SAVED",
            "activity_data": {"target_type": "CURATED", "target_id": CURATED_ID},
            "created_at": datetime(2026, 9, 25, 11, 0),
        },
    ]

    def fetch_all_router(sql, params=()):
        if "DISTINCT ON" in sql:
            return rows
        if "FROM posts" in sql:
            return [{"post_id": POST_ID, "username": "friend", "full_name": "Friend"}]
        if "FROM curated_content" in sql:
            return [{"content_id": CURATED_ID, "title": "Ocean Wonders"}]
        return []

    with patch("mobile.api.fetch_all", side_effect=fetch_all_router):
        snap = _liked_saved_snapshot(CHILD_ID)

    # POST 5 was unliked after being liked -> excluded; CURATED 7 still saved
    assert len(snap) == 1
    item = snap[0]
    assert item["action"] == "saved"
    assert item["target_type"] == "CURATED"
    assert item["target_id"] == CURATED_ID
    assert item["target_label"] == "Ocean Wonders"
    assert set(item.keys()) == {
        "log_id", "activity_type", "action", "target_type",
        "target_id", "target_label", "created_at",
    }


def test_liked_saved_snapshot_labels_post_author():
    rows = [
        {
            "log_id": 4,
            "activity_type": "POST_SAVED",
            "activity_data": {"target_type": "POST", "target_id": POST_ID},
            "created_at": datetime(2026, 9, 25, 12, 0),
        },
    ]

    def fetch_all_router(sql, params=()):
        if "DISTINCT ON" in sql:
            return rows
        if "FROM posts" in sql:
            return [{"post_id": POST_ID, "username": "friend", "full_name": "Friend"}]
        return []

    with patch("mobile.api.fetch_all", side_effect=fetch_all_router):
        snap = _liked_saved_snapshot(CHILD_ID)

    assert len(snap) == 1
    assert snap[0]["action"] == "saved"
    assert snap[0]["target_label"] == "Post by @friend"
