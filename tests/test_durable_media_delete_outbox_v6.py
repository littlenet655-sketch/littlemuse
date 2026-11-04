import pytest
from unittest.mock import patch
from services.media_outbox import reconcile_pending_deletes, enqueue_delete
from database.connection import execute, fetch_one, fetch_all


@pytest.fixture(autouse=True)
def clean_media_outbox_test():
    prefix = "uploads/r2/v6_test_"
    execute("DELETE FROM media_delete_outbox WHERE reference LIKE %s", (prefix + "%",))
    yield
    execute("DELETE FROM media_delete_outbox WHERE reference LIKE %s", (prefix + "%",))


def test_durable_reconcile_success(monkeypatch):
    deleted_refs = []
    monkeypatch.setattr("services.object_storage.delete_reference", lambda ref: deleted_refs.append(ref) or True)

    ref = "uploads/r2/v6_test_sample.jpg"
    enqueue_delete(ref, "posts", 9999)

    row = fetch_one("SELECT * FROM media_delete_outbox WHERE reference=%s", (ref,))
    assert row is not None
    assert row["completed_at"] is None
    assert row["attempts"] == 0

    res = reconcile_pending_deletes(limit=100)
    assert res["completed"] >= 1
    assert ref in deleted_refs

    row_done = fetch_one("SELECT * FROM media_delete_outbox WHERE reference=%s", (ref,))
    assert row_done["completed_at"] is not None
    assert row_done["attempts"] == 1

    # Running reconcile again does not process this already-completed row
    deleted_refs.clear()
    reconcile_pending_deletes(limit=100)
    assert ref not in deleted_refs


def test_durable_reconcile_retry_and_exhaustion(monkeypatch):
    def failing_delete(ref):
        raise RuntimeError("Cloudflare R2 503 Service Unavailable")

    monkeypatch.setattr("services.object_storage.delete_reference", failing_delete)

    ref = "uploads/r2/v6_test_fail.mp4"
    enqueue_delete(ref, "posts", 9998)

    # First attempt fails
    res1 = reconcile_pending_deletes(limit=100)
    assert res1["failed"] >= 1

    row = fetch_one("SELECT * FROM media_delete_outbox WHERE reference=%s", (ref,))
    assert row["attempts"] == 1
    assert row["completed_at"] is None
    assert "503" in row["last_error"]

    # Manually cap attempts to 8 (exhausted)
    execute("UPDATE media_delete_outbox SET attempts=8 WHERE reference=%s", (ref,))
    # When attempts >= 8, reconcile must skip it
    attempt_count_before = fetch_one("SELECT attempts FROM media_delete_outbox WHERE reference=%s", (ref,))["attempts"]
    reconcile_pending_deletes(limit=100)
    attempt_count_after = fetch_one("SELECT attempts FROM media_delete_outbox WHERE reference=%s", (ref,))["attempts"]
    assert attempt_count_after == attempt_count_before == 8


def test_web_startup_non_blocking():
    from pathlib import Path
    modal_code = Path(r"C:\LittleNet-FINAL-WORK\LittleNet\modal_web.py").read_text(encoding="utf-8")
    web_def = modal_code.split("def web():")[1].split("def persist_upload_changes")[0]
    assert "reconcile_pending_deletes" not in web_def
    assert "drain_media_delete_outbox" in modal_code
