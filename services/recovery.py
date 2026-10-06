"""Scheduled recovery sweep: stale media jobs + abandoned upload sessions.

Runs every 15 minutes from Modal (``modal_web.recovery_sweep``) and remains
available manually via ``POST /api/mobile/v2/maintenance/reap-stale-jobs``.

Without a schedule, stuck PROCESSING media jobs and abandoned direct-to-R2
quarantine uploads accumulate until someone remembers to hit the manual
endpoint. Each recovery step is independent: a failure in one is recorded in
the result dict and the others still run, so one broken sweep never starves
the rest.
"""
from __future__ import annotations

from typing import Any


def run_recovery_sweep(stale_job_seconds: int = 300) -> dict[str, Any]:
    """Run all three recovery passes; never let one failure block the others."""
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
