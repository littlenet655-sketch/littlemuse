"""Reusable moderation-signal cache for exact content.

This cache stores model signals, never a final ALLOW/BLOCK decision. The current
child safety policy is always re-applied after a cache hit.

The cache is intentionally versioned. Bump LITTLENET_MODERATION_CACHE_VERSION
whenever deployed moderation models or preprocessing materially change.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from database.connection import execute, fetch_one


DEFAULT_CACHE_VERSION = "2026-09-20-v1"


def cache_version() -> str:
    return (os.getenv("LITTLENET_MODERATION_CACHE_VERSION") or DEFAULT_CACHE_VERSION).strip()[:80]


def _ttl_days() -> int:
    try:
        value = int(os.getenv("LITTLENET_MODERATION_CACHE_TTL_DAYS", "30"))
    except (TypeError, ValueError):
        value = 30
    return max(1, min(value, 90))


def file_fingerprint(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def text_fingerprint(text: str) -> str:
    normalized = (text or "").strip().encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


def get_cached_signals(content_type: str, fingerprint: str) -> dict[str, Any] | None:
    row = fetch_one(
        """SELECT signals
             FROM moderation_signal_cache
            WHERE content_type=%s
              AND content_sha256=%s
              AND cache_version=%s
              AND created_at >= NOW() - (%s || ' days')::INTERVAL
            LIMIT 1""",
        (str(content_type).upper(), fingerprint, cache_version(), str(_ttl_days())),
    )
    if not row:
        return None
    raw = row.get("signals")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return None
    if not isinstance(raw, dict) or not raw:
        return None

    # Never reuse incomplete/failed evidence.
    if raw.get("total_safety_failure") or raw.get("partial_safety_failure"):
        return None

    execute(
        """UPDATE moderation_signal_cache
              SET last_used_at=NOW(), hit_count=hit_count+1
            WHERE content_type=%s AND content_sha256=%s AND cache_version=%s""",
        (str(content_type).upper(), fingerprint, cache_version()),
    )
    cached = dict(raw)
    cached.setdefault("cache", {})
    if isinstance(cached["cache"], dict):
        cached["cache"].update({"hit": True, "version": cache_version()})
    return cached


def store_cached_signals(content_type: str, fingerprint: str, signals: dict[str, Any]) -> bool:
    if not isinstance(signals, dict) or not signals:
        return False
    if signals.get("total_safety_failure") or signals.get("partial_safety_failure"):
        return False

    payload = dict(signals)
    payload.pop("cache", None)
    execute(
        """INSERT INTO moderation_signal_cache
             (content_type, content_sha256, cache_version, signals, created_at, last_used_at, hit_count)
           VALUES(%s,%s,%s,%s::jsonb,NOW(),NOW(),0)
           ON CONFLICT(content_type, content_sha256, cache_version)
           DO UPDATE SET signals=EXCLUDED.signals,
                         last_used_at=NOW()""",
        (
            str(content_type).upper(),
            fingerprint,
            cache_version(),
            json.dumps(payload, separators=(",", ":"), default=str),
        ),
    )
    return True


def cached_or_none_for_file(content_type: str, path: str | Path) -> tuple[str, dict[str, Any] | None]:
    fingerprint = file_fingerprint(path)
    return fingerprint, get_cached_signals(content_type, fingerprint)


def cached_or_none_for_text(text: str) -> tuple[str, dict[str, Any] | None]:
    fingerprint = text_fingerprint(text)
    return fingerprint, get_cached_signals("TEXT", fingerprint)
