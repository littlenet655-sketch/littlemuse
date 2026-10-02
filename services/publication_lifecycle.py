"""Visibility refresh hooks for a newly published child post.

Most LittleNet surfaces query PostgreSQL directly, but feed/reel cursor
sessions are intentionally materialized for pagination. A newly ALLOWED post
must invalidate those sessions or it can remain absent for the session TTL.
"""
from __future__ import annotations

from database.connection import execute


def refresh_publication_visibility(post_id: int, creator_id: int, is_reel: bool = False) -> bool:
    """Invalidate stale feed/reel sessions after an ALLOW transition.

    Profile, Explore, and search eligibility are query-backed and therefore
    refresh automatically on the next request. Deleting the materialized
    sessions refreshes both the creator's feed and every viewer's relevant
    feed/reel surface. REVIEW and BLOCK callers must not invoke this hook.
    """
    try:
        # Remove the specific item first for databases where session cleanup is
        # asynchronous or foreign-key cascades are disabled.
        execute(
            "DELETE FROM feed_session_items WHERE source_type='SOCIAL' AND source_id=%s",
            (int(post_id),),
        )
        execute(
            """DELETE FROM feed_sessions
               WHERE surface='FEED' OR (%s=TRUE AND surface='REELS')""",
            (bool(is_reel),),
        )
        return True
    except Exception:
        # Publication is already committed; stale sessions are safe (they
        # never expose REVIEW/BLOCK content) and can be rebuilt on expiry.
        return False