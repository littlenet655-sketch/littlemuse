"""Safe personalized ranking for LittleNet's dedicated Kids feed.

Merges social graph candidates with safe curated educational content.
Never returns an empty feed solely because the child has zero approved social connections.
"""
from __future__ import annotations

import math
import os
from datetime import datetime, timezone
from typing import Any

from database.connection import fetch_all, fetch_one
from services.controls import EDUCATIONAL_CATEGORIES, effective_categories
from services.curated_feed import (
    apply_category_diversity,
    _child_real_age,
    fetch_curated_candidates,
    merge_candidates,
    normalize_curated_item,
    normalize_social_item,
)
from services.social import _age_group
from services.recommendation_signals import signal_scores


def _item_key(item: dict[str, Any]) -> tuple[str, int] | None:
    """Canonical (source_type, source_id) key for an item, or None if unusable."""
    try:
        source_id = int(item.get("source_id", item.get("post_id", 0)) or 0)
    except (TypeError, ValueError):
        return None
    if source_id <= 0:
        return None
    return (str(item.get("source_type") or "SOCIAL").upper(), source_id)


def hidden_items(child_id: int, rows: list[dict[str, Any]]) -> set[tuple[str, int]]:
    """Return items the child explicitly hid or marked not-interested.

    Unlike the advisory `signal_scores` weights (which only demote), an explicit
    HIDE / NOT_INTERESTED is a hard exclusion: the item must not be recommended
    again in any feed surface. BLOCK and MUTE are creator-scoped and are
    enforced separately through the block/mute feed filters.
    """
    if not rows:
        return set()
    social_ids = set()
    curated_ids = set()
    for item in rows:
        key = _item_key(item)
        if not key:
            continue
        (curated_ids if key[0] == "CURATED" else social_ids).add(key[1])
    if not social_ids and not curated_ids:
        return set()
    try:
        found = fetch_all(
            """SELECT DISTINCT source_type, source_id
                 FROM recommendation_signals
                WHERE child_id = %s
                  AND signal IN ('NOT_INTERESTED', 'HIDE')
                  AND ((source_type = 'SOCIAL' AND source_id = ANY(%s))
                    OR (source_type = 'CURATED' AND source_id = ANY(%s)))""",
            (int(child_id), list(social_ids), list(curated_ids)),
        )
    except Exception:
        # Fail open on telemetry read failure: scoring still applies the
        # strong negative weight, so the item is demoted even if not hidden.
        return set()
    return {
        (str(r.get("source_type") or "").upper(), int(r["source_id"]))
        for r in found or []
        if r.get("source_id") is not None
    }


def _flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _profile_terms(cid: int) -> tuple[list[str], str]:
    rows = fetch_all(
        """SELECT value FROM (
             SELECT skill_name AS value FROM child_skills WHERE child_id = %s AND approved = TRUE
             UNION SELECT interest_name FROM child_interests WHERE child_id = %s AND approved = TRUE
             UNION SELECT ambition_name FROM child_ambitions WHERE child_id = %s AND approved = TRUE
           ) x""",
        (cid, cid, cid),
    )
    terms = [str(r["value"]).strip() for r in rows if r.get("value")]
    profile = fetch_one("SELECT bio, current_class FROM child_profiles WHERE child_id = %s", (cid,)) or {}
    context = " ".join(terms + [str(profile.get("bio") or ""), str(profile.get("current_class") or "")]).strip()
    return terms, context or "safe educational and age appropriate content"


def candidates(cid: int, cap: int = 60, surface: str = "FEED") -> list[dict[str, Any]]:
    """Retrieve combined candidates from social connections and curated catalog independently.

    A child with zero social connections will receive curated LittleNet content rather
    than experiencing empty-feed starvation.
    """
    # Reuse the exact child-discovery boundary instead of building a wider
    # recommendation-only graph. Recommendations must never reveal children the
    # viewer could not otherwise discover under Parent Mode policy.
    from child.service import discoverable_child_ids

    is_reel = str(surface).upper() == "REELS"
    allowed_child_ids = discoverable_child_ids(cid)
    cats = effective_categories(cid) if allowed_child_ids else []
    age_group = _age_group(cid) if allowed_child_ids else None
    if is_reel and allowed_child_ids:
        social_rows = fetch_all(
            """SELECT p.*,u.full_name,cp.profile_picture,
                (SELECT COUNT(*) FROM likes l WHERE l.post_id=p.post_id) likes,
                (SELECT COUNT(*) FROM comments c WHERE c.post_id=p.post_id AND c.moderation_status='ALLOWED') comments_count,
                EXISTS(SELECT 1 FROM followers f WHERE f.approved=TRUE AND f.approval_stage='ACTIVE'
                  AND ((f.child_id=%s AND f.following_child_id=p.child_id) OR (f.child_id=p.child_id AND f.following_child_id=%s))) is_following
              FROM posts p JOIN users u ON u.user_id=p.child_id LEFT JOIN child_profiles cp ON cp.child_id=p.child_id
              WHERE p.moderation_status='ALLOWED' AND p.is_safe=TRUE AND p.is_story=FALSE AND p.is_reel=TRUE
                AND p.content_category=ANY(%s)
                AND (%s IS NULL OR p.audience_age_group='ALL' OR p.audience_age_group=%s)
                AND p.child_id=ANY(%s) AND p.child_id<>%s
                AND p.child_id NOT IN (
                  SELECT blocked_id FROM blocked_users WHERE blocker_id=%s
                  UNION SELECT blocker_id FROM blocked_users WHERE blocked_id=%s
                  UNION SELECT muted_id FROM muted_users WHERE muter_id=%s)
              ORDER BY p.created_at DESC LIMIT %s""",
            (cid, cid, cats, age_group, age_group, allowed_child_ids, cid, cid, cid, cid, cap),
        )
    else:
        if not allowed_child_ids:
            social_rows = []
        else:
            social_rows = fetch_all(
                """SELECT p.*,u.full_name,cp.profile_picture,
                    (SELECT COUNT(*) FROM likes l WHERE l.post_id=p.post_id) likes,
                    (SELECT COUNT(*) FROM comments c WHERE c.post_id=p.post_id AND c.moderation_status='ALLOWED') comments_count,
                    EXISTS(SELECT 1 FROM followers f WHERE f.approved=TRUE AND f.approval_stage='ACTIVE'
                      AND ((f.child_id=%s AND f.following_child_id=p.child_id) OR (f.child_id=p.child_id AND f.following_child_id=%s))) is_following
                  FROM posts p JOIN users u ON u.user_id=p.child_id LEFT JOIN child_profiles cp ON cp.child_id=p.child_id
                  WHERE p.moderation_status='ALLOWED' AND p.is_safe=TRUE AND p.is_story=FALSE AND p.is_reel=FALSE
                    AND p.child_id=ANY(%s)
                    AND p.content_category=ANY(%s)
                    AND (%s IS NULL OR p.audience_age_group='ALL' OR p.audience_age_group=%s)
                    AND p.child_id<>%s
                    AND p.child_id NOT IN (
                      SELECT blocked_id FROM blocked_users WHERE blocker_id=%s
                      UNION SELECT blocker_id FROM blocked_users WHERE blocked_id=%s
                      UNION SELECT muted_id FROM muted_users WHERE muter_id=%s)
                  ORDER BY p.created_at DESC LIMIT %s""",
                (cid, cid, allowed_child_ids, cats, age_group, age_group, cid, cid, cid, cid, cap),
            )

    social_candidates = [normalize_social_item(r) for r in social_rows]
    curated_candidates = fetch_curated_candidates(cid, surface=surface, limit=cap)

    # Both social and curated are normalized to the common feed schema.
    # Provide backward-compatibility keys for legacy callers expecting post-like dicts:
    for item in social_candidates + curated_candidates:
        if "post_id" not in item:
            item["post_id"] = item["source_id"]
        if "content_category" not in item:
            item["content_category"] = item["category"]
        if "media_path" not in item:
            item["media_path"] = item["media_reference"]

    return merge_candidates(social_candidates, curated_candidates)


def _text_for(item: dict[str, Any]) -> str:
    parts = [
        item.get("category"),
        item.get("content_category"),
        item.get("title"),
        item.get("caption"),
        item.get("ranking_metadata", {}).get("author_name") if isinstance(item.get("ranking_metadata"), dict) else None,
        item.get("full_name"),
    ]
    return " ".join(str(p or "") for p in parts)[:500]


def _recency_score(item: dict[str, Any]) -> float:
    """Small freshness bonus with a 14-day decay; malformed dates get no bonus."""
    meta = item.get("ranking_metadata") or {}
    raw = (
        meta.get("created_at")
        or item.get("created_at")
        or meta.get("published_at")
        or item.get("published_at")
    )
    if not raw:
        return 0.0
    try:
        if isinstance(raw, datetime):
            created = raw
        else:
            created = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age_days = max(0.0, (datetime.now(timezone.utc) - created.astimezone(timezone.utc)).total_seconds() / 86400.0)
        return 1.5 * math.exp(-age_days / 14.0)
    except (TypeError, ValueError, OverflowError):
        return 0.0


def _engagement_score(item: dict[str, Any]) -> float:
    """Bounded popularity signal so viral content cannot swamp child interests."""
    meta = item.get("ranking_metadata") or {}
    try:
        likes = max(0.0, float(meta.get("likes") or item.get("likes") or 0))
    except (TypeError, ValueError):
        likes = 0.0
    try:
        comments = max(0.0, float(meta.get("comments_count") or item.get("comments_count") or 0))
    except (TypeError, ValueError):
        comments = 0.0
    return min(2.0, 0.25 * math.log1p(likes) + 0.35 * math.log1p(comments))


def _fallback_score(item: dict[str, Any], terms: list[str]) -> float:
    """Fast CPU-only rank score used for normal production feed requests."""
    hay = _text_for(item).lower()
    score = 0.0
    for term in terms:
        normalized = term.strip().lower()
        if normalized and normalized in hay:
            score += 3.0

    meta = item.get("ranking_metadata") or {}
    if meta.get("is_following"):
        score += 2.0
    if item.get("category") in EDUCATIONAL_CATEGORIES or item.get("content_category") in EDUCATIONAL_CATEGORIES:
        score += 1.0
    if item.get("source_type") == "CURATED":
        score += min(2.0, max(0.0, float(meta.get("editorial_weight") or 1.0)))
    score += _engagement_score(item)
    score += _recency_score(item)
    return score


def _category_affinities(cid: int) -> dict[str, float]:
    """Learn bounded category preferences from recent explicit/implicit feedback.

    One grouped query is executed only when a new feed session is ranked. Existing
    session pagination does not call this function, so normal scrolling stays cheap.
    """
    try:
        rows = fetch_all(
            """SELECT category, SUM(weight) AS score
                 FROM (
                   SELECT p.content_category AS category, rs.weight
                     FROM recommendation_signals rs
                     JOIN posts p ON p.post_id = rs.source_id
                    WHERE rs.child_id = %s
                      AND rs.source_type = 'SOCIAL'
                      AND rs.created_at >= NOW() - INTERVAL '30 days'
                   UNION ALL
                   SELECT cat.display_name AS category, rs.weight
                     FROM recommendation_signals rs
                     JOIN curated_content cc ON cc.content_id = rs.source_id
                     JOIN content_categories cat ON cat.category_id = cc.category_id
                    WHERE rs.child_id = %s
                      AND rs.source_type = 'CURATED'
                      AND rs.created_at >= NOW() - INTERVAL '30 days'
                 ) recent
                WHERE category IS NOT NULL
                GROUP BY category""",
            (cid, cid),
        )
    except Exception:
        return {}

    affinities: dict[str, float] = {}
    for row in rows or []:
        category = str(row.get("category") or "").strip().casefold()
        if not category:
            continue
        try:
            raw = float(row.get("score") or 0.0)
        except (TypeError, ValueError):
            continue
        # Saturate at +/-3 so a long interaction history cannot overpower safety,
        # profile interests, freshness, or diversity.
        affinities[category] = 3.0 * math.tanh(raw / 8.0)
    return affinities


def _feedback_bonus(item: dict[str, Any], feedback: dict[tuple[str, int], float]) -> float:
    source_id = int(item.get("source_id", item.get("post_id", 0)) or 0)
    source_type = str(item.get("source_type") or "SOCIAL").upper()
    creator_id = int((item.get("ranking_metadata") or {}).get("child_id") or 0)
    raw = (
        feedback.get((source_type, source_id), 0.0)
        + feedback.get(("CREATOR", creator_id), 0.0)
    )
    # Strong negative actions remain strong, but repeated positive interactions
    # cannot make one creator/item permanently dominate the feed.
    return 6.0 * math.tanh(float(raw) / 6.0)


def _composite_rank_score(
    item: dict[str, Any],
    terms: list[str],
    feedback: dict[tuple[str, int], float],
    category_affinities: dict[str, float],
    ai_scores: dict[int, float],
) -> float:
    source_id = int(item.get("source_id", item.get("post_id", 0)) or 0)
    category = str(item.get("category") or item.get("content_category") or "").strip().casefold()
    semantic = max(-1.0, min(1.0, float(ai_scores.get(source_id, 0.0))))
    return (
        _fallback_score(item, terms)
        + _feedback_bonus(item, feedback)
        + category_affinities.get(category, 0.0)
        + (2.0 * semantic)
    )


def rank_candidates(cid: int, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    rows = _safe_rank_candidates(cid, rows)
    if not rows:
        return []
    terms, profile_text = _profile_terms(cid)
    feedback = signal_scores(cid, rows)
    category_affinities = _category_affinities(cid)
    ai_scores: dict[int, float] = {}
    try:
        from safety import remote_client

        if remote_client.enabled():
            # remote_client.rank_texts() is itself guarded by AI_ENABLE_REMOTE_RANKING=0
            # by default, so normal feed requests do not wake the Modal T4.
            ranked = remote_client.rank_texts(
                profile_text,
                [{"id": p.get("source_id", p.get("post_id")), "text": _text_for(p)} for p in rows],
            )
            ai_scores = {int(x["id"]): float(x["score"]) for x in ranked}
        elif _flag("LITTLENET_ENABLE_LOCAL_RECOMMENDATION_MODEL", False):
            # Local CLIP ranking is also opt-in. The default web path stays lightweight
            # and avoids loading PyTorch/Transformers solely for recommendations.
            from safety.semantic_service import rank_texts

            scores = rank_texts(profile_text, [_text_for(p) for p in rows])
            ai_scores = {int(p.get("source_id", p.get("post_id"))): float(score) for p, score in zip(rows, scores)}
    except Exception:
        # Personalization is not a safety gate. Safe deterministic ranking remains available.
        ai_scores = {}

    return sorted(
        rows,
        key=lambda p: (
            _composite_rank_score(p, terms, feedback, category_affinities, ai_scores),
            p.get("ranking_metadata", {}).get("created_at") or p.get("created_at") or "",
        ),
        reverse=True,
    )


def _safe_rank_candidates(cid: int, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Re-apply publication, age, and Parent Mode gates before ranking."""
    cats = set(effective_categories(cid))
    age_group = _age_group(cid)
    real_age = _child_real_age(cid)
    creator_ids = {
        int((item.get("ranking_metadata") or {}).get("child_id"))
        for item in rows
        if (item.get("ranking_metadata") or {}).get("child_id") is not None
    }
    blocked_ids = set()
    if creator_ids:
        try:
            blocked_rows = fetch_all(
                """SELECT blocked_id AS creator_id FROM blocked_users
                   WHERE blocker_id=%s AND blocked_id=ANY(%s)
                   UNION
                   SELECT blocker_id AS creator_id FROM blocked_users
                   WHERE blocked_id=%s AND blocker_id=ANY(%s)
                   UNION
                   SELECT muted_id AS creator_id FROM muted_users
                   WHERE muter_id=%s AND muted_id=ANY(%s)""",
                (cid, list(creator_ids), cid, list(creator_ids), cid, list(creator_ids)),
            )
            blocked_ids = {int(row["creator_id"]) for row in blocked_rows or [] if row.get("creator_id") is not None}
        except Exception:
            blocked_ids = set()
    hidden = hidden_items(cid, rows)
    eligible = []
    for item in rows:
        key = _item_key(item)
        if key is not None and key in hidden:
            continue
        if str(item.get("moderation_status") or "").upper() != "ALLOWED":
            continue
        if item.get("is_safe") is not True:
            continue
        creator_id = (item.get("ranking_metadata") or {}).get("child_id")
        if creator_id is not None and int(creator_id) in blocked_ids:
            continue
        category = item.get("category") or item.get("content_category")
        if category not in cats:
            continue
        audience = str(item.get("audience_age_group") or "ALL")
        if age_group and audience not in {"ALL", age_group}:
            continue
        try:
            if not (int(item.get("min_age", 4)) <= real_age <= int(item.get("max_age", 18))):
                continue
        except (TypeError, ValueError):
            continue
        eligible.append(item)
    return eligible


def apply_diversity_and_balance(ranked_items: list[dict[str, Any]], max_consecutive: int = 2) -> list[dict[str, Any]]:
    """Enforces category diversity and guarantees educational balance in Kids feed."""
    return apply_category_diversity(ranked_items, max_consecutive=max_consecutive)


def personalized_posts(cid: int, limit: int = 30, offset: int = 0) -> list[dict[str, Any]]:
    rows = candidates(cid, max(60, limit + offset + 20))
    ranked = rank_candidates(cid, rows)
    balanced = apply_diversity_and_balance(ranked)
    return balanced[offset : offset + limit]
