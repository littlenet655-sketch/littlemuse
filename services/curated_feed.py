"""Curated and merged feed service for LittleNet Kids Mode.

Maintains strict separation between curated system media and user-generated social posts.
Enforces fail-closed database safety gates BEFORE ranking:
- Only PUBLISHED curated content
- Only ALLOWED and is_safe=TRUE media assets
- Active content categories permitted by Parent Mode controls
- Child age bounds (min_age <= age <= max_age and audience_age_group matching)
- Stable feed sessions with position-based cursor pagination and content_impressions tracking
- Category diversity (max 2 consecutive items from the same category)
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any

from database.connection import execute, fetch_all, fetch_one, get_db_connection
from services.controls import EDUCATIONAL_CATEGORIES, controls_for_child, effective_categories
from services.request_cache import memo as _req_memo
from services.social import _age_group, child_surface_open


def _child_real_age(child_id: int) -> int:
    # Queried once per media authorization in feed loops; the child's age
    # cannot change mid-request, so memoize it on flask.g.
    return _req_memo(("_child_real_age", child_id), lambda: _child_real_age_uncached(child_id))


def _child_real_age_uncached(child_id: int) -> int:
    row = fetch_one("SELECT age, date_of_birth FROM child_profiles WHERE child_id=%s", (child_id,)) or {}
    age = row.get("age")
    if not age and row.get("date_of_birth"):
        from datetime import date
        dob = row["date_of_birth"]
        today = date.today()
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    if not age:
        u = fetch_one("SELECT age FROM users WHERE user_id=%s", (child_id,)) or {}
        age = u.get("age")
    try:
        val = int(age)
        if 6 <= val <= 16:
            return val
    except (TypeError, ValueError):
        pass
    # Fallback to middle of age group or standard 10
    grp = _age_group(child_id)
    if grp == "6-8":
        return 7
    if grp == "9-11":
        return 10
    if grp == "12-13":
        return 12
    if grp == "14-18":
        return 15
    return 10


def normalize_curated_item(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize a curated_content row to the common LittleNet feed item format."""
    media_ref = row.get("delivery_object_key") or row.get("original_object_key") or ""
    poster_ref = row.get("poster_object_key") or row.get("thumbnail_object_key")
    return {
        "source_type": "CURATED",
        "source_id": int(row["content_id"]),
        "post_id": int(row["content_id"]),
        "author_name": "LittleNet Learning",
        "full_name": "LittleNet Learning",
        "avatar_url": None,
        "media_type": str(row.get("media_type") or "IMAGE").upper(),
        "media_reference": media_ref,
        "poster_reference": poster_ref,
        "title": str(row.get("title") or ""),
        "caption": str(row.get("caption") or ""),
        "category": str(row.get("category") or "General Knowledge"),
        "content_category": str(row.get("category") or "General Knowledge"),
        "category_slug": str(row.get("category_slug") or "general-knowledge"),
        "is_educational": bool(row.get("is_educational", True)),
        "is_reel": bool(row.get("is_reel", False)),
        "audience_age_group": str(row.get("audience_age_group") or "ALL"),
        "min_age": int(row.get("min_age") or 4),
        "max_age": int(row.get("max_age") or 18),
        "is_safe": True,
        "moderation_status": "ALLOWED",
        "likes": 0,
        "comments_count": 0,
        "ranking_metadata": {
            "editorial_weight": float(row.get("editorial_weight") or 1.0),
            "published_at": str(row.get("published_at") or ""),
            "author_name": "LittleNet Learning",
            "is_curated": True,
        },
    }


def normalize_social_item(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize a social posts row to the common LittleNet feed item format."""
    cat = str(row.get("content_category") or "Other")
    return {
        "source_type": "SOCIAL",
        "source_id": int(row["post_id"]),
        "post_id": int(row["post_id"]),
        "author_name": str(row.get("full_name") or "Friend"),
        "full_name": str(row.get("full_name") or "Friend"),
        "avatar_url": row.get("profile_picture"),
        "media_type": str(row.get("media_type") or "TEXT").upper(),
        "media_reference": row.get("media_path") or row.get("media_url") or "",
        "poster_reference": row.get("poster_path") or row.get("thumbnail_url"),
        "title": None,
        "caption": str(row.get("caption") or ""),
        "category": cat,
        "content_category": cat,
        "category_slug": cat.lower().replace(" & ", "-").replace(" ", "-"),
        "is_educational": cat in EDUCATIONAL_CATEGORIES,
        "is_reel": bool(row.get("is_reel", False)),
        "audience_age_group": str(row.get("audience_age_group") or "ALL"),
        "min_age": 4,
        "max_age": 18,
        "is_safe": bool(row.get("is_safe", True)),
        "moderation_status": str(row.get("moderation_status") or "ALLOWED"),
        "likes": int(row.get("likes") or 0),
        "comments_count": int(row.get("comments_count") or 0),
        "ranking_metadata": {
            "likes": int(row.get("likes") or 0),
            "comments_count": int(row.get("comments_count") or 0),
            "is_following": bool(row.get("is_following", False)),
            "created_at": str(row.get("created_at") or ""),
            "child_id": int(row.get("child_id") or 0),
            "author_name": str(row.get("full_name") or "Friend"),
            "author_avatar": row.get("profile_picture"),
            "is_curated": False,
        },
    }


def _social_media_renderable(item: dict[str, Any]) -> bool:
    """Keep legacy/missing media rows out of mobile feeds instead of rendering broken tiles."""
    media_type=str(item.get("media_type") or "TEXT").upper()
    if media_type == "TEXT":
        return True
    ref=str(item.get("media_reference") or "").strip()
    if not ref:
        return False
    if ref.startswith(("https://","http://","uploads/r2/","static/")):
        return True
    if ref.startswith("uploads/"):
        return os.path.exists(ref)
    return False


def fetch_curated_candidates(child_id: int, surface: str = "FEED", limit: int = 60) -> list[dict[str, Any]]:
    """Retrieve verified safe curated content with database-level safety gates."""
    cats = effective_categories(child_id)
    if not cats:
        return []
    child_age = _child_real_age(child_id)
    age_grp = _age_group(child_id)
    is_reel = str(surface).upper() == "REELS"

    # Strictly fail-closed: must be PUBLISHED, asset must be ALLOWED & is_safe=TRUE, category must be active
    rows = fetch_all(
        """SELECT 
             cc.content_id, cc.title, cc.caption, cc.audience_age_group, cc.min_age, cc.max_age,
             cc.is_reel, cc.editorial_weight, cc.published_at,
             cma.asset_id, cma.media_type, cma.delivery_object_key, cma.original_object_key,
             cma.poster_object_key, cma.thumbnail_object_key, cma.mime_type, cma.width, cma.height,
             cma.duration_seconds, cma.file_size_bytes, cma.moderation_status, cma.is_safe,
             cat.category_id, cat.slug AS category_slug, cat.display_name AS category, cat.is_educational
           FROM curated_content cc
           JOIN curated_media_assets cma ON cma.asset_id = cc.asset_id
           JOIN content_categories cat ON cat.category_id = cc.category_id
           WHERE cc.publish_status = 'PUBLISHED'
             AND cma.moderation_status = 'ALLOWED'
             AND cma.is_safe = TRUE
             AND cat.active = TRUE
             AND cat.display_name = ANY(%s)
             AND cc.is_reel = %s
             AND cc.min_age <= %s AND cc.max_age >= %s
             AND (%s IS NULL OR cc.audience_age_group = 'ALL' OR cc.audience_age_group = %s)
           ORDER BY cc.editorial_weight DESC, cc.published_at DESC NULLS LAST, cc.content_id DESC
           LIMIT %s""",
        (cats, is_reel, child_age, child_age, age_grp, age_grp, limit),
    )
    return [normalize_curated_item(r) for r in rows]


def fetch_social_candidates(child_id: int, surface: str = "FEED", limit: int = 60) -> list[dict[str, Any]]:
    """Retrieve safe social posts using only fixed parameterized SQL."""
    from child.service import discoverable_child_ids

    allowed_child_ids = discoverable_child_ids(child_id)
    if allowed_child_ids is not None and len(allowed_child_ids) == 0:
        return []
    cats = effective_categories(child_id)
    age_grp = _age_group(child_id)
    is_reel = str(surface).upper() == "REELS"
    if is_reel:
        rows = fetch_all(
            """SELECT p.*, u.full_name, cp.profile_picture,
                 (SELECT COUNT(*) FROM likes l WHERE l.post_id = p.post_id) AS likes,
                 (SELECT COUNT(*) FROM comments c WHERE c.post_id = p.post_id AND c.moderation_status = 'ALLOWED') AS comments_count,
                 EXISTS(SELECT 1 FROM followers f WHERE f.approved = TRUE AND f.approval_stage = 'ACTIVE'
                   AND ((f.child_id = %s AND f.following_child_id = p.child_id) OR (f.child_id = p.child_id AND f.following_child_id = %s))) AS is_following
               FROM posts p
               JOIN users u ON u.user_id = p.child_id
               LEFT JOIN child_profiles cp ON cp.child_id = p.child_id
               WHERE p.moderation_status = 'ALLOWED' AND p.is_safe = TRUE AND p.is_story = FALSE
                 AND p.is_reel = TRUE
                  AND p.child_id = ANY(%s::int[])
                 AND p.content_category = ANY(%s)
                 AND (%s IS NULL OR p.audience_age_group = 'ALL' OR p.audience_age_group = %s)
                 AND p.child_id <> %s
                 AND p.child_id NOT IN (
                   SELECT blocked_id FROM blocked_users WHERE blocker_id = %s
                   UNION SELECT blocker_id FROM blocked_users WHERE blocked_id = %s
                   UNION SELECT muted_id FROM muted_users WHERE muter_id = %s)
               ORDER BY p.created_at DESC
               LIMIT %s""",
             (child_id, child_id, allowed_child_ids, cats, age_grp, age_grp, child_id, child_id, child_id, child_id, limit),
        )
        normalized=[normalize_social_item(r) for r in rows]
        return [item for item in normalized if _social_media_renderable(item)]
    rows = fetch_all(
        """SELECT p.*, u.full_name, cp.profile_picture,
             (SELECT COUNT(*) FROM likes l WHERE l.post_id = p.post_id) AS likes,
             (SELECT COUNT(*) FROM comments c WHERE c.post_id = p.post_id AND c.moderation_status = 'ALLOWED') AS comments_count,
             EXISTS(SELECT 1 FROM followers f WHERE f.approved = TRUE AND f.approval_stage = 'ACTIVE'
               AND ((f.child_id = %s AND f.following_child_id = p.child_id) OR (f.child_id = p.child_id AND f.following_child_id = %s))) AS is_following
           FROM posts p
           JOIN users u ON u.user_id = p.child_id
           LEFT JOIN child_profiles cp ON cp.child_id = p.child_id
           WHERE p.moderation_status = 'ALLOWED' AND p.is_safe = TRUE AND p.is_story = FALSE
             AND p.is_reel = FALSE
             AND (%s::int[] IS NULL OR p.child_id = ANY(%s::int[]))
             AND p.content_category = ANY(%s)
             AND (%s IS NULL OR p.audience_age_group = 'ALL' OR p.audience_age_group = %s)
             AND p.child_id <> %s
             AND p.child_id NOT IN (
               SELECT blocked_id FROM blocked_users WHERE blocker_id = %s
               UNION SELECT blocker_id FROM blocked_users WHERE blocked_id = %s
               UNION SELECT muted_id FROM muted_users WHERE muter_id = %s)
           ORDER BY p.created_at DESC
           LIMIT %s""",
        (child_id, child_id, allowed_child_ids, allowed_child_ids, cats, age_grp, age_grp,
         child_id, child_id, child_id, child_id, limit),
    )
    normalized=[normalize_social_item(r) for r in rows]
    return [item for item in normalized if _social_media_renderable(item)]


def get_recent_impression_keys(child_id: int, surface: str, hours: int = 2) -> set[tuple[str, int]]:
    """Retrieve items shown to the child recently to enforce no-repeat windows."""
    rows = fetch_all(
        """SELECT source_type, source_id
           FROM content_impressions
           WHERE child_id = %s AND surface = %s AND shown_at >= NOW() - (%s || ' hours')::INTERVAL""",
        (child_id, str(surface).upper(), str(hours)),
    )
    return {(r["source_type"], int(r["source_id"])) for r in rows}


def apply_category_diversity(items: list[dict[str, Any]], max_consecutive: int = 2) -> list[dict[str, Any]]:
    """Enforce that no more than max_consecutive items share the exact same category when alternatives exist."""
    if not items or len(items) <= max_consecutive:
        return list(items)

    balanced = []
    pool = list(items)
    last_cat = None
    consecutive_count = 0

    while pool:
        selected_idx = None
        for idx, item in enumerate(pool):
            cat = item.get("category") or "Other"
            if cat != last_cat or consecutive_count < max_consecutive:
                selected_idx = idx
                break
        if selected_idx is None:
            # All remaining share the same category; take the first
            selected_idx = 0

        item = pool.pop(selected_idx)
        cat = item.get("category") or "Other"
        if cat == last_cat:
            consecutive_count += 1
        else:
            last_cat = cat
            consecutive_count = 1
        balanced.append(item)

    return balanced


def merge_candidates(social: list[dict[str, Any]], curated: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge social and curated candidates in a balanced educational blend."""
    if not social:
        return curated
    if not curated:
        return social

    merged: list[dict[str, Any]] = []
    s_idx, c_idx = 0, 0
    # Blend pattern: 2 social, 1 curated when available
    while s_idx < len(social) or c_idx < len(curated):
        for _ in range(2):
            if s_idx < len(social):
                merged.append(social[s_idx])
                s_idx += 1
        if c_idx < len(curated):
            merged.append(curated[c_idx])
            c_idx += 1

    return merged


def _session_source_keys(child_id: int, surface: str, session_id: str | None) -> set[tuple[str, int]]:
    """Return source identities from one child-owned feed session.

    Session ids cross an HTTP trust boundary. Reject malformed UUIDs before
    PostgreSQL sees them so a bad/stale client value cannot turn pagination
    into a 500 response.
    """
    if not session_id:
        return set()
    try:
        from uuid import UUID
        UUID(str(session_id))
    except (TypeError, ValueError, AttributeError):
        return set()
    rows = fetch_all(
        """SELECT fsi.source_type, fsi.source_id
           FROM feed_session_items fsi
           JOIN feed_sessions fs ON fs.session_id = fsi.session_id
           WHERE fs.session_id = %s AND fs.child_id = %s AND fs.surface = %s""",
        (session_id, child_id, str(surface).upper()),
    )
    return {(str(r["source_type"]).upper(), int(r["source_id"])) for r in rows or []}


def _filter_feed_mode(items: list[dict[str, Any]], mode: str) -> list[dict[str, Any]]:
    mode_clean = str(mode or "for_you").strip().lower()
    if mode_clean == "friends":
        return [it for it in items if it.get("source_type") == "SOCIAL"]
    if mode_clean == "learn":
        edu_cats = {"Science", "Math", "Technology", "Nature", "Books", "Coding", "General Knowledge", "Education", "Art"}
        return [it for it in items if it.get("source_type") == "CURATED" or it.get("category") in edu_cats]
    return list(items)


def _has_refill_candidates(child_id: int, surface: str, session_id: str, mode: str) -> bool:
    """Probe for eligible content outside the exhausted session."""
    surface_clean = str(surface).upper()
    excluded = _session_source_keys(child_id, surface_clean, session_id)
    curated = [
        item for item in fetch_curated_candidates(child_id, surface_clean, limit=180)
        if (item["source_type"], int(item["source_id"])) not in excluded
    ]
    social = [
        item for item in fetch_social_candidates(child_id, surface_clean, limit=180)
        if (item["source_type"], int(item["source_id"])) not in excluded
    ]
    combined = merge_candidates(social, curated)
    from services.recommendation import rank_candidates, apply_diversity_and_balance
    ranked = rank_candidates(child_id, combined)
    diversified = apply_diversity_and_balance(ranked, max_consecutive=2)
    return bool(_filter_feed_mode(diversified, mode))


def get_or_create_feed_session(
    child_id: int,
    surface: str = "FEED",
    session_id: str | None = None,
    exclude_session_id: str | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Get an active session or create a refill session excluding the prior session."""
    surface_clean = str(surface).upper()
    if session_id:
        existing = fetch_one(
            """SELECT session_id FROM feed_sessions
               WHERE session_id = %s AND child_id = %s AND surface = %s AND expires_at > NOW()""",
            (session_id, child_id, surface_clean),
        )
        if existing:
            # Session exists, load items
            raw_items = fetch_all(
                """SELECT position, source_type, source_id
                   FROM feed_session_items
                   WHERE session_id = %s ORDER BY position ASC""",
                (session_id,),
            )
            items = _materialize_session_items(raw_items, child_id, surface_clean)
            return str(existing["session_id"]), items

    # Create new session. Refill sessions probe a wider catalog so the first
    # 60 candidates cannot hide additional eligible content.
    excluded = _session_source_keys(child_id, surface_clean, exclude_session_id)
    candidate_limit = 180 if excluded else 60
    curated = [
        item for item in fetch_curated_candidates(child_id, surface_clean, limit=candidate_limit)
        if (item["source_type"], int(item["source_id"])) not in excluded
    ]
    social = [
        item for item in fetch_social_candidates(child_id, surface_clean, limit=candidate_limit)
        if (item["source_type"], int(item["source_id"])) not in excluded
    ]

    # Filter recently shown impressions
    recent = get_recent_impression_keys(child_id, surface_clean, hours=2)
    curated_filtered = [c for c in curated if (c["source_type"], c["source_id"]) not in recent]
    social_filtered = [s for s in social if (s["source_type"], s["source_id"]) not in recent]

    # Fallback to full pool if filtered pool is too small
    active_curated = curated_filtered if len(curated_filtered) >= 5 else curated
    active_social = social_filtered if len(social_filtered) >= 3 else social

    combined = merge_candidates(active_social, active_curated)
    from services.recommendation import rank_candidates, apply_diversity_and_balance
    ranked = rank_candidates(child_id, combined)
    diversified = apply_diversity_and_balance(ranked, max_consecutive=2)

    # Deduplicate within session
    seen_keys: set[tuple[str, int]] = set()
    final_items: list[dict[str, Any]] = []
    for item in diversified:
        key = (item["source_type"], int(item["source_id"]))
        if key not in seen_keys:
            seen_keys.add(key)
            final_items.append(item)

    # Persist session to database
    row = execute(
        """INSERT INTO feed_sessions(child_id, surface)
           VALUES(%s, %s) RETURNING session_id""",
        (child_id, surface_clean),
        returning=True,
    )
    new_session_id = str(row["session_id"])

    if final_items:
        records = [(new_session_id, pos, item["source_type"], item["source_id"]) for pos, item in enumerate(final_items)]
        from psycopg2.extras import execute_values
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    "INSERT INTO feed_session_items(session_id, position, source_type, source_id) VALUES %s",
                    records,
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    return new_session_id, final_items


def _materialize_session_items(raw_items: list[dict[str, Any]], child_id: int, surface: str) -> list[dict[str, Any]]:
    """Hydrate session position entries with full item payload."""
    curated_ids = [int(r["source_id"]) for r in raw_items if r["source_type"] == "CURATED"]
    social_ids = [int(r["source_id"]) for r in raw_items if r["source_type"] == "SOCIAL"]

    curated_map = {}
    if curated_ids:
        c_rows = fetch_all(
            """SELECT 
                 cc.content_id, cc.title, cc.caption, cc.audience_age_group, cc.min_age, cc.max_age,
                 cc.is_reel, cc.editorial_weight, cc.published_at,
                 cma.asset_id, cma.media_type, cma.delivery_object_key, cma.original_object_key,
                 cma.poster_object_key, cma.thumbnail_object_key, cma.mime_type, cma.width, cma.height,
                 cma.duration_seconds, cma.file_size_bytes, cma.moderation_status, cma.is_safe,
                 cat.category_id, cat.slug AS category_slug, cat.display_name AS category, cat.is_educational
               FROM curated_content cc
               JOIN curated_media_assets cma ON cma.asset_id = cc.asset_id
               JOIN content_categories cat ON cat.category_id = cc.category_id
               WHERE cc.content_id = ANY(%s)
                 AND cc.publish_status = 'PUBLISHED'
                 AND cma.moderation_status = 'ALLOWED'
                 AND cma.is_safe = TRUE""",
            (curated_ids,),
        )
        curated_map = {int(r["content_id"]): normalize_curated_item(r) for r in c_rows}

    social_map = {}
    if social_ids:
        s_rows = fetch_all(
            """SELECT p.*, u.full_name, cp.profile_picture,
                 (SELECT COUNT(*) FROM likes l WHERE l.post_id = p.post_id) AS likes,
                 (SELECT COUNT(*) FROM comments c WHERE c.post_id = p.post_id AND c.moderation_status = 'ALLOWED') AS comments_count
               FROM posts p
               JOIN users u ON u.user_id = p.child_id
               LEFT JOIN child_profiles cp ON cp.child_id = p.child_id
               WHERE p.post_id = ANY(%s) AND p.moderation_status = 'ALLOWED' AND p.is_safe = TRUE""",
            (social_ids,),
        )
        social_map = {int(r["post_id"]): normalize_social_item(r) for r in s_rows}

    # Session rows are only a cursor, not an authorization grant. Re-check
    # current Parent controls, age, friendship/discoverability, and blocks
    # after loading the materialized content so settings take effect without
    # waiting for the session TTL.
    surface_clean = str(surface).upper()
    controls = controls_for_child(child_id)
    if surface_clean == "REELS" and not controls.get("allow_reels", True):
        return []
    cats = set(effective_categories(child_id))
    age_group = _age_group(child_id)
    child_age = _child_real_age(child_id)
    from child.service import discoverable_child_ids
    discoverable_ids = set(discoverable_child_ids(child_id) or [])
    blocked_rows = fetch_all(
        """SELECT blocked_id AS creator_id FROM blocked_users WHERE blocker_id=%s
           UNION SELECT blocker_id AS creator_id FROM blocked_users WHERE blocked_id=%s
           UNION SELECT muted_id AS creator_id FROM muted_users WHERE muter_id=%s""",
        (child_id, child_id, child_id),
    )
    blocked_ids = {int(row["creator_id"]) for row in blocked_rows or [] if row.get("creator_id") is not None}

    # A HIDE / NOT_INTERESTED recorded after the session was created must take
    # effect immediately, without waiting for the session TTL to expire.
    from services.recommendation import hidden_items as _hidden_items
    _probe = []
    for r in raw_items:
        sid = int(r["source_id"])
        stype = r["source_type"]
        item = curated_map.get(sid) if stype == "CURATED" else social_map.get(sid)
        if item:
            _probe.append({"source_type": stype, "source_id": sid})
    hidden_keys = _hidden_items(child_id, _probe)

    def current_eligible(item: dict[str, Any]) -> bool:
        key = (str(item.get("source_type") or "SOCIAL").upper(), int(item.get("source_id", 0) or 0))
        if key in hidden_keys:
            return False
        if item.get("moderation_status") != "ALLOWED" or item.get("is_safe") is not True:
            return False
        if bool(item.get("is_reel")) != (surface_clean == "REELS"):
            return False
        if item.get("category") not in cats:
            return False
        audience = str(item.get("audience_age_group") or "ALL")
        if age_group and audience not in {"ALL", age_group}:
            return False
        try:
            if not (int(item.get("min_age", 4)) <= child_age <= int(item.get("max_age", 18))):
                return False
        except (TypeError, ValueError):
            return False
        if item.get("source_type") == "SOCIAL":
            creator_id = int((item.get("ranking_metadata") or {}).get("child_id") or 0)
            if creator_id in blocked_ids or creator_id not in discoverable_ids:
                return False
        return True

    hydrated = []
    for r in raw_items:
        sid = int(r["source_id"])
        stype = r["source_type"]
        item = curated_map.get(sid) if stype == "CURATED" else social_map.get(sid)
        if item and current_eligible(item):
            hydrated.append(item)

    return hydrated


def get_feed_page(
    child_id: int,
    surface: str = "FEED",
    cursor: int = 0,
    limit: int = 10,
    session_id: str | None = None,
    mode: str = "for_you",
    refill_from_session_id: str | None = None,
) -> dict[str, Any]:
    """Paginate stable sessions and expose an explicit safe refill boundary."""
    if refill_from_session_id and not session_id:
        sess_id, items = get_or_create_feed_session(
            child_id,
            surface,
            None,
            exclude_session_id=refill_from_session_id,
        )
    else:
        sess_id, items = get_or_create_feed_session(child_id, surface, session_id)

    mode_clean = str(mode or "for_you").strip().lower()
    items = _filter_feed_mode(items, mode_clean)

    total = len(items)
    start = max(0, cursor)
    page_items = [dict(item, feed_session_id=sess_id) for item in items[start : start + limit]]
    next_cursor = start + len(page_items)
    has_more = next_cursor < total

    can_refill = False
    if not has_more and total > 0:
        can_refill = _has_refill_candidates(child_id, surface, sess_id, mode_clean)

    exhaustion_reason = None
    if not has_more:
        exhaustion_reason = "SESSION_END" if can_refill else "NO_ELIGIBLE_CONTENT"

    return {
        "session_id": sess_id,
        "mode": mode_clean,
        "items": page_items,
        "cursor": cursor,
        "next_cursor": next_cursor if has_more else None,
        "has_more": has_more,
        "can_refill": can_refill,
        "exhaustion_reason": exhaustion_reason,
        "total_in_session": total,
    }


def curated_item_visible_to(child_id: int, content_id: int) -> bool:
    """Light eligibility check for a curated item (publication, asset safety, category, age).

    Used for validating feedback actions without resolving media delivery URLs.
    """
    cats = effective_categories(child_id)
    if not cats:
        return False
    child_age = _child_real_age(child_id)
    age_group = _age_group(child_id)
    row = fetch_one(
        """SELECT 1
             FROM curated_content cc
             JOIN curated_media_assets cma ON cma.asset_id = cc.asset_id
             JOIN content_categories cat ON cat.category_id = cc.category_id
            WHERE cc.content_id = %s
              AND cc.publish_status = 'PUBLISHED'
              AND cma.moderation_status = 'ALLOWED'
              AND cma.is_safe = TRUE
              AND cat.active = TRUE
              AND cat.display_name = ANY(%s)
              AND cc.min_age <= %s AND cc.max_age >= %s
              AND (%s IS NULL OR cc.audience_age_group = 'ALL' OR cc.audience_age_group = %s)""",
        (content_id, cats, child_age, child_age, age_group, age_group),
    )
    return bool(row)


def authorize_curated_media(child_id: int, content_id: int) -> dict[str, Any]:
    """Authorize access to curated media for a child, enforcing all safety and parent gates."""
    if not child_surface_open(child_id):
        raise PermissionError("child_surface_locked")

    cats = effective_categories(child_id)
    child_age = _child_real_age(child_id)

    row = fetch_one(
        """SELECT 
             cc.content_id, cc.publish_status, cc.min_age, cc.max_age, cc.audience_age_group,
             cat.display_name AS category, cat.active AS category_active,
             cma.asset_id, cma.media_type, cma.delivery_object_key, cma.original_object_key,
             cma.poster_object_key, cma.moderation_status, cma.is_safe
           FROM curated_content cc
           JOIN curated_media_assets cma ON cma.asset_id = cc.asset_id
           JOIN content_categories cat ON cat.category_id = cc.category_id
           WHERE cc.content_id = %s""",
        (content_id,),
    )
    if not row:
        raise FileNotFoundError("curated_content_not_found")

    # Fail closed: must be PUBLISHED, ALLOWED, safe, active category, within age bounds, permitted by parent
    if row.get("publish_status") != "PUBLISHED":
        raise PermissionError("content_not_published")
    if row.get("moderation_status") != "ALLOWED" or not row.get("is_safe"):
        raise PermissionError("content_blocked_or_unapproved")
    if not row.get("category_active") or row.get("category") not in cats:
        raise PermissionError("category_restricted_by_parent")
    if not (row["min_age"] <= child_age <= row["max_age"]):
        raise PermissionError("age_ineligible")

    key = row.get("delivery_object_key") or row.get("original_object_key")
    from services.media_delivery import resolve_media_delivery

    m_res = resolve_media_delivery(key, viewer_id=child_id, viewer_role="CHILD")
    p_res = resolve_media_delivery(row.get("poster_object_key"), viewer_id=child_id, viewer_role="CHILD")

    return {
        "content_id": row["content_id"],
        "media_type": row["media_type"],
        "media_url": m_res.get("url"),
        "poster_url": p_res.get("url"),
        "playback_expires_at": m_res.get("expires_at"),
    }


def record_feed_impression(
    child_id: int,
    session_id: str,
    source_type: str,
    source_id: int,
    surface: str,
    watched_ms: int | None = None,
    completed: bool = False,
    liked: bool = False,
    saved: bool = False,
    replay_count: int = 0,
) -> bool:
    """Record that an item was viewed by a child after validating it belonged to their active session."""
    stype = str(source_type).upper()
    if stype in {"POST", "REEL", "STORY"}:
        stype = "SOCIAL"
    surf = str(surface).upper()
    if stype not in {"SOCIAL", "CURATED"} or surf not in {"FEED", "REELS"}:
        return False
    if not session_id or watched_ms is not None and (int(watched_ms) < 0 or int(watched_ms) > 14_400_000):
        return False

    # Validate that session belongs to child and item was part of that session
    valid = fetch_one(
        """SELECT 1
           FROM feed_sessions fs
           JOIN feed_session_items fsi ON fsi.session_id = fs.session_id
           WHERE fs.session_id = %s AND fs.child_id = %s AND fs.surface = %s
             AND fs.expires_at > NOW()
             AND fsi.source_type = %s AND fsi.source_id = %s""",
        (session_id, child_id, surf, stype, source_id),
    )
    if not valid:
        return False

    execute(
        """INSERT INTO content_impressions(
             child_id, source_type, source_id, surface, watched_ms, completed, liked, saved, replay_count)
           VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (child_id, stype, source_id, surf, watched_ms, completed, liked, saved, max(0, int(replay_count or 0))),
    )
    from services.recommendation_signals import record_reel_completion, record_signal
    if completed:
        record_reel_completion(child_id, stype, source_id, replay_count if surf == "REELS" else 0)
    elif replay_count and surf == "REELS":
        for _ in range(min(max(int(replay_count), 0), 20)):
            record_signal(child_id, stype, source_id, "REEL_REPLAY")
    if liked:
        record_signal(child_id, stype, source_id, "LIKE")
    if saved:
        record_signal(child_id, stype, source_id, "SAVE")
    return True


def search_curated_content(child_id: int, query: str, limit: int = 20) -> list[dict[str, Any]]:
    """Search safe published curated content by title, caption, category or hashtag."""
    cats = effective_categories(child_id)
    child_age = _child_real_age(child_id)
    cleaned = str(query or "").strip().lstrip("#").lower()
    if not cleaned or not cats:
        return []

    pattern = f"%{cleaned}%"
    rows = fetch_all(
        """SELECT DISTINCT
             cc.content_id, cc.title, cc.caption, cc.audience_age_group, cc.min_age, cc.max_age,
             cc.is_reel, cc.editorial_weight, cc.published_at,
             cma.asset_id, cma.media_type, cma.delivery_object_key, cma.original_object_key,
             cma.poster_object_key, cma.thumbnail_object_key, cma.mime_type, cma.width, cma.height,
             cma.duration_seconds, cma.file_size_bytes, cma.moderation_status, cma.is_safe,
             cat.category_id, cat.slug AS category_slug, cat.display_name AS category, cat.is_educational
           FROM curated_content cc
           JOIN curated_media_assets cma ON cma.asset_id = cc.asset_id
           JOIN content_categories cat ON cat.category_id = cc.category_id
           LEFT JOIN curated_content_hashtags cch ON cch.content_id = cc.content_id
           LEFT JOIN hashtags h ON h.hashtag_id = cch.hashtag_id
           WHERE cc.publish_status = 'PUBLISHED'
             AND cma.moderation_status = 'ALLOWED'
             AND cma.is_safe = TRUE
             AND cat.active = TRUE
             AND cat.display_name = ANY(%s)
             AND cc.min_age <= %s AND cc.max_age >= %s
             AND (
               LOWER(cc.title) LIKE %s
               OR LOWER(cc.caption) LIKE %s
               OR LOWER(cat.display_name) LIKE %s
               OR LOWER(h.tag) LIKE %s
             )
           ORDER BY cc.editorial_weight DESC, cc.content_id DESC
           LIMIT %s""",
        (cats, child_age, child_age, pattern, pattern, pattern, pattern, limit),
    )
    return [normalize_curated_item(r) for r in rows]
