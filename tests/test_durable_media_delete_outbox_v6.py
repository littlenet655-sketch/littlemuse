import pytest
from unittest.mock import patch
import services.media_outbox as mo
import database.connection as db_conn


def _is_db_available():
    try:
        conn = db_conn.get_db_connection()
        conn.close()
        return True
    except Exception:
        return False


DB_AVAILABLE = _is_db_available()


@pytest.fixture(autouse=True)
def media_outbox_env(monkeypatch):
    if not DB_AVAILABLE:
        # Provide an in-memory mock store for media_delete_outbox when disposable postgres is not running
        table = {}
        counter = [0]

        def mock_execute(sql, params=()):
            sql_clean = " ".join(sql.split())
            if "DELETE FROM media_delete_outbox" in sql_clean:
                prefix = params[0].rstrip("%")
                to_del = [k for k in table if k.startswith(prefix)]
                for k in to_del:
                    del table[k]
            elif "INSERT INTO media_delete_outbox" in sql_clean:
                ref, src, sid = params
                counter[0] += 1
                table[ref] = {
                    "outbox_id": counter[0],
                    "reference": ref,
                    "source_table": src,
                    "source_id": sid,
                    "attempts": 0,
                    "completed_at": None,
                    "last_error": None,
                }
            elif "UPDATE media_delete_outbox SET completed_at" in sql_clean:
                oid = params[0]
                for r in table.values():
                    if r["outbox_id"] == oid:
                        r["completed_at"] = "NOW"
                        r["attempts"] += 1
                        r["last_error"] = None
            elif "UPDATE media_delete_outbox SET attempts=attempts+1" in sql_clean:
                err, oid = params
                for r in table.values():
                    if r["outbox_id"] == oid:
                        r["attempts"] += 1
                        r["last_error"] = err
            elif "UPDATE media_delete_outbox SET attempts=8" in sql_clean or "SET attempts=" in sql_clean:
                ref = params[0]
                if ref in table:
                    table[ref]["attempts"] = 8

        def mock_fetch_all(sql, params=()):
            sql_clean = " ".join(sql.split())
            if "SELECT outbox_id,reference FROM media_delete_outbox" in sql_clean:
                limit = params[0]
                res = [
                    {"outbox_id": r["outbox_id"], "reference": r["reference"]}
                    for r in table.values()
                    if r["completed_at"] is None and r["attempts"] < 8
                ]
                return res[:limit]
            return []

        def mock_fetch_one(sql, params=()):
            sql_clean = " ".join(sql.split())
            if "WHERE reference=%s" in sql_clean:
                ref = params[0]
                return table.get(ref)
            return None

        monkeypatch.setattr(mo, "execute", mock_execute)
        monkeypatch.setattr(mo, "fetch_all", mock_fetch_all)
        monkeypatch.setattr(db_conn, "execute", mock_execute)
        monkeypatch.setattr(db_conn, "fetch_all", mock_fetch_all)
        monkeypatch.setattr(db_conn, "fetch_one", mock_fetch_one)
        yield
    else:
        prefix = "uploads/r2/v6_test_"
        db_conn.execute("DELETE FROM media_delete_outbox WHERE reference LIKE %s", (prefix + "%",))
        yield
        db_conn.execute("DELETE FROM media_delete_outbox WHERE reference LIKE %s", (prefix + "%",))


def test_durable_reconcile_success(monkeypatch):
    deleted_refs = []
    monkeypatch.setattr("services.object_storage.delete_reference", lambda ref: deleted_refs.append(ref) or True)

    ref = "uploads/r2/v6_test_sample.jpg"
    mo.enqueue_delete(ref, "posts", 9999)

    row = db_conn.fetch_one("SELECT * FROM media_delete_outbox WHERE reference=%s", (ref,))
    assert row is not None
    assert row["completed_at"] is None
    assert row["attempts"] == 0

    res = mo.reconcile_pending_deletes(limit=100)
    assert res["completed"] >= 1
    assert ref in deleted_refs

    row_done = db_conn.fetch_one("SELECT * FROM media_delete_outbox WHERE reference=%s", (ref,))
    assert row_done["completed_at"] is not None
    assert row_done["attempts"] == 1

    # Running reconcile again does not process this already-completed row
    deleted_refs.clear()
    mo.reconcile_pending_deletes(limit=100)
    assert ref not in deleted_refs


def test_durable_reconcile_retry_and_exhaustion(monkeypatch):
    def failing_delete(ref):
        raise RuntimeError("Cloudflare R2 503 Service Unavailable")

    monkeypatch.setattr("services.object_storage.delete_reference", failing_delete)

    ref = "uploads/r2/v6_test_fail.mp4"
    mo.enqueue_delete(ref, "posts", 9998)

    # First attempt fails
    res1 = mo.reconcile_pending_deletes(limit=100)
    assert res1["failed"] >= 1

    row = db_conn.fetch_one("SELECT * FROM media_delete_outbox WHERE reference=%s", (ref,))
    assert row["attempts"] == 1
    assert row["completed_at"] is None
    assert "503" in row["last_error"]

    # Manually cap attempts to 8 (exhausted)
    db_conn.execute("UPDATE media_delete_outbox SET attempts=8 WHERE reference=%s", (ref,))
    # When attempts >= 8, reconcile must skip it
    attempt_count_before = db_conn.fetch_one("SELECT attempts FROM media_delete_outbox WHERE reference=%s", (ref,))["attempts"]
    mo.reconcile_pending_deletes(limit=100)
    attempt_count_after = db_conn.fetch_one("SELECT attempts FROM media_delete_outbox WHERE reference=%s", (ref,))["attempts"]
    assert attempt_count_after == attempt_count_before == 8


def test_web_startup_non_blocking():
    from pathlib import Path
    modal_path = Path(__file__).resolve().parents[1] / "modal_web.py"
    if not modal_path.exists():
        modal_path = Path(r"C:\LittleNet-FINAL-WORK\LittleNet\modal_web.py")
    modal_code = modal_path.read_text(encoding="utf-8")
    web_def = modal_code.split("def web():")[1].split("def persist_upload_changes")[0]
    assert "reconcile_pending_deletes" not in web_def
    assert "drain_media_delete_outbox" in modal_code
