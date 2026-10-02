"""Client for the optional split LittleNet AI inference service.

The web app can run with only the lightweight dependencies and delegate heavy
inference (YOLO/NSFW/semantic ranking) to the protected AI service.
Every network request has a centrally bounded timeout and fails closed in its
caller when the AI service is unavailable.
"""
import json
import math
import os
import time
from pathlib import Path

import requests


def enabled() -> bool:
    return bool(os.getenv("AI_SERVICE_URL", "").strip()) and os.getenv("LITTLENET_AI_SERVER") != "1"


def _base() -> str:
    return os.environ["AI_SERVICE_URL"].rstrip("/")


def _headers():
    secret = os.getenv("AI_SHARED_SECRET", "").strip()
    return {"X-LittleNet-AI-Key": secret} if secret else {}


def _timeout() -> int:
    """Return a finite AI timeout; never allow an unbounded remote call."""
    try:
        configured = int(os.getenv("AI_REQUEST_TIMEOUT", "120"))
    except (TypeError, ValueError):
        configured = 120
    return max(10, min(configured, 300))


def _health_timeout() -> int:
    """Health probes must tolerate a Modal cold start but remain bounded."""
    try:
        configured = int(os.getenv("AI_HEALTH_TIMEOUT", "30"))
    except (TypeError, ValueError):
        configured = 30
    return max(10, min(configured, 90))


def _flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _json_object(response, name: str) -> dict:
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError(f"{name}_invalid_json")
    return data


def _moderation_signals(response) -> dict:
    data = _json_object(response, "moderation")
    if data.get("ok") is False:
        raise ValueError(str(data.get("error") or "moderation_failed"))
    signals = data.get("signals")
    if not isinstance(signals, dict) or not signals:
        raise ValueError("moderation_signals_missing")
    return signals


def moderate_text(text: str) -> dict:
    r = requests.post(  # nosec B113 - timeout is explicitly bounded by _timeout()
        _base() + "/ai/moderate",
        data={"content_type": "TEXT", "text": text or ""},
        headers=_headers(), timeout=_timeout(),
    )
    r.raise_for_status()
    return _moderation_signals(r)


def moderate_file(content_type: str, path: str) -> dict:
    with open(path, "rb") as fh:
        r = requests.post(  # nosec B113 - timeout is explicitly bounded by _timeout()
            _base() + "/ai/moderate",
            data={"content_type": content_type.upper()},
            files={"file": (Path(path).name, fh)},
            headers=_headers(), timeout=_timeout(),
        )
    r.raise_for_status()
    return _moderation_signals(r)


def moderate_upload(content_type: str, path: str, text: str = "") -> dict:
    """Moderate upload text + media in one protected AI request.

    This keeps one upload on one GPU container wake instead of making separate
    caption/media round-trips. The AI service still returns independent signals
    so the web worker can apply policy normally.
    """
    with open(path, "rb") as fh:
        r = requests.post(  # nosec B113 - timeout is explicitly bounded by _timeout()
            _base() + "/ai/moderate-upload",
            data={
                "content_type": content_type.upper(),
                "text": (text or "")[:4000],
            },
            files={"file": (Path(path).name, fh)},
            headers=_headers(),
            timeout=_timeout(),
        )
    r.raise_for_status()
    data = _json_object(r, "moderate_upload")
    if data.get("ok") is not True:
        raise ValueError(str(data.get("error") or "moderate_upload_failed"))
    text_signals = data.get("text_signals")
    media_signals = data.get("media_signals")
    if not isinstance(text_signals, dict):
        text_signals = {}
    if not isinstance(media_signals, dict) or not media_signals:
        raise ValueError("moderate_upload_media_signals_missing")
    return {
        "text_signals": text_signals,
        "media_signals": media_signals,
    }


def health() -> dict:
    """Cheap readiness check by default; deep probe only when explicitly enabled.

    A normal /readyz request must never wake the T4 just to prove that the AI URL
    is configured. Set AI_DEEP_HEALTH=1 only for an intentional release/debug
    probe, or configure AI_HEALTH_URL to a future CPU-only health endpoint.
    """
    configured = bool(os.getenv("AI_SERVICE_URL", "").strip())
    health_url = os.getenv("AI_HEALTH_URL", "").strip()
    if not configured:
        return {"ok": False, "error": "ai_service_url_missing", "mode": "passive"}

    if not health_url and not _flag("AI_DEEP_HEALTH", False):
        return {
            "ok": True,
            "service": "littlenet-ai",
            "mode": "passive_configured",
            "gpu_woken": False,
        }

    attempts = 3
    try:
        attempts = max(1, min(int(os.getenv("AI_HEALTH_ATTEMPTS", "3")), 5))
    except (TypeError, ValueError):
        attempts = 3
    timeout = _health_timeout()
    last_error = "ai_health_unavailable"
    url = health_url or (_base() + "/healthz")
    for attempt in range(1, attempts + 1):
        try:
            r = requests.get(  # nosec B113 - timeout is explicitly bounded above
                url, headers=_headers(), timeout=timeout
            )
            r.raise_for_status()
            data = _json_object(r, "health")
            if data.get("ok") is True:
                data.setdefault("mode", "deep")
                return data
            last_error = str(data.get("error") or data.get("status") or "ai_not_ready")
        except (requests.RequestException, ValueError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        if attempt < attempts:
            time.sleep(min(2 * attempt, 4))
    return {
        "ok": False,
        "error": "ai_health_unavailable",
        "detail": last_error[:300],
        "attempts": attempts,
        "timeout_seconds": timeout,
        "mode": "deep",
    }


def rank_texts(profile_text: str, items: list[dict]) -> list[dict]:
    """Remote semantic ranking is opt-in because it otherwise wakes the T4 on feeds.

    Returning [] is intentional: the caller already has a deterministic ranking
    fallback for safe/allowed candidate posts.
    """
    if not _flag("AI_ENABLE_REMOTE_RANKING", False):
        return []
    payload={
        "profile_text": (profile_text or "")[:500],
        "items": [{"id": int(x["id"]), "text": str(x.get("text", ""))[:500]} for x in items[:60]],
    }
    r = requests.post(  # nosec B113 - timeout is explicitly bounded by _timeout()
        _base()+"/ai/rank", json=payload, headers=_headers(), timeout=_timeout()
    )
    r.raise_for_status()
    data=_json_object(r,"rank")
    rows=data.get("items",[])
    return rows if isinstance(rows,list) else []
