"""Regression: upload_sessions.expires_at must live on the same clock as created_at.

``upload_sessions`` stores naive TIMESTAMPs that Postgres reads in the DB session
timezone (Asia/Kolkata by default, see database/connection.py). The session-create
endpoint used to write ``datetime.utcnow()``, which landed 5h30m behind the
``created_at`` default, so brand-new sessions were born with created_at > expires_at
and looked expired to any SQL-side comparison (including the abandoned-session
reaper). These tests pin the invariant at the DB boundary, not at the Python one.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app import create_app
from database.connection import execute, fetch_one
from mobile.api import _issue_token

# Reuse the existing fixtures/helpers rather than duplicating the family graph setup.
from test_phase25_production_hardening import _ensure_child, _make_session


@pytest.fixture(scope="module")
def app():
    a = create_app()
    a.config["TESTING"] = True
    return a


@pytest.fixture(scope="module")
def client(app):
    return app.test_client()


def _create_session(client, child_id: int) -> dict:
    token = _issue_token({"user_id": child_id, "role": "CHILD"})
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
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def test_new_session_is_never_born_expired(client, app):
    with app.app_context():
        _ensure_child(9951, "tz_kid_01")
    body = _create_session(client, 9951)

    with app.app_context():
        row = fetch_one(
            """SELECT created_at, expires_at,
                      (expires_at < CURRENT_TIMESTAMP) AS expired_now,
                      EXTRACT(EPOCH FROM (expires_at - created_at)) AS ttl_seconds
                 FROM upload_sessions WHERE upload_id=%s""",
            (body["upload_id"],),
        )

    assert row["created_at"] < row["expires_at"], "created_at must precede expires_at"
    assert row["expired_now"] is False
    # 900s TTL; allow slack for the gap between Python computing it and the INSERT.
    assert 890 <= float(row["ttl_seconds"]) <= 905


def test_response_expiry_is_valid_aware_iso8601(client, app):
    with app.app_context():
        _ensure_child(9952, "tz_kid_02")
    before = datetime.now(timezone.utc)
    body = _create_session(client, 9952)

    # An aware isoformat() already carries its offset; a trailing "Z" on top of it
    # ("...+00:00Z") is not valid ISO-8601 and breaks strict client parsers.
    assert "+00:00Z" not in str(body["expires_at"])
    parsed = datetime.fromisoformat(str(body["expires_at"]).replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
    delta = (parsed - before).total_seconds()
    assert 890 <= delta <= 910


def test_live_session_is_not_rejected_as_expired(client, app):
    with app.app_context():
        _ensure_child(9953, "tz_kid_03")
        u_id = _make_session(9953)  # aware UTC, +15 minutes

    token = _issue_token({"user_id": 9953, "role": "CHILD"})
    resp = client.post(
        f"/api/mobile/v2/uploads/{u_id}/complete",
        headers={"Authorization": f"Bearer {token}"},
        json={"caption": "still valid"},
    )
    # It may fail later (no object uploaded in this DB-only test) but never as expired.
    assert (resp.get_json() or {}).get("error") != "upload_session_expired"


def test_expired_session_is_rejected_and_marked(client, app):
    with app.app_context():
        _ensure_child(9954, "tz_kid_04")
        u_id = _make_session(9954, expired=True)  # aware UTC, -1 minute

    token = _issue_token({"user_id": 9954, "role": "CHILD"})
    resp = client.post(
        f"/api/mobile/v2/uploads/{u_id}/complete",
        headers={"Authorization": f"Bearer {token}"},
        json={"caption": "late"},
    )
    assert resp.status_code == 400
    assert resp.get_json().get("error") == "upload_session_expired"
    with app.app_context():
        assert fetch_one("SELECT status FROM upload_sessions WHERE upload_id=%s", (u_id,))["status"] == "EXPIRED"


def test_reaper_threshold_agrees_with_writer_clock(client, app):
    """A session created now must not be reaper-eligible; one stale beyond the
    reaper window must be. Guards writer/reaper clock agreement."""
    with app.app_context():
        _ensure_child(9955, "tz_kid_05")
    fresh = _create_session(client, 9955)["upload_id"]
    with app.app_context():
        stale = str(uuid.uuid4())
        execute(
            """INSERT INTO upload_sessions(upload_id, child_id, object_key, media_type, kind,
                   expected_size_bytes, mime_type, extension, status, expires_at)
               VALUES(%s, 9955, %s, 'IMAGE', 'POST', 1, 'image/jpeg', 'jpg', 'PENDING', %s)""",
            (stale, f"uploads/r2/quarantine/9955/{stale}/source.jpg",
             datetime.now(timezone.utc) - timedelta(days=3)),
        )
        threshold = datetime.now(timezone.utc) - timedelta(seconds=86400)
        eligible = {
            str(r["upload_id"])
            for r in (
                __import__("database.connection", fromlist=["fetch_all"]).fetch_all(
                    "SELECT upload_id FROM upload_sessions WHERE status IN ('PENDING','EXPIRED') AND expires_at < %s",
                    (threshold,),
                )
                or []
            )
        }
    assert stale in eligible
    assert fresh not in eligible


# ── Same clock invariant for the other naive-TIMESTAMP expiry sites ───────────

def test_media_retry_backoff_uses_db_clock(app):
    """posts.last_attempt_at is naive session-zone time. A attempt made seconds ago
    must still be inside the backoff window, and one made long ago must not be."""
    from services.media_processor import claim_media_job_lease

    with app.app_context():
        _ensure_child(9956, "tz_kid_06")
        pid = []
        for label, ago in (("recent", "5 seconds"), ("old", "10 minutes")):
            row = execute(
                f"""INSERT INTO posts(child_id, media_type, source_media_path, caption,
                        processing_status, processing_attempts, max_processing_attempts, last_attempt_at)
                    VALUES(9956, 'IMAGE', %s, %s, 'PROCESSING', 2, 5, NOW() - INTERVAL '{ago}')
                    RETURNING post_id""",
                (f"uploads/r2/quarantine/9956/{uuid.uuid4().hex}.jpg", label),
                returning=True,
            )
            pid.append((row[0] if isinstance(row, list) else row)["post_id"])

        acquired_recent, _, info = claim_media_job_lease(pid[0])
        acquired_old, _, _ = claim_media_job_lease(pid[1])

    assert acquired_recent is False and info.get("retry_after_seconds", 0) > 0
    # Backoff for attempts=2 is 10s, so a 5s-old attempt waits <= 10s, never hours.
    assert info["retry_after_seconds"] <= 10
    assert acquired_old is True


def test_approval_token_expiry_uses_db_clock(app):
    """A 48h token is valid at issue time and rejected once past expiry."""
    from auth.service import get_child_approval_details

    with app.app_context():
        _ensure_child(9957, "tz_kid_07")
        results = {}
        for label, delta in (("live", timedelta(hours=47)), ("expired", timedelta(hours=-1)),
                             ("just_expired_offset", timedelta(hours=-2))):
            tok = uuid.uuid4().hex
            execute(
                """UPDATE parent_child_map
                      SET approval_token=%s, approval_token_expires_at=%s,
                          is_token_used=FALSE, approved=FALSE
                    WHERE child_id=9957""",
                (tok, datetime.now(timezone.utc) + delta),
            )
            results[label] = get_child_approval_details(tok, 9900)

    assert results["live"].get("reason") != "TOKEN_EXPIRED"
    assert results["expired"] == {**results["expired"], "valid": False, "reason": "TOKEN_EXPIRED"}
    # Previously a token expired 1-5h ago still validated (5h30m skew).
    assert results["just_expired_offset"].get("reason") == "TOKEN_EXPIRED"
