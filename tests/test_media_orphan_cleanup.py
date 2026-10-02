"""R2 orphan-cleanup regression tests (DB-free; object storage is mocked).

Covers the media-pipeline fixer workstream:
* ``block_and_cleanup_quarantine`` deletes the quarantine object on
  successful publication (ALLOW) and on BLOCK, logs failures with key-prefix
  context, and hands failures to the durable outbox instead of swallowing
  them.
* ``delete_orphaned_media_refs`` uses the real ``object_storage.is_reference``
  API — the historical ``is_r2_reference`` attribute never existed, and its
  AttributeError used to be swallowed by the inner ``except Exception``,
  leaking orphaned R2 objects on exactly the path meant to prevent them.
* ``reap_stale_media_jobs`` cleans the quarantine object when a job goes
  terminal FAILED, and ``reconcile_abandoned_upload_sessions`` sweeps
  never-completed direct-upload sessions in a bounded, TTL-gated way.
"""
import logging
import types
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from services import media_processor, object_storage


def _fake_storage(**overrides):
    """A strict stand-in for the object_storage module.

    Deliberately has NO ``is_r2_reference`` attribute: any code touching it
    raises AttributeError, proving the fixed code paths cannot hit the old
    bug.
    """
    namespace = {
        "enabled": lambda: True,
        "is_reference": lambda ref: bool(ref and str(ref).startswith("uploads/r2/")),
        "delete_reference": lambda ref: None,
    }
    namespace.update(overrides)
    return types.SimpleNamespace(**namespace)


def _use_fake_storage(monkeypatch, tmp_path, **overrides):
    monkeypatch.chdir(tmp_path)
    fake = _fake_storage(**overrides)
    monkeypatch.setattr(media_processor, "object_storage", fake)
    return fake


# ---------------------------------------------------------------------------
# block_and_cleanup_quarantine
# ---------------------------------------------------------------------------

def test_quarantine_deleted_on_successful_publication(monkeypatch, tmp_path):
    """ALLOW path: the quarantine R2 object is deleted and True is returned."""
    deleted = []
    fake = _use_fake_storage(
        monkeypatch, tmp_path, delete_reference=lambda ref: deleted.append(ref)
    )
    key = f"uploads/r2/quarantine/7/{uuid.uuid4().hex}/source.mp4"
    assert media_processor.block_and_cleanup_quarantine(123, key) is True
    assert deleted == [key]
    # Must not touch the non-existent is_r2_reference attribute (would raise).
    assert not hasattr(fake, "is_r2_reference")


def test_quarantine_cleanup_failure_logs_and_enqueues_outbox(monkeypatch, tmp_path, caplog):
    """Failure is logged with the key prefix, outbox gets the retry, False returned."""
    enqueued = []

    def fake_enqueue(reference, source_table="compensation", source_id=None):
        enqueued.append((reference, source_table, source_id))

    _use_fake_storage(
        monkeypatch,
        tmp_path,
        delete_reference=lambda ref: (_ for _ in ()).throw(RuntimeError("R2 500")),
    )
    monkeypatch.setattr(
        "services.media_outbox.enqueue_delete", fake_enqueue
    )
    key = f"uploads/r2/quarantine/7/{uuid.uuid4().hex}/source.mp4"
    with caplog.at_level(logging.WARNING, logger="services.media_processor"):
        assert media_processor.block_and_cleanup_quarantine(123, key) is False
    assert any(key[:32] in rec.getMessage() for rec in caplog.records), \
        "failure must be logged with the object-key prefix as context"
    assert enqueued == [(key, "posts", 123)]


def test_quarantine_cleanup_no_key_is_noop(monkeypatch, tmp_path):
    calls = []
    _use_fake_storage(
        monkeypatch, tmp_path, delete_reference=lambda ref: calls.append(ref)
    )
    assert media_processor.block_and_cleanup_quarantine(123, None) is True
    assert calls == []


# ---------------------------------------------------------------------------
# delete_orphaned_media_refs (lease-loss / compensation paths)
# ---------------------------------------------------------------------------

def test_orphan_cleanup_uses_real_is_reference_api(monkeypatch, tmp_path):
    """No AttributeError path: R2 refs deleted, local files unlinked."""
    deleted = []
    fake = _use_fake_storage(
        monkeypatch, tmp_path, delete_reference=lambda ref: deleted.append(ref)
    )
    local = tmp_path / "perm" / "1_media.jpg"
    local.parent.mkdir(parents=True)
    local.write_bytes(b"x")
    r2_ref = f"uploads/r2/posts/7/9_media.mp4"

    failed = media_processor.delete_orphaned_media_refs(
        (r2_ref, str(local), None), context="unit_test"
    )
    assert failed == []
    assert deleted == [r2_ref]
    assert not local.exists()
    assert not hasattr(fake, "is_r2_reference")


def test_orphan_cleanup_records_failures_continues_and_enqueues(monkeypatch, tmp_path, caplog):
    enqueued = []

    def fake_enqueue(reference, source_table="compensation", source_id=None):
        enqueued.append((reference, source_table, source_id))

    def boom(ref):
        raise RuntimeError("network down")

    _use_fake_storage(monkeypatch, tmp_path, delete_reference=boom)
    monkeypatch.setattr("services.media_outbox.enqueue_delete", fake_enqueue)

    refs = [f"uploads/r2/posts/7/{uuid.uuid4().hex}_media.mp4" for _ in range(2)]
    with caplog.at_level(logging.WARNING, logger="services.media_processor"):
        failed = media_processor.delete_orphaned_media_refs(refs, context="unit_test")

    # Both attempted (no early abort), both recorded, both queued for retry.
    assert failed == refs
    assert len(enqueued) == 2
    assert all(src == "orphan_cleanup:unit_test" for _, src, _ in enqueued)
    logged = " ".join(rec.getMessage() for rec in caplog.records)
    assert refs[0][:32] in logged and refs[1][:32] in logged


def test_no_is_r2_reference_attribute_access_in_services():
    """Static guard: no services module may use the non-existent attribute."""
    services_dir = Path(media_processor.__file__).parent
    offenders = []
    for py in services_dir.glob("*.py"):
        text = py.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("''"):
                continue
            if ".is_r2_reference" in line:
                offenders.append(f"{py.name}:{lineno}")
    assert offenders == [], f"non-existent is_r2_reference attribute used: {offenders}"
    assert not hasattr(object_storage, "is_r2_reference")


# ---------------------------------------------------------------------------
# reap_stale_media_jobs — terminal FAILED cleans quarantine
# ---------------------------------------------------------------------------

def _stale_post_row(post_id=42, attempts=3, max_attempts=3):
    return {
        "post_id": post_id,
        "child_id": 7,
        "source_media_path": f"uploads/r2/quarantine/7/{uuid.uuid4().hex}/source.mp4",
        "is_reel": False,
        "is_story": False,
        "processing_status": "PROCESSING",
        "processing_started_at": None,
        "created_at": None,
        "processing_attempts": attempts,
        "max_processing_attempts": max_attempts,
    }


def test_reaper_cleans_quarantine_on_terminal_failure(monkeypatch):
    row = _stale_post_row()
    cleaned = []

    monkeypatch.setattr(media_processor, "fetch_all", lambda *a, **k: [row])
    monkeypatch.setattr(media_processor, "execute_count", lambda *a, **k: 1)
    monkeypatch.setattr(
        media_processor,
        "block_and_cleanup_quarantine",
        lambda post_id, key: cleaned.append((post_id, key)) or True,
    )
    res = media_processor.reap_stale_media_jobs(stale_seconds=300)
    assert res["ok"] is True
    assert cleaned == [(row["post_id"], row["source_media_path"])]
    assert res["failed"][0]["post_id"] == row["post_id"]
    assert res["failed"][0]["quarantine_cleaned"] is True


def test_reaper_skips_quarantine_cleanup_when_row_not_transitioned(monkeypatch):
    """If another worker already moved the row, the reaper must not delete."""
    row = _stale_post_row()
    cleaned = []

    monkeypatch.setattr(media_processor, "fetch_all", lambda *a, **k: [row])
    monkeypatch.setattr(media_processor, "execute_count", lambda *a, **k: 0)
    monkeypatch.setattr(
        media_processor,
        "block_and_cleanup_quarantine",
        lambda post_id, key: cleaned.append((post_id, key)) or True,
    )
    res = media_processor.reap_stale_media_jobs(stale_seconds=300)
    assert cleaned == []
    assert "quarantine_cleaned" not in res["failed"][0]


# ---------------------------------------------------------------------------
# reconcile_abandoned_upload_sessions — bounded, TTL-gated
# ---------------------------------------------------------------------------

def _abandoned_session_row():
    upload_id = str(uuid.uuid4())
    return {
        "upload_id": upload_id,
        "child_id": 7,
        "object_key": f"uploads/r2/quarantine/7/{upload_id}/source.mp4",
        "extension": "mp4",
    }


def test_reconcile_abandoned_upload_sessions(monkeypatch, tmp_path):
    row = _abandoned_session_row()
    deleted = []
    marked = []

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(media_processor, "fetch_all", lambda *a, **k: [row])
    monkeypatch.setattr(media_processor, "execute_count",
                        lambda sql, params: marked.append(params) or 1)
    fake = _fake_storage(delete_reference=lambda ref: deleted.append(ref))
    monkeypatch.setattr(media_processor, "object_storage", fake)

    res = media_processor.reconcile_abandoned_upload_sessions(stale_seconds=3600)
    assert res["ok"] is True
    assert res["checked"] == 1
    assert res["cleaned"] == [row["upload_id"]]
    assert res["failed"] == []
    assert deleted == [row["object_key"]]
    # Session terminal-marked exactly once, atomically (no double sweep).
    assert marked == [(row["upload_id"],)]


def test_reconcile_abandoned_upload_sessions_r2_failure_queues_outbox(monkeypatch, tmp_path):
    row = _abandoned_session_row()
    enqueued = []

    def fake_enqueue(reference, source_table="compensation", source_id=None):
        enqueued.append((reference, source_table, source_id))

    def boom(ref):
        raise RuntimeError("network down")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(media_processor, "fetch_all", lambda *a, **k: [row])
    monkeypatch.setattr(media_processor, "execute_count", lambda *a, **k: 1)
    monkeypatch.setattr(media_processor, "object_storage", _fake_storage(delete_reference=boom))
    monkeypatch.setattr("services.media_outbox.enqueue_delete", fake_enqueue)

    res = media_processor.reconcile_abandoned_upload_sessions(stale_seconds=3600)
    assert res["failed"][0]["upload_id"] == row["upload_id"]
    assert enqueued == [(row["object_key"], "abandoned_upload_session", row["upload_id"])]


def test_reconcile_uses_bounded_ttl_query():
    """The sweep must be TTL-gated and LIMIT-bounded (no unbounded scans)."""
    source = Path(media_processor.__file__).read_text(encoding="utf-8")
    fn = source.split("def reconcile_abandoned_upload_sessions")[1].split("\ndef ")[0]
    assert "LIMIT 50" in fn
    assert "expires_at < %s" in fn
    assert "status IN ('PENDING', 'EXPIRED')" in fn


# ---------------------------------------------------------------------------
# upload_file audio-strip contract: default strips, explicit opt-out skips
# ---------------------------------------------------------------------------

def test_upload_file_skip_audio_strip_flag(tmp_path, monkeypatch):
    from services import media_sanitizer

    class FakeS3:
        def __init__(self):
            self.uploads = []

        def upload_file(self, *args, **kwargs):
            self.uploads.append((args, kwargs))

    path = tmp_path / "clip.mp4"
    path.write_bytes(b"fake-video")
    calls = []
    s3 = FakeS3()
    monkeypatch.setattr(
        media_sanitizer, "strip_video_audio_in_place", lambda p: calls.append(p) or True
    )
    monkeypatch.setattr(object_storage, "_client", lambda: s3)
    monkeypatch.setenv("R2_BUCKET", "test-bucket")

    # Default: fail-closed strip still applies (all non-derivatives callers).
    object_storage.upload_file(str(path), "posts/1/a.mp4")
    assert calls == [str(path)]

    # Opt-out: derivatives path already stripped; no redundant second pass.
    object_storage.upload_file(str(path), "posts/1/b.mp4", skip_audio_strip=True)
    assert calls == [str(path)]
    assert len(s3.uploads) == 2
