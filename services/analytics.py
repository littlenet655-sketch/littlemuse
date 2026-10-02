"""Server-side product analytics via PostHog.

Backend-only by design: the PostHog project API key never leaves the server
(repo rule: the only expected Expo env var is EXPO_PUBLIC_API_BASE_URL).
All capture paths are env-gated and fail-silent so analytics can never break
a user flow.
"""
import logging
import os

log = logging.getLogger(__name__)

_client = None
_enabled = False


def init_analytics():
    """Initialize once at app startup. Safe to call repeatedly."""
    global _client, _enabled
    api_key = os.getenv("POSTHOG_API_KEY", "").strip()
    if not api_key:
        return False
    try:
        from posthog import Posthog

        host = os.getenv("POSTHOG_HOST", "https://us.i.posthog.com").strip() or "https://us.i.posthog.com"
        _client = Posthog(project_api_key=api_key, host=host, debug=False)
        _enabled = True
        log.info("analytics: PostHog enabled (host=%s)", host)
        return True
    except Exception as exc:  # pragma: no cover - init path
        log.warning("analytics: PostHog init failed: %s", exc)
        return False


def is_enabled():
    return _enabled and _client is not None


def capture(distinct_id, event, properties=None):
    """Capture a server-side event. Never raises."""
    if not is_enabled():
        return
    try:
        _client.capture(str(distinct_id), event, properties or {})
    except Exception as exc:
        log.debug("analytics: capture failed for %s: %s", event, exc)


def flush():
    if is_enabled():
        try:
            _client.flush()
        except Exception:
            pass
