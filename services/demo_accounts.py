"""Server-authoritative demo/testing account exceptions.

The exception is deliberately narrow: a flagged CHILD bypasses screen-time and
quiet-hour/app-off timing gates so a college demo cannot lock itself out.
Moderation, relationship checks, parent feature controls, authentication and
all other safety/access-control rules remain unchanged.
"""
from __future__ import annotations

from database.connection import fetch_one
from services.request_cache import memo as _req_memo


def is_demo_unlimited(child_id: int) -> bool:
    return bool(
        _req_memo(
            ("demo_unlimited", int(child_id)),
            lambda: _is_demo_unlimited_uncached(int(child_id)),
        )
    )


def _is_demo_unlimited_uncached(child_id: int) -> bool:
    row = fetch_one(
        """SELECT demo_unlimited
           FROM users
           WHERE user_id=%s AND role='CHILD' AND account_status='ACTIVE'""",
        (child_id,),
    )
    return bool((row or {}).get("demo_unlimited"))
