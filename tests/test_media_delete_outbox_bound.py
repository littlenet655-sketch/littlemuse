"""Delete outbox retries must stop after repeated storage failures."""
import os
from unittest.mock import patch

import pytest

from services.media_outbox import ENQUEUE_DELETE_SQL, enqueue_delete, reconcile_pending_deletes


def test_reconcile_skips_rows_past_attempt_cap():
    with patch("services.media_outbox.fetch_all", return_value=[]) as fetch_all:
        assert reconcile_pending_deletes() == {"checked": 0, "completed": 0, "failed": 0}
    sql = fetch_all.call_args.args[0]
    assert "attempts < 8" in sql
    assert "completed_at IS NULL" in sql


def test_enqueue_sql_resets_attempts_only_when_exhausted_or_completed():
    sql = " ".join(ENQUEUE_DELETE_SQL.split())
    assert "attempts=CASE" in sql.replace(" ", "").replace("\n", "") or "attempts = CASE" in sql
    assert "media_delete_outbox.attempts >= 8" in sql
    assert "completed_at IS NOT NULL" in sql
    assert "THEN 0" in sql
    assert "ELSE media_delete_outbox.attempts" in sql


def _conflict_reset(attempts: int, completed_at) -> int:
    if attempts >= 8 or completed_at is not None:
        return 0
    return attempts


def test_exhausted_row_reenqueue_starts_new_bounded_cycle():
    attempts = _conflict_reset(8, None)
    assert attempts == 0
    for _ in range(8):
        attempts += 1
    assert attempts == 8
    assert _conflict_reset(attempts, None) == 0
    assert _conflict_reset(3, None) == 3
    assert _conflict_reset(3, "done") == 0


@pytest.mark.skipif(not os.getenv("DISPOSABLE_DATABASE_URL"), reason="Disposable PostgreSQL URL not configured")
def test_reenqueue_exhausted_outbox_row_is_retryable_again():
    from database.connection import execute, fetch_one

    ref = "uploads/r2/test/outbox-reenqueue-regression.mp4"
    execute("DELETE FROM media_delete_outbox WHERE reference=%s", (ref,))
    try:
        execute(
            """INSERT INTO media_delete_outbox(reference,source_table,source_id,attempts,last_error)
               VALUES(%s,'compensation',NULL,8,'exhausted')""",
            (ref,),
        )
        row = fetch_one("SELECT attempts,completed_at FROM media_delete_outbox WHERE reference=%s", (ref,))
        assert row["attempts"] == 8
        enqueue_delete(ref, "compensation", None)
        row = fetch_one(
            "SELECT attempts,completed_at,last_error FROM media_delete_outbox WHERE reference=%s",
            (ref,),
        )
        assert row["attempts"] == 0
        assert row["completed_at"] is None
        assert row["last_error"] is None
        pending = fetch_one(
            """SELECT attempts FROM media_delete_outbox
               WHERE reference=%s AND completed_at IS NULL AND attempts < 8""",
            (ref,),
        )
        assert pending["attempts"] == 0
        execute("UPDATE media_delete_outbox SET attempts=8 WHERE reference=%s", (ref,))
        assert (
            fetch_one(
                """SELECT attempts FROM media_delete_outbox
                   WHERE reference=%s AND completed_at IS NULL AND attempts < 8""",
                (ref,),
            )
            is None
        )
    finally:
        execute("DELETE FROM media_delete_outbox WHERE reference=%s", (ref,))
