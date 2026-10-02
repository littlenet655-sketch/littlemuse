"""Mock-only regressions for naive-TIMESTAMP vs aware-datetime handling.

Legacy columns (child_messages.sent_at, notifications.created_at,
child_vocabulary_progress.next_review_due, ...) are TIMESTAMP WITHOUT TIME ZONE
whose wall-clock lives in the DB session timezone (APP_TIMEZONE). These tests
need no database.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from database.connection import database_aware


@pytest.fixture(autouse=True)
def _kolkata(monkeypatch):
    monkeypatch.setenv("APP_TIMEZONE", "Asia/Kolkata")


def test_database_aware_attaches_session_timezone_to_naive_values():
    naive = datetime(2026, 10, 2, 12, 0, 0)
    aware = database_aware(naive)
    assert aware.tzinfo is not None
    assert aware.utcoffset() == timedelta(hours=5, minutes=30)
    assert aware.astimezone(timezone.utc) == datetime(2026, 10, 2, 6, 30, tzinfo=timezone.utc)


def test_database_aware_leaves_aware_and_non_datetimes_unchanged():
    aware = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)
    assert database_aware(aware) is aware
    assert database_aware("2026-10-02") == "2026-10-02"
    assert database_aware(None) is None


def test_database_aware_falls_back_to_utc_for_invalid_timezone(monkeypatch):
    monkeypatch.setenv("APP_TIMEZONE", "Not/AZone")
    assert database_aware(datetime(2026, 1, 1)).utcoffset() == timedelta(0)


def test_recent_naive_db_timestamp_is_not_in_the_future():
    # A row written "just now" by NOW() in the Kolkata session reads back as a
    # naive Kolkata wall-clock; subtracting it from aware UTC now must be ~0,
    # not -5h30m (which the old utcnow() comparison produced).
    sent_naive = datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None) - timedelta(minutes=10)
    delta = datetime.now(timezone.utc) - database_aware(sent_naive)
    assert timedelta(minutes=9) < delta < timedelta(minutes=11)


def test_recommendation_recency_treats_naive_created_at_as_db_local_time():
    from services.recommendation import _recency_score

    local_now = datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)
    fresh = _recency_score({"created_at": local_now})
    # Interpreted as UTC the value would look 5.5h old; as DB-local it is ~0h old.
    assert fresh == pytest.approx(1.5, abs=0.001)


def test_record_vocabulary_attempt_writes_aware_next_review_due():
    from quiz import learning_service

    captured = []
    with patch.object(learning_service, "fetch_one", return_value=None), \
         patch.object(learning_service, "execute", side_effect=lambda sql, params=(), **kw: captured.append(params)):
        learning_service.record_vocabulary_attempt(1, "hello", "hi", True)
        learning_service.record_vocabulary_attempt(1, "hello", "hi", False)

    assert len(captured) == 2
    for params in captured:
        next_due = params[4]
        assert next_due.tzinfo is not None, "naive datetime.now() would be stored as APP_TIMEZONE wall-clock"
    now = datetime.now(timezone.utc)
    assert timedelta(hours=23) < captured[0][4] - now < timedelta(hours=25)
    assert timedelta(hours=3) < captured[1][4] - now < timedelta(hours=5)


def test_record_vocabulary_attempt_update_path_writes_aware_next_review_due():
    from quiz import learning_service

    existing = {"progress_id": 7, "times_seen": 1, "times_correct": 0}
    captured = []
    with patch.object(learning_service, "fetch_one", return_value=existing), \
         patch.object(learning_service, "execute", side_effect=lambda sql, params=(), **kw: captured.append(params)):
        learning_service.record_vocabulary_attempt(1, "hello", "hi", True)

    assert captured and captured[0][2].tzinfo is not None
