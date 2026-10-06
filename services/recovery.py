"""Scheduled recovery sweep for stale media and abandoned upload sessions.

Runs from Modal every 15 minutes. Each cleanup pass is isolated so one failing
subsystem cannot prevent the remaining recovery work from running.
"""
from __future__ import annotations

from typing import Any


def run_recovery_sweep(stale_job_seconds: int = 300) -> dict[str, Any]:
    results: dict[str, Any] = {}

    try:
        from services.media_processor import reap_stale_media_jobs
        results["stale_media_jobs"] = reap_stale_media_jobs(stale_seconds=stale_job_seconds)
    except Exception as exc:
        results["stale_media_jobs"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    try:
        from services.media_processor import reconcile_abandoned_upload_sessions
        results["abandoned_uploads"] = reconcile_abandoned_upload_sessions()
    except Exception as exc:
        results["abandoned_uploads"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    try:
        from services.chat_media import reconcile_abandoned_chat_upload_sessions
        results["abandoned_chat_uploads"] = reconcile_abandoned_chat_upload_sessions()
    except Exception as exc:
        results["abandoned_chat_uploads"] = {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }

    return results
