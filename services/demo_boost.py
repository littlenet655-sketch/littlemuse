"""Temporary demo-day acceleration for LittleNet.

Demo Boost never bypasses moderation or authorization. It only changes the
autoscaling idle window of the already-deployed Modal AI functions, capped at
one container, then wakes those functions once. min_containers stays at zero so
idle compute can still return to zero automatically.
"""
from __future__ import annotations

import base64
import os
import threading
import time
from datetime import datetime, timezone

import requests

from database.connection import execute, fetch_one

START_MINUTES = {15, 30, 60}
EXTEND_MINUTES = {5, 15, 30}
DEFAULT_SCALEDOWN_SECONDS = 30

# Valid 1x1 JPEG used only to wake the CPU image/text moderation function.
_WARMUP_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////"
    "2wBDAf//////////////////////////////////////////////////////////////////////////////////////"
    "wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAX/xAAUEAEAAAAAAAAAAAAAAAAAAAAA"
    "/9oADAMBAAIQAxAAAAH/AP/EABQQAQAAAAAAAAAAAAAAAAAAABD/2gAIAQEAAQUCf//EABQRAQAAAAAAAAAA"
    "AAAAAAAAABD/2gAIAQMBAT8Bf//EABQRAQAAAAAAAAAAAAAAAAAAABD/2gAIAQIBAT8Bf//EABQQAQAAAAAA"
    "AAAAAAAAAAAAABD/2gAIAQEABj8Cf//Z"
)


def _row() -> dict:
    row = fetch_one(
        """SELECT state_id,status,activated_by,started_at,expires_at,last_error,updated_at,
                  CASE WHEN expires_at IS NOT NULL
                       THEN GREATEST(0, EXTRACT(EPOCH FROM (expires_at-NOW())))::int
                       ELSE 0 END AS remaining_seconds
           FROM demo_boost_state WHERE state_id=1"""
    )
    return dict(row or {})


def _public(row: dict | None = None) -> dict:
    row = row or {}
    remaining = max(0, int(row.get("remaining_seconds") or 0))
    status = str(row.get("status") or "OFF").upper()
    active = status in {"WARMING", "READY"} and remaining > 0
    if not active:
        status = "OFF"
        remaining = 0
    return {
        "active": active,
        "status": status,
        "remaining_seconds": remaining,
        "expires_at": row.get("expires_at"),
        "started_at": row.get("started_at"),
        "last_error": row.get("last_error") if status == "WARMING" else None,
    }


def _modal_functions():
    import modal

    app_name = os.getenv("LITTLENET_AI_MODAL_APP", "littlemuse-ai").strip() or "littlemuse-ai"
    gpu_name = os.getenv("LITTLENET_AI_WEB_FUNCTION", "ai_web").strip() or "ai_web"
    cpu_name = os.getenv("LITTLENET_AI_IMAGE_CPU_FUNCTION", "moderate_image_upload_cpu").strip() or "moderate_image_upload_cpu"
    return (
        modal.Function.from_name(app_name, gpu_name),
        modal.Function.from_name(app_name, cpu_name),
    )


def _set_autoscaler(seconds: int) -> None:
    gpu, cpu = _modal_functions()
    bounded = max(DEFAULT_SCALEDOWN_SECONDS, min(int(seconds), 60 * 65))
    # Never make Demo Boost an uncapped cost switch.
    gpu.update_autoscaler(min_containers=0, max_containers=1, scaledown_window=bounded)
    cpu.update_autoscaler(min_containers=0, max_containers=1, scaledown_window=bounded)


def _configured_scaledown(env_name: str) -> int:
    """Restore the deployed idle window, not a hardcoded 30s."""
    raw = (os.getenv(env_name) or str(DEFAULT_SCALEDOWN_SECONDS)).strip()
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = DEFAULT_SCALEDOWN_SECONDS
    return max(1, min(value, 60 * 65))


def _restore_autoscaler() -> bool:
    """Restore each function's configured idle window. Returns False on Modal error.

    Expiry restoration is lazy on the existing status() poll path (and stop()).
    There is no permanent scheduled GPU worker just to restore the window.
    Callers must keep the boost row non-OFF on failure so the next status poll
    retries; otherwise a long T4/CPU idle window would stay attached until
    the next deploy.
    """
    try:
        gpu, cpu = _modal_functions()
        gpu.update_autoscaler(
            min_containers=0,
            max_containers=1,
            scaledown_window=_configured_scaledown("MODAL_AI_GPU_SCALEDOWN_WINDOW"),
        )
        cpu.update_autoscaler(
            min_containers=0,
            max_containers=1,
            scaledown_window=_configured_scaledown("MODAL_AI_IMAGE_CPU_SCALEDOWN_WINDOW"),
        )
        return True
    except Exception:
        return False


def _mark_ready(expected_expiry) -> None:
    execute(
        """UPDATE demo_boost_state
           SET status='READY',last_error=NULL,updated_at=NOW()
           WHERE state_id=1 AND status='WARMING' AND expires_at=%s AND expires_at>NOW()""",
        (expected_expiry,),
    )


def _mark_warm_error(expected_expiry, exc: Exception) -> None:
    execute(
        """UPDATE demo_boost_state
           SET last_error=%s,updated_at=NOW()
           WHERE state_id=1 AND status='WARMING' AND expires_at=%s AND expires_at>NOW()""",
        (f"{type(exc).__name__}: {str(exc)[:240]}", expected_expiry),
    )


def _warm_async(expected_expiry) -> None:
    """Wake CPU + GPU pools without blocking the Admin button request."""
    try:
        _gpu, cpu = _modal_functions()
        # Spawn returns immediately while still creating/warming the CPU worker.
        cpu.spawn(_WARMUP_JPEG, "demo-warmup.jpg", "LittleNet demo warmup", True, True)

        ai_url = str(os.getenv("AI_SERVICE_URL") or "").rstrip("/")
        secret = str(os.getenv("AI_SHARED_SECRET") or "")
        if not ai_url or not secret:
            raise RuntimeError("demo_boost_ai_service_not_configured")
        response = requests.get(
            f"{ai_url}/warmup",
            headers={"X-LittleNet-AI-Key": secret},
            timeout=120,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("ok") is not True:
            raise RuntimeError("demo_boost_gpu_warmup_failed")
        _mark_ready(expected_expiry)
    except Exception as exc:
        _mark_warm_error(expected_expiry, exc)


def _start_warm_thread(expected_expiry, delay_seconds: float | None = None) -> None:
    if delay_seconds is None:
        row = _row()
        delay_seconds = max(0.1, float((row or {}).get("remaining_seconds") or 0.1))
    _schedule_auto_restore(delay_seconds)
    thread = threading.Thread(target=_warm_async, args=(expected_expiry,), daemon=True, name="littlenet-demo-warm")
    thread.start()


def status() -> dict:
    row = _row()
    public = _public(row)
    if public["active"]:
        return public

    # Expired boosts must not leave a long autoscaler override attached to
    # future requests. Restore defaults lazily the first time any app screen
    # polls status after expiry.
    if str(row.get("status") or "OFF").upper() != "OFF":
        # Restore first; only mark OFF once Modal confirmed, so a failed restore
        # is retried by the next poll instead of being forgotten.
        if _restore_autoscaler():
            execute(
                """UPDATE demo_boost_state
                   SET status='OFF',activated_by=NULL,last_error=NULL,updated_at=NOW()
                   WHERE state_id=1"""
            )
    return _public(_row())


def activate(admin_id: int, minutes: int) -> dict:
    minutes = int(minutes)
    if minutes not in START_MINUTES:
        raise ValueError("invalid_demo_boost_minutes")
    seconds = minutes * 60
    _set_autoscaler(seconds)
    row = fetch_one(
        """UPDATE demo_boost_state
           SET status='WARMING',activated_by=%s,started_at=NOW(),
               expires_at=NOW()+(%s * INTERVAL '1 second'),
               last_error=NULL,updated_at=NOW()
           WHERE state_id=1
           RETURNING expires_at""",
        (admin_id, seconds),
    )
    expected_expiry = row["expires_at"]
    _start_warm_thread(expected_expiry, delay_seconds=seconds)
    return status()


def extend(admin_id: int, minutes: int) -> dict:
    minutes = int(minutes)
    if minutes not in EXTEND_MINUTES:
        raise ValueError("invalid_demo_boost_extension")
    current = status()
    if not current.get("active"):
        raise ValueError("demo_boost_not_active")
    row = fetch_one(
        """UPDATE demo_boost_state
           SET activated_by=%s,
               expires_at=GREATEST(COALESCE(expires_at,NOW()),NOW())+(%s * INTERVAL '1 minute'),
               status=CASE WHEN status='OFF' THEN 'WARMING' ELSE status END,
               last_error=NULL,updated_at=NOW()
           WHERE state_id=1
           RETURNING expires_at,
             GREATEST(0, EXTRACT(EPOCH FROM (expires_at-NOW())))::int AS remaining_seconds""",
        (admin_id, minutes),
    )
    remaining = max(DEFAULT_SCALEDOWN_SECONDS, int(row.get("remaining_seconds") or 0))
    _set_autoscaler(remaining)
    if _public({**row, "status": "WARMING"})["remaining_seconds"] > 0:
        _start_warm_thread(row["expires_at"], delay_seconds=remaining)
    return status()


def stop() -> dict:
    # Expire immediately (boost is inactive for every client); status() performs
    # the autoscaler restore and flips the row to OFF, retrying on later polls
    # if Modal is temporarily unreachable.
    execute(
        """UPDATE demo_boost_state
           SET expires_at=NOW(),last_error=NULL,updated_at=NOW()
           WHERE state_id=1"""
    )
    return status()


_TIMER_LOCK = threading.Lock()
_TIMER_HANDLE = None

def _schedule_auto_restore(delay_seconds):
    global _TIMER_HANDLE
    with _TIMER_LOCK:
        if _TIMER_HANDLE is not None:
            try:
                _TIMER_HANDLE.cancel()
            except Exception:
                pass
            _TIMER_HANDLE = None
        delay = max(0.1, float(delay_seconds))
        timer = threading.Timer(delay, _auto_restore_worker)
        timer.daemon = True
        timer.name = 'littlenet-demo-boost-auto-restore'
        _TIMER_HANDLE = timer
        timer.start()

def _auto_restore_worker():
    global _TIMER_HANDLE
    with _TIMER_LOCK:
        _TIMER_HANDLE = None
    try:
        auto_restore_if_expired()
    except Exception:
        pass

def auto_restore_if_expired(max_retries=3, backoff_base=0.5):
    row = _row()
    if not row:
        return True
    status_str = str(row.get('status') or 'OFF').upper()
    if status_str == 'OFF':
        return True
    remaining = max(0, int(row.get('remaining_seconds') or 0))
    if remaining > 0:
        _schedule_auto_restore(remaining)
        return False
    restored = False
    for attempt in range(max(1, max_retries)):
        if _restore_autoscaler():
            restored = True
            break
        if attempt < max_retries - 1:
            time.sleep(backoff_base * (2 ** attempt))
    if restored:
        execute('UPDATE demo_boost_state SET status=\'OFF\',activated_by=NULL,last_error=NULL,updated_at=NOW() WHERE state_id=1')
        return True
    return False


def reconcile_demo_boost_on_startup() -> bool:
    """Process-independent recovery hook called upon server startup / cold container boot.
    
    Checks persisted PostgreSQL state in demo_boost_state. If a boost was left in
    WARMING or READY while the container was terminated, restores Modal autoscaler
    and transitions the DB row cleanly to OFF.
    """
    try:
        return auto_restore_if_expired(max_retries=2)
    except Exception:
        return False
