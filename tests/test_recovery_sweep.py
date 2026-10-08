"""run_recovery_sweep must invoke all three recovery passes independently."""
from __future__ import annotations

import pytest

import services.chat_media as chat_media
import services.media_processor as media_processor
from services.recovery import run_recovery_sweep


def _boom(*args, **kwargs):
    raise RuntimeError("db down")


@pytest.fixture
def stubs(monkeypatch):
    calls = []
    monkeypatch.setattr(
        media_processor,
        "reap_stale_media_jobs",
        lambda stale_seconds=300: calls.append(("stale_media_jobs", stale_seconds))
        or {"ok": True, "reaped": 2},
    )
    monkeypatch.setattr(
        media_processor,
        "reconcile_abandoned_upload_sessions",
        lambda: calls.append(("abandoned_uploads",)) or {"ok": True, "cancelled": 1},
    )
    monkeypatch.setattr(
        chat_media,
        "reconcile_abandoned_chat_upload_sessions",
        lambda: calls.append(("abandoned_chat_uploads",)) or {"ok": True, "deleted": 3},
    )
    return calls


def test_sweep_invokes_all_three_recovery_passes(stubs):
    res = run_recovery_sweep()

    assert [name for name, *_ in stubs] == [
        "stale_media_jobs",
        "abandoned_uploads",
        "abandoned_chat_uploads",
    ]
    assert stubs[0][1] == 300  # default stale-job horizon matches the manual endpoint
    assert res["stale_media_jobs"]["ok"] is True
    assert res["abandoned_uploads"]["ok"] is True
    assert res["abandoned_chat_uploads"]["ok"] is True


def test_one_failing_pass_does_not_starve_the_others(monkeypatch, stubs):
    monkeypatch.setattr(media_processor, "reap_stale_media_jobs", _boom)

    res = run_recovery_sweep()

    assert res["stale_media_jobs"]["ok"] is False
    assert "RuntimeError" in res["stale_media_jobs"]["error"]
    assert res["abandoned_uploads"]["ok"] is True
    assert res["abandoned_chat_uploads"]["ok"] is True


def test_stale_post_without_quarantine_source_finishes_failed_instead_of_hanging(monkeypatch):
    orphan = {
        "post_id": 501,
        "child_id": 7,
        "source_media_path": None,
        "processing_status": "UPLOADED",
        "processing_attempts": 0,
        "max_processing_attempts": 3,
    }
    statements = []
    monkeypatch.setattr(media_processor, "fetch_all", lambda *_a, **_k: [orphan])
    monkeypatch.setattr(
        media_processor, "execute_count",
        lambda sql, params: statements.append((sql, params)) or 1,
    )
    monkeypatch.setattr(
        media_processor, "claim_media_job_lease",
        lambda *_a, **_k: pytest.fail("orphan must never be dispatched"),
    )

    result = media_processor.reap_stale_media_jobs(stale_seconds=300)

    assert result["redriven"] == []
    assert result["failed"] == [{"post_id": 501, "error": "missing_quarantine_source"}]
    assert len(statements) == 1
    sql, params = statements[0]
    assert "processing_status='FAILED'" in sql
    assert "source_media_path IS NULL" in sql
    assert "processing_lease_token IS NULL" in sql
    assert params[0] == 501


def test_stale_orphan_race_does_not_overwrite_a_recovered_worker(monkeypatch):
    orphan = {
        "post_id": 502,
        "child_id": 7,
        "source_media_path": "",
        "processing_status": "PROCESSING",
        "processing_attempts": 1,
        "max_processing_attempts": 3,
    }
    monkeypatch.setattr(media_processor, "fetch_all", lambda *_a, **_k: [orphan])
    # The guarded UPDATE no longer matches if a concurrent worker recovered it.
    monkeypatch.setattr(media_processor, "execute_count", lambda *_a, **_k: 0)

    result = media_processor.reap_stale_media_jobs(stale_seconds=300)

    assert result["count"] == 0
    assert result["redriven"] == []
    assert result["failed"] == []
