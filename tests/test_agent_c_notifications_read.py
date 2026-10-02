"""Agent C: authoritative kids notifications mark-read (smallest safe route)."""
import os
from urllib.parse import urlparse

import pytest
from app import create_app
from config import Config
from database.connection import execute, fetch_one
from mobile.api import _issue_token


def _h(uid, role):
    return {"Authorization": f"Bearer {_issue_token({'user_id': uid, 'role': role})}", "Content-Type": "application/json"}


def test_kids_notifications_read_marks_own_only():
    disposable_url = os.getenv("DISPOSABLE_DATABASE_URL", "")
    hostname = (urlparse(Config.DATABASE_URL).hostname or "").lower()
    if not disposable_url or Config.DATABASE_URL != disposable_url or not hostname or hostname in {"localhost", "127.0.0.1"} or "prod" in hostname or "production" in hostname:
        pytest.skip("A verified disposable PostgreSQL hostname is required")
    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()
    me = fetch_one("SELECT user_id FROM users WHERE role='CHILD' AND account_status='ACTIVE' LIMIT 1")
    assert me, "notification test requires at least one active CHILD fixture"
    other = fetch_one("SELECT user_id FROM users WHERE role='CHILD' AND account_status='ACTIVE' AND user_id<>%s LIMIT 1", (me["user_id"],))
    assert other, "notification test requires a second active CHILD fixture"
    execute("DELETE FROM notifications WHERE user_id IN (%s,%s)", (me["user_id"], other["user_id"]))
    execute("INSERT INTO notifications(user_id, notification_type, message, is_read) VALUES(%s,'LIKE','hello',FALSE)", (me["user_id"],))
    execute("INSERT INTO notifications(user_id, notification_type, message, is_read) VALUES(%s,'LIKE','other',FALSE)", (other["user_id"],))
    mine = fetch_one("SELECT notification_id FROM notifications WHERE user_id=%s", (me["user_id"],))
    theirs = fetch_one("SELECT notification_id FROM notifications WHERE user_id=%s", (other["user_id"],))

    # Unauthenticated is rejected.
    assert client.post("/api/mobile/v1/kids/notifications/read", json={}).status_code == 401

    # Scoped ids mark only the caller's rows (idempotent).
    res = client.post("/api/mobile/v1/kids/notifications/read", headers=_h(me["user_id"], "CHILD"), json={"notification_ids": [mine["notification_id"], theirs["notification_id"]]})
    assert res.status_code == 200
    assert res.get_json()["marked"] == 1
    assert fetch_one("SELECT is_read r FROM notifications WHERE notification_id=%s", (mine["notification_id"],))["r"] is True
    assert fetch_one("SELECT is_read r FROM notifications WHERE notification_id=%s", (theirs["notification_id"],))["r"] is False

    # Empty body marks all own rows.
    res_all = client.post("/api/mobile/v1/kids/notifications/read", headers=_h(me["user_id"], "CHILD"), json={})
    assert res_all.status_code == 200
    assert res_all.get_json()["marked"] == "all"

    # Invalid payload is rejected without touching rows.
    assert client.post("/api/mobile/v1/kids/notifications/read", headers=_h(me["user_id"], "CHILD"), json={"notification_ids": ["nope"]}).status_code == 400
    execute("DELETE FROM notifications WHERE user_id IN (%s,%s)", (me["user_id"], other["user_id"]))
