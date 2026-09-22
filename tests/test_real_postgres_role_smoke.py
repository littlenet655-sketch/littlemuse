"""Real PostgreSQL authenticated role smoke for submission verification.

This module is intentionally skipped in the normal unit suite. CI enables it in a
separate job with a disposable PostgreSQL service so Child/Parent/Admin browser and
React Native bearer-API guards are exercised against the actual production migration
chain instead of mocks.
"""
import json
import os

import pytest


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_REAL_POSTGRES_E2E") != "1",
    reason="requires disposable PostgreSQL service",
)


CHILD_ID = 9101
PARENT_ID = 9102
ADMIN_ID = 9103
OTHER_PARENT_ID = 9104


def _db_exec(sql, params=()):
    import psycopg2

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def _db_fetchone(sql, params=()):
    import psycopg2
    from psycopg2.extras import RealDictCursor

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
        conn.commit()
        return dict(row) if row else None
    finally:
        conn.close()


def _seed_role_fixture():
    _db_exec(
        """
        DELETE FROM users WHERE user_id IN (%s,%s,%s,%s);
        INSERT INTO users(user_id,username,full_name,email,password_hash,role,age,dob,account_status)
        VALUES
          (%s,'ci_child','CI Child','ci-child@example.invalid','x','CHILD',12,'2014-01-01','ACTIVE'),
          (%s,'ci_parent','CI Parent','ci-parent@example.invalid','x','PARENT',NULL,'1985-01-01','ACTIVE'),
          (%s,'ci_admin','CI Admin','ci-admin@example.invalid','x','ADMIN',NULL,'1980-01-01','ACTIVE'),
          (%s,'ci_other_parent','CI Other Parent','ci-other-parent@example.invalid','x','PARENT',NULL,'1982-01-01','ACTIVE');
        """,
        (CHILD_ID, PARENT_ID, ADMIN_ID, OTHER_PARENT_ID, CHILD_ID, PARENT_ID, ADMIN_ID, OTHER_PARENT_ID),
    )
    _db_exec(
        """INSERT INTO child_profiles(child_id,parent_id,full_name,age)
           VALUES(%s,%s,'CI Child',12)
           ON CONFLICT(child_id) DO UPDATE SET
             parent_id=EXCLUDED.parent_id,
             full_name=EXCLUDED.full_name,
             age=EXCLUDED.age""",
        (CHILD_ID, PARENT_ID),
    )
    _db_exec(
        """INSERT INTO child_quiz_progress(child_id,quiz_required)
           VALUES(%s,FALSE)
           ON CONFLICT(child_id) DO UPDATE SET quiz_required=FALSE""",
        (CHILD_ID,),
    )
    _db_exec(
        """
        INSERT INTO parent_child_map(child_id,parent_id,parent_name,parent_email,approved,approved_at,approval_status,parent_verified,verified_parent_id,verified_at)
        VALUES(%s,%s,'CI Parent','ci-parent@example.invalid',TRUE,NOW(),'APPROVED',TRUE,%s,NOW())
        ON CONFLICT(child_id,parent_email) DO UPDATE SET
          parent_id=EXCLUDED.parent_id,
          approved=TRUE,
          approved_at=NOW(),
          approval_status='APPROVED',
          parent_verified=TRUE,
          verified_parent_id=EXCLUDED.verified_parent_id,
          verified_at=NOW();
        """,
        (CHILD_ID, PARENT_ID, PARENT_ID),
    )


def _login(client, user_id, role, name):
    with client.session_transaction() as sess:
        sess.clear()
        sess["user_id"] = user_id
        sess["role"] = role
        sess["full_name"] = name


def _mobile_headers(user_id, role, name):
    from mobile.api import _issue_token

    token = _issue_token({"user_id": user_id, "role": role, "full_name": name})
    return {"Authorization": f"Bearer {token}"}


def test_real_postgres_child_parent_admin_routes_and_live_status_guards():
    _seed_role_fixture()

    from app import create_app

    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    with app.test_client() as client:
        _login(client, CHILD_ID, "CHILD", "CI Child")
        child = client.get("/saved/", follow_redirects=False)
        assert child.status_code == 200, child.get_data(as_text=True)[:500]

        _login(client, PARENT_ID, "PARENT", "CI Parent")
        parent = client.get(f"/parent/usage-report/?child_id={CHILD_ID}", follow_redirects=False)
        assert parent.status_code == 200, parent.get_data(as_text=True)[:500]

        _login(client, ADMIN_ID, "ADMIN", "CI Admin")
        admin = client.get("/admin/users/", follow_redirects=False)
        assert admin.status_code == 200, admin.get_data(as_text=True)[:500]

        # Role confusion must not grant access to another mode.
        _login(client, CHILD_ID, "CHILD", "CI Child")
        wrong_role = client.get("/admin/users/", follow_redirects=False)
        assert wrong_role.status_code in {302, 401, 403}

        # React Native bearer routes must work against the same real database.
        child_mobile = client.get(
            "/api/mobile/v1/kids/home",
            headers=_mobile_headers(CHILD_ID, "CHILD", "CI Child"),
        )
        assert child_mobile.status_code == 200, child_mobile.get_data(as_text=True)[:500]
        assert child_mobile.get_json()["ok"] is True

        parent_mobile = client.get(
            "/api/mobile/v1/parent/dashboard",
            headers=_mobile_headers(PARENT_ID, "PARENT", "CI Parent"),
        )
        assert parent_mobile.status_code == 200, parent_mobile.get_data(as_text=True)[:500]
        assert any(int(k["user_id"]) == CHILD_ID for k in parent_mobile.get_json()["children"])
        child_summary = next(k for k in parent_mobile.get_json()["children"] if int(k["user_id"]) == CHILD_ID)
        assert child_summary["username"] == "ci_child"

        parent_headers = _mobile_headers(PARENT_ID, "PARENT", "CI Parent")
        disabled = client.put(
            f"/api/mobile/v1/parent/controls/{CHILD_ID}",
            headers=parent_headers,
            json={"allow_messaging": False},
        )
        assert disabled.status_code == 200, disabled.get_data(as_text=True)[:500]
        child_messages = client.get(
            "/api/mobile/v1/kids/messages",
            headers=_mobile_headers(CHILD_ID, "CHILD", "CI Child"),
        )
        assert child_messages.status_code == 403
        assert child_messages.get_json()["error"] == "disabled_by_parent"
        enabled = client.put(
            f"/api/mobile/v1/parent/controls/{CHILD_ID}",
            headers=parent_headers,
            json={"allow_messaging": True},
        )
        assert enabled.status_code == 200, enabled.get_data(as_text=True)[:500]

        time_limit = client.put(
            f"/api/mobile/v1/parent/time-limit/{CHILD_ID}",
            headers=parent_headers,
            json={"daily_limit_minutes": 75, "strict_mode": True},
        )
        assert time_limit.status_code == 200
        assert time_limit.get_json()["limit"]["daily_limit_minutes"] == 75

        _db_exec(
            """INSERT INTO parent_notifications(parent_id,child_id,notification_type,notification_message)
               VALUES(%s,%s,'CI_NOTICE','CI parent notification')""",
            (PARENT_ID, CHILD_ID),
        )
        marked_read = client.post("/api/mobile/v1/parent/notifications", headers=parent_headers, json={})
        assert marked_read.status_code == 200
        assert all(item["is_read"] for item in marked_read.get_json()["notifications"])
        activity = client.get(f"/api/mobile/v1/parent/activity/{CHILD_ID}", headers=parent_headers)
        assert activity.status_code == 200
        assert any(item["activity_type"] == "PARENT_CONTROLS_UPDATED" for item in activity.get_json()["events"])

        admin_mobile = client.get(
            "/api/mobile/v1/admin/dashboard",
            headers=_mobile_headers(ADMIN_ID, "ADMIN", "CI Admin"),
        )
        assert admin_mobile.status_code == 200, admin_mobile.get_data(as_text=True)[:500]

        # ESCALATE must append an audit-trail row while leaving the event open,
        # then a later final APPROVE must succeed for the same event.
        event = _db_fetchone(
            """INSERT INTO moderation_events(child_id,content_type,risk_score,decision,reason,status)
               VALUES(%s,'TEXT',55,'REVIEW','CI native escalation smoke','OPEN')
               RETURNING event_id""",
            (CHILD_ID,),
        )
        event_id = int(event["event_id"])
        admin_headers = _mobile_headers(ADMIN_ID, "ADMIN", "CI Admin")

        admin_queue = client.get("/api/mobile/v1/admin/reviews", headers=admin_headers)
        assert admin_queue.status_code == 200
        assert any(int(item["event_id"]) == event_id for item in admin_queue.get_json()["events"])
        admin_detail = client.get(f"/api/mobile/v1/admin/reviews/{event_id}", headers=admin_headers)
        assert admin_detail.status_code == 200
        assert int(admin_detail.get_json()["event"]["event_id"]) == event_id

        other_parent_headers = _mobile_headers(OTHER_PARENT_ID, "PARENT", "CI Other Parent")
        other_queue = client.get("/api/mobile/v1/parent/safety", headers=other_parent_headers)
        assert other_queue.status_code == 200
        assert all(int(item["event_id"]) != event_id for item in other_queue.get_json()["events"])
        cross_parent = client.post(
            f"/api/mobile/v1/parent/safety/{event_id}",
            headers=other_parent_headers,
            json={"action": "APPROVE"},
        )
        assert cross_parent.status_code == 403

        escalated = client.post(
            f"/api/mobile/v1/admin/reviews/{event_id}",
            headers=admin_headers,
            json={"action": "ESCALATE", "notes": "CI escalation"},
        )
        assert escalated.status_code == 200, escalated.get_data(as_text=True)[:500]
        assert escalated.get_json()["status"] == "OPEN"

        approved = client.post(
            f"/api/mobile/v1/admin/reviews/{event_id}",
            headers=admin_headers,
            json={"action": "APPROVE", "notes": "CI final decision"},
        )
        assert approved.status_code == 200, approved.get_data(as_text=True)[:500]
        assert approved.get_json()["status"] == "RESOLVED"
        reviews = _db_fetchone(
            "SELECT COUNT(*)::int n FROM moderation_reviews WHERE event_id=%s",
            (event_id,),
        )
        assert reviews["n"] == 2
        admin_audit = client.get("/api/mobile/v1/admin/audit", headers=admin_headers)
        assert admin_audit.status_code == 200
        assert any(item["action"] == "MODERATION_APPROVE" for item in admin_audit.get_json()["events"])

        # Live account status is authoritative; stale browser and bearer sessions
        # must stop working immediately after suspension.
        _login(client, PARENT_ID, "PARENT", "CI Parent")
        _db_exec("UPDATE users SET account_status='SUSPENDED' WHERE user_id=%s", (PARENT_ID,))
        suspended = client.get(f"/parent/usage-report/?child_id={CHILD_ID}", follow_redirects=False)
        assert suspended.status_code in {302, 403}
        suspended_mobile = client.get("/api/mobile/v1/parent/dashboard", headers=parent_headers)
        assert suspended_mobile.status_code == 401

        _db_exec("UPDATE users SET account_status='ACTIVE' WHERE user_id=%s", (PARENT_ID,))
