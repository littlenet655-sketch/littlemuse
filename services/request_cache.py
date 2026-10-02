"""Per-request memoization for read-only policy values.

Feed/home loops re-derive per-viewer policy (surface state, age, categories,
feature flags, relationship checks) once per media item, producing hundreds of
redundant sequential DB round trips per page. Within a single HTTP request
these values do not change, so they are cached on ``flask.g`` for the request
only.

Fail-closed semantics are preserved: whatever the underlying function returns
(including a denial) is what every caller inside the same request observes.
Outside a request context the maker runs uncached, exactly as before.
"""
from __future__ import annotations

from typing import Any, Callable, Hashable


def memo(key: Hashable, maker: Callable[[], Any]) -> Any:
    """Return the cached value for *key*, computing it once per request.

    Cache/context setup may fall back, but a failing maker is never executed a
    second time implicitly. That avoids duplicate DB/network work and preserves
    the original policy failure.
    """
    try:
        from flask import g, has_request_context
    except ImportError:  # pragma: no cover - flask is always present in app
        return maker()
    try:
        in_request = has_request_context()
        cache = getattr(g, "_littlenet_req_memo", None) if in_request else None
        if in_request and cache is None:
            cache = {}
            g._littlenet_req_memo = cache
    except Exception:
        return maker()
    if not in_request:
        return maker()
    if key not in cache:
        cache[key] = maker()
    return cache[key]
