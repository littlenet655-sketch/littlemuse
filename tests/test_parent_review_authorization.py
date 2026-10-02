"""Parent Review authorization fixtures.

Controlled in-memory fixtures only. No production REVIEW rows are read or written.
"""
from unittest.mock import patch

import pytest

from app import app
from mobile.api import _issue_token, _resolve_parent_review


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


def _headers(user_id, role):
    token = _issue_token({"user_id": user_id, "role": role, "full_name": role.title()})
    return {"Authorization": f"Bearer {token}"}


def _user(user_id, role):
    return {
        "user_id": user_id,
        "username": f"u{user_id}",
        "full_name": role.title(),
        "email": f"{role.lower()}@test.invalid",
        "role": role,
        "age": 10 if role == "CHILD" else None,
        "account_status": "ACTIVE",
        "session_version": 1,
    }


class _Cursor:
    def __init__(self, handler):
        self.handler = handler
        self.statements = []
        self._row = None

    def execute(self, sql, params=None):
        q = " ".join(str(sql).split())
        self.statements.append((q, params))
        self._row = self.handler(q, params)

    def fetchone(self):
        return self._row

    def fetchall(self):
        return [self._row] if self._row else []


class _Conn:
    def __init__(self, handler):
        self.cur = _Cursor(handler)
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self.cur

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass


def test_child_cannot_invoke_parent_review_decision(client):
    with patch("mobile.api._mobile_token_revoked", return_value=False), \
         patch("mobile.api.fetch_one", return_value=_user(202, "CHILD")), \
         patch("mobile.api._resolve_parent_review", side_effect=AssertionError("child reached decision")):
        response = client.post(
            "/api/mobile/v1/parent/safety/9",
            headers=_headers(202, "CHILD"),
            json={"action": "APPROVE", "parent_id": 101, "child_id": 7},
        )
    assert response.status_code == 403
    assert response.get_json()["error"] == "role_forbidden"


def test_invalid_action_is_rejected_before_any_write(client):
    with patch("mobile.api._mobile_token_revoked", return_value=False), \
         patch("mobile.api.fetch_one", return_value=_user(101, "PARENT")), \
         patch("mobile.api.get_db_connection", side_effect=AssertionError("db opened")):
        response = client.post(
            "/api/mobile/v1/parent/safety/9",
            headers=_headers(101, "PARENT"),
            json={"action": "DELETE"},
        )
    assert response.status_code == 400
    assert response.get_json()["result"] == "invalid_action"


def test_missing_or_resolved_event_is_not_found_and_query_requires_open(client):
    def handler(q, _params):
        return None

    conn = _Conn(handler)
    with patch("mobile.api._mobile_token_revoked", return_value=False), \
         patch("mobile.api.fetch_one", return_value=_user(101, "PARENT")), \
         patch("mobile.api.get_db_connection", return_value=conn):
        response = client.post(
            "/api/mobile/v1/parent/safety/404",
            headers=_headers(101, "PARENT"),
            json={"action": "BLOCK"},
        )
    assert response.status_code == 404
    assert response.get_json()["result"] == "not_found"
    assert conn.rolled_back
    assert not conn.committed
    sql = conn.cur.statements[0][0]
    assert "status='OPEN'" in sql
    assert "decision='REVIEW'" in sql


def test_client_supplied_parent_or_child_id_cannot_grant_access(client):
    seen = {}

    def handler(q, params):
        if "FROM moderation_events" in q:
            return {
                "event_id": 9, "child_id": 7, "content_type": "TEXT",
                "content_id": 3, "decision": "REVIEW", "status": "OPEN",
            }
        return None

    def owns(parent_id, child_id):
        seen["parent_id"] = parent_id
        seen["child_id"] = child_id
        return False

    conn = _Conn(handler)
    with patch("mobile.api._mobile_token_revoked", return_value=False), \
         patch("mobile.api.fetch_one", return_value=_user(101, "PARENT")), \
         patch("mobile.api.get_db_connection", return_value=conn), \
         patch("mobile.api.owns", side_effect=owns):
        response = client.post(
            "/api/mobile/v1/parent/safety/9",
            headers=_headers(101, "PARENT"),
            json={"action": "APPROVE", "parent_id": 1, "child_id": 7},
        )
    assert response.status_code == 404
    assert response.get_json()["result"] == "forbidden"
    assert seen == {"parent_id": 101, "child_id": 7}
    assert not conn.committed


def test_linked_parent_block_persists_terminal_review(client):
    def handler(q, params):
        if "FROM moderation_events" in q:
            return {
                "event_id": 9, "child_id": 7, "content_type": "COMMENT",
                "content_id": 3, "decision": "REVIEW", "status": "OPEN",
            }
        if q.startswith("SELECT moderation_status"):
            return {"moderation_status": "REVIEW"}
        return None

    conn = _Conn(handler)
    with patch("mobile.api._mobile_token_revoked", return_value=False), \
         patch("mobile.api.fetch_one", return_value=_user(101, "PARENT")), \
         patch("mobile.api.get_db_connection", return_value=conn), \
         patch("mobile.api.owns", return_value=True):
        response = client.post(
            "/api/mobile/v1/parent/safety/9",
            headers=_headers(101, "PARENT"),
            json={"action": "BLOCK", "parent_id": 999},
        )
    assert response.status_code == 200
    assert response.get_json()["result"] == "BLOCK"
    assert conn.committed
    updates = [p for q, p in conn.cur.statements if q.startswith("UPDATE comments")]
    assert updates and updates[0][0] == "BLOCKED"
    reviews = [p for q, p in conn.cur.statements if "INSERT INTO moderation_reviews" in q]
    assert reviews[0][0] == 9
    assert reviews[0][1] == 101
    assert reviews[0][2] == "BLOCK"
    resolved = [q for q, _p in conn.cur.statements if q.startswith("UPDATE moderation_events")]
    assert resolved and "RESOLVED" in resolved[0]


def test_second_decision_on_resolved_event_is_rejected():
    def handler(q, _params):
        assert "status='OPEN'" in q
        return None

    conn = _Conn(handler)
    with patch("mobile.api.get_db_connection", return_value=conn), \
         patch("mobile.api.owns", return_value=True):
        ok, result = _resolve_parent_review(101, 9, "APPROVE")
    assert ok is False
    assert result == "not_found"
    assert not conn.committed
