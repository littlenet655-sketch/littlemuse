"""Media-worker recovery must not overwrite a newer, completed lease.

Covers stale-snapshot races without requiring production SQL mutations.
"""
from unittest.mock import Mock
import pytest
from services import media_processor as mp


def test_exhausted_sweep_preserves_concurrently_recovered_post(monkeypatch):
    stale = {
        "post_id": 39, "child_id": 2, "source_media_path": "uploads/r2/quarantine/39.jpg",
        "processing_status": "PROCESSING", "processing_started_at": None,
        "created_at": None, "processing_attempts": 3, "max_processing_attempts": 3,
    }
    statements = []
    monkeypatch.setattr(mp, "fetch_all", lambda *_a, **_kw: [stale])
    # Another worker won the lease between SELECT and UPDATE: no transition.
    monkeypatch.setattr(mp, "execute_count", lambda sql, params: statements.append((sql, params)) or 0)
    cleanup = Mock(side_effect=AssertionError("must not purge a live quarantine"))
    monkeypatch.setattr(mp, "block_and_cleanup_quarantine", cleanup)
    result = mp.reap_stale_media_jobs()
    assert result["failed"] == []
    assert result["redriven"] == []
    cleanup.assert_not_called()
    query, params = statements[0]
    assert "processing_attempts >= max_processing_attempts" in query
    assert "processing_lease_token IS NULL OR processing_lease_expires_at < NOW()" in query
    assert "processing_started_at < %s" in query
    assert params[0] == 39 and len(params) == 3


def test_redrive_dispatch_failure_only_releases_the_owning_lease(monkeypatch):
    monkeypatch.setattr(mp, "claim_media_job_lease", lambda *_a, **_kw: (
        True, "my-current-lease", {"post_id": 100, "child_id": 9,
                                  "is_reel": False, "is_story": False,
                                  "source_media_path": "uploads/r2/q/100.jpg"},
    ))
    monkeypatch.setattr("services.job_queue.enqueue_media_job",
                        lambda *_a, **_kw: (_ for _ in ()).throw(RuntimeError("queue unavailable")))
    updates = []
    monkeypatch.setattr(mp, "execute", lambda sql, params, **_kw: updates.append((sql, params)))
    result = mp.redrive_media_job(100)
    assert result["error"] == "job_dispatch_failed"
    sql, params = updates[0]
    assert "processing_status='UPLOADED'" in sql
    assert "processing_status='PROCESSING'" in sql
    assert "processing_lease_token=%s" in sql
    assert params[-2:] == (100, "my-current-lease")


def test_stale_reaper_dispatch_failure_only_releases_the_owning_lease(monkeypatch):
    monkeypatch.setattr(mp, "fetch_all", lambda *_a, **_kw: [{
        "post_id": 200, "child_id": 9, "source_media_path": "uploads/r2/q/200.jpg",
        "processing_status": "UPLOADED", "processing_attempts": 0,
        "max_processing_attempts": 3, "is_reel": False, "is_story": False,
    }])
    monkeypatch.setattr(mp, "claim_media_job_lease", lambda *_a, **_kw: (
        True, "sweep-lease", {"processing_attempts": 1},
    ))
    monkeypatch.setattr("services.job_queue.enqueue_media_job",
                        lambda *_a, **_kw: (_ for _ in ()).throw(RuntimeError("network unavailable")))
    updates = []
    monkeypatch.setattr(mp, "execute", lambda sql, params, **_kw: updates.append((sql, params)))
    result = mp.reap_stale_media_jobs()
    assert result["failed"][0]["post_id"] == 200
    sql, params = updates[0]
    assert "processing_lease_token=%s" in sql
    assert "processing_status='PROCESSING'" in sql
    assert params[-2:] == (200, "sweep-lease")


def test_redrive_missing_source_finishes_without_sticking_in_processing(monkeypatch):
    monkeypatch.setattr(mp, "claim_media_job_lease", lambda *_a, **_kw: (
        True, "missing-source-lease", {"post_id": 300, "child_id": 9,
                                       "source_media_path": None},
    ))
    writes = []
    monkeypatch.setattr(mp, "execute_count", lambda sql, params: writes.append((sql, params)) or 1)
    result = mp.redrive_media_job(300)
    assert result["error"] == "missing_source_media_path"
    assert len(writes) == 1
    assert "processing_status='FAILED'" in writes[0][0]
    assert "processing_lease_token=%s" in writes[0][0]
    assert writes[0][1] == (300, "missing-source-lease")


def test_exhausted_claim_refreshes_state_after_failed_transition(monkeypatch):
    rows = iter([
        {"post_id": 400, "processing_status": "UPLOADED", "processing_attempts": 3,
         "max_processing_attempts": 3, "processing_lease_token": None},
        {"post_id": 400, "processing_status": "PROCESSING", "processing_attempts": 4,
         "max_processing_attempts": 3, "processing_lease_token": "other-lease"},
    ])
    monkeypatch.setattr(mp, "fetch_one", lambda *_a, **_kw: next(rows))
    writes = []
    monkeypatch.setattr(mp, "execute_count", lambda sql, params: writes.append((sql, params)) or 0)
    acquired, token, state = mp.claim_media_job_lease(400)
    assert acquired is False and token is None
    assert state["processing_status"] == "PROCESSING"
    assert state["processing_lease_token"] == "other-lease"
    assert "processing_lease_token IS NULL" in writes[0][0]
