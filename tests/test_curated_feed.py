"""Comprehensive tests for the curated content and merged feed recommendation architecture."""
from __future__ import annotations

import pytest

from services.curated_feed import (
    apply_category_diversity,
    authorize_curated_media,
    fetch_curated_candidates,
    fetch_social_candidates,
    get_feed_page,
    merge_candidates,
    normalize_curated_item,
    normalize_social_item,
    record_feed_impression,
    search_curated_content,
)
from services.recommendation import candidates, personalized_posts


def _dummy_curated_row(
    content_id=1,
    title="Soil Science",
    category="Science & Gardening",
    category_slug="gardening",
    is_educational=True,
    min_age=4,
    max_age=18,
    audience="ALL",
    publish_status="PUBLISHED",
    moderation_status="ALLOWED",
    is_safe=True,
    is_reel=False,
    delivery_key="curated/v1/gardening/ab/test.jpg",
):
    return {
        "content_id": content_id,
        "creator_id": 7,
        "creator_display_name": "AIT Star Student",
        "creator_username": "ait_star_student",
        "creator_avatar_reference": None,
        "title": title,
        "caption": f"Educational content {title}",
        "audience_age_group": audience,
        "min_age": min_age,
        "max_age": max_age,
        "is_reel": is_reel,
        "editorial_weight": 1.0,
        "published_at": "2026-09-08T12:00:00Z",
        "asset_id": "00000000-0000-0000-0000-000000000001",
        "media_type": "IMAGE",
        "delivery_object_key": delivery_key,
        "original_object_key": delivery_key,
        "poster_object_key": None,
        "thumbnail_object_key": None,
        "mime_type": "image/jpeg",
        "width": 1024,
        "height": 768,
        "duration_seconds": None,
        "file_size_bytes": 100000,
        "moderation_status": moderation_status,
        "is_safe": is_safe,
        "category_id": 1,
        "category_slug": category_slug,
        "category": category,
        "category_active": True,
        "is_educational": is_educational,
        "publish_status": publish_status,
    }


def _dummy_social_row(post_id=101, category="Nature & Animals", is_reel=False):
    return {
        "post_id": post_id,
        "child_id": 42,
        "content_category": category,
        "caption": "My pet rabbit eating carrots",
        "media_type": "IMAGE",
        "media_path": "uploads/r2/posts/rabbit.jpg",
        "is_reel": is_reel,
        "is_story": False,
        "audience_age_group": "ALL",
        "moderation_status": "ALLOWED",
        "is_safe": True,
        "full_name": "Alice Friend",
        "profile_picture": None,
        "likes": 5,
        "comments_count": 2,
        "is_following": True,
        "created_at": "2026-09-08T10:00:00Z",
    }


def test_empty_social_graph_returns_curated_content(monkeypatch):
    """A child with zero social connections must still receive safe curated content."""
    child_id = 15

    # Mock empty social connections
    import child.service as cs

    monkeypatch.setattr(cs, "discoverable_child_ids", lambda cid: [])

    # Mock effective categories and age
    import services.curated_feed as cf

    monkeypatch.setattr(cf, "effective_categories", lambda cid: ["Science & Gardening", "Nature & Animals"])
    monkeypatch.setattr(cf, "_child_real_age", lambda cid: 10)
    monkeypatch.setattr(cf, "_age_group", lambda cid: "9-11")

    # Mock database returning published curated items
    sample_curated = [
        _dummy_curated_row(content_id=1, title="Earthworms at Work", category="Science & Gardening"),
        _dummy_curated_row(content_id=2, title="Honeybee Pollination", category="Nature & Animals"),
    ]
    monkeypatch.setattr(cf, "fetch_all", lambda sql, params: sample_curated)

    social_candidates = fetch_social_candidates(child_id, surface="FEED")
    assert social_candidates == [], "Social candidates must be empty for 0-friend child"

    curated_candidates = fetch_curated_candidates(child_id, surface="FEED")
    assert len(curated_candidates) == 2
    assert curated_candidates[0]["source_type"] == "CURATED"
    assert curated_candidates[0]["source_id"] == 1

    # Merged candidates must not be empty!
    all_candidates = candidates(child_id, surface="FEED")
    assert len(all_candidates) == 2
    assert all_candidates[0]["source_type"] == "CURATED"


def test_legacy_missing_media_is_not_rendered_as_a_broken_feed_tile(monkeypatch):
    import services.curated_feed as cf

    valid=normalize_social_item(_dummy_social_row(1))
    assert cf._social_media_renderable(valid) is True

    missing=normalize_social_item({**_dummy_social_row(2), "media_path": "uploads/legacy/missing.jpg"})
    monkeypatch.setattr(cf.os.path, "exists", lambda path: False)
    assert cf._social_media_renderable(missing) is False

    stale=normalize_social_item({**_dummy_social_row(3), "media_path": "posts/clean.jpg"})
    assert cf._social_media_renderable(stale) is False

    text_post=normalize_social_item({**_dummy_social_row(4), "media_type": "TEXT", "media_path": None})
    assert cf._social_media_renderable(text_post) is True


def test_curated_identity_is_hydrated_from_editorial_relation():
    row = _dummy_curated_row(content_id=10)
    item = normalize_curated_item(row)
    assert item["source_type"] == "CURATED"
    assert item["creator_id"] == 7
    assert item["creator_username"] == "ait_star_student"
    assert item["author_name"] == "AIT Star Student"
    assert item.get("child_id") is None


def test_curated_creator_migration_uses_relational_creator_id():
    migration = (ROOT / "db/migrations/20260924000002_curated_creators_engagement.sql").read_text(encoding="utf-8")
    service = (ROOT / "services/curated_feed.py").read_text(encoding="utf-8")
    assert "creator_id BIGSERIAL PRIMARY KEY" in migration
    assert "ADD COLUMN IF NOT EXISTS creator_id BIGINT REFERENCES curated_creators(creator_id)" in migration
    assert "JOIN curated_creators cr ON cr.creator_id = cc.creator_id" in service
    assert "creator_payload" not in service
    assert '"creator_id": int(creator_id)' in service


def test_social_and_curated_merge(monkeypatch):
    """When both social and curated items exist, they are merged in a balanced feed."""
    social_items = [normalize_social_item(_dummy_social_row(1)), normalize_social_item(_dummy_social_row(2))]
    curated_items = [normalize_curated_item(_dummy_curated_row(10)), normalize_curated_item(_dummy_curated_row(11))]

    merged = merge_candidates(social_items, curated_items)
    assert len(merged) == 4
    source_types = [item["source_type"] for item in merged]
    assert "SOCIAL" in source_types
    assert "CURATED" in source_types


def test_category_diversity_max_two_consecutive():
    """No more than 2 consecutive items from the same category when alternatives exist."""
    items = [
        {"category": "Gardening", "id": 1},
        {"category": "Gardening", "id": 2},
        {"category": "Gardening", "id": 3},
        {"category": "Animals", "id": 4},
        {"category": "Animals", "id": 5},
    ]
    balanced = apply_category_diversity(items, max_consecutive=2)
    categories = [b["category"] for b in balanced]

    # Verify no 3 consecutive identical categories
    for i in range(len(categories) - 2):
        assert not (categories[i] == categories[i + 1] == categories[i + 2]), f"Violated at index {i}: {categories}"


def test_blocked_and_unapproved_curated_media_rejected(monkeypatch):
    """Curated media authorization strictly rejects BLOCKED, REVIEW, PENDING, and unpublished media."""
    import services.curated_feed as cf

    monkeypatch.setattr(cf, "child_surface_open", lambda cid: True)
    monkeypatch.setattr(cf, "effective_categories", lambda cid: ["Science & Gardening"])
    monkeypatch.setattr(cf, "_child_real_age", lambda cid: 10)

    # 1. Blocked asset
    blocked_row = _dummy_curated_row(content_id=99, moderation_status="BLOCKED", is_safe=False)
    monkeypatch.setattr(cf, "fetch_one", lambda sql, params: blocked_row)
    with pytest.raises(PermissionError, match="content_blocked_or_unapproved"):
        authorize_curated_media(child_id=1, content_id=99)

    # 2. Review status
    review_row = _dummy_curated_row(content_id=98, moderation_status="REVIEW", is_safe=False)
    monkeypatch.setattr(cf, "fetch_one", lambda sql, params: review_row)
    with pytest.raises(PermissionError, match="content_blocked_or_unapproved"):
        authorize_curated_media(child_id=1, content_id=98)

    # 3. Draft / unpublished
    draft_row = _dummy_curated_row(content_id=97, publish_status="DRAFT")
    monkeypatch.setattr(cf, "fetch_one", lambda sql, params: draft_row)
    with pytest.raises(PermissionError, match="content_not_published"):
        authorize_curated_media(child_id=1, content_id=97)

    # 4. Age ineligible (child is 10, content is 14-18)
    age_row = _dummy_curated_row(content_id=96, min_age=14, max_age=18)
    monkeypatch.setattr(cf, "fetch_one", lambda sql, params: age_row)
    with pytest.raises(PermissionError, match="age_ineligible"):
        authorize_curated_media(child_id=1, content_id=96)

    # 5. Parent-disabled category
    cat_row = _dummy_curated_row(content_id=95, category="Cooking")
    monkeypatch.setattr(cf, "fetch_one", lambda sql, params: cat_row)
    with pytest.raises(PermissionError, match="category_restricted_by_parent"):
        authorize_curated_media(child_id=1, content_id=95)


def test_impression_recording_requires_valid_session_item(monkeypatch):
    """Impression recording fails if item was not part of the active feed session."""
    import services.curated_feed as cf

    # Mock invalid session validation query
    monkeypatch.setattr(cf, "fetch_one", lambda sql, params: None)
    recorded = record_feed_impression(
        child_id=5,
        session_id="00000000-0000-0000-0000-000000000001",
        source_type="CURATED",
        source_id=999,
        surface="FEED",
    )
    assert recorded is False, "Untrusted source_id not in session must be rejected"

    # Mock valid session validation query
    monkeypatch.setattr(cf, "fetch_one", lambda sql, params: {"1": 1})
    executed = []
    monkeypatch.setattr(cf, "execute", lambda sql, params: executed.append((sql, params)))

    recorded_ok = record_feed_impression(
        child_id=5,
        session_id="00000000-0000-0000-0000-000000000001",
        source_type="CURATED",
        source_id=1,
        surface="FEED",
        watched_ms=1500,
        completed=True,
    )
    assert recorded_ok is True
    assert len(executed) == 1
    assert "INSERT INTO content_impressions" in executed[0][0]


def test_search_curated_content_safely(monkeypatch):
    """Search returns only published, allowed, safe curated content matching terms."""
    import services.curated_feed as cf

    monkeypatch.setattr(cf, "effective_categories", lambda cid: ["Science & Gardening"])
    monkeypatch.setattr(cf, "_child_real_age", lambda cid: 10)

    matched_rows = [
        _dummy_curated_row(content_id=1, title="Garden Friends: Earthworms at Work"),
    ]
    monkeypatch.setattr(cf, "fetch_all", lambda sql, params: matched_rows)

    results = search_curated_content(child_id=3, query="earthworms", limit=10)
    assert len(results) == 1
    assert results[0]["source_id"] == 1
    assert "Earthworms" in results[0]["title"]


def test_feed_session_cursor_pagination(monkeypatch):
    """Cursor advances through session items with correct next_cursor and has_more values."""
    import services.curated_feed as cf

    # Mock get_or_create_feed_session to return 5 items
    dummy_items = [normalize_curated_item(_dummy_curated_row(i)) for i in range(1, 6)]
    monkeypatch.setattr(cf, "get_or_create_feed_session", lambda cid, surf, sess: ("test-sess-uuid", dummy_items))
    monkeypatch.setattr(cf, "_has_refill_candidates", lambda cid, surf, sess, mode: False)

    # Page 1: cursor=0, limit=2
    p1 = get_feed_page(child_id=1, surface="FEED", cursor=0, limit=2)
    assert len(p1["items"]) == 2
    assert p1["cursor"] == 0
    assert p1["next_cursor"] == 2
    assert p1["has_more"] is True

    # Page 2: cursor=2, limit=2
    p2 = get_feed_page(child_id=1, surface="FEED", cursor=2, limit=2)
    assert len(p2["items"]) == 2
    assert p2["cursor"] == 2
    assert p2["next_cursor"] == 4
    assert p2["has_more"] is True

    # Page 3: cursor=4, limit=2 (only 1 item remaining)
    p3 = get_feed_page(child_id=1, surface="FEED", cursor=4, limit=2)
    assert len(p3["items"]) == 1
    assert p3["cursor"] == 4
    assert p3["next_cursor"] is None
    assert p3["has_more"] is False




def test_feed_session_boundary_can_advertise_safe_refill(monkeypatch):
    import services.curated_feed as cf

    dummy_items = [normalize_curated_item(_dummy_curated_row(i)) for i in range(1, 4)]
    monkeypatch.setattr(cf, "get_or_create_feed_session", lambda cid, surf, sess: ("sess-a", dummy_items))
    monkeypatch.setattr(cf, "_has_refill_candidates", lambda cid, surf, sess, mode: True)

    page = get_feed_page(child_id=1, surface="FEED", cursor=0, limit=10)
    assert page["has_more"] is False
    assert page["can_refill"] is True
    assert page["exhaustion_reason"] == "SESSION_END"
    assert all(item["feed_session_id"] == "sess-a" for item in page["items"])


def test_refill_session_excludes_immediately_previous_session(monkeypatch):
    import services.curated_feed as cf

    previous = {("CURATED", 1), ("SOCIAL", 2)}
    monkeypatch.setattr(cf, "_session_source_keys", lambda cid, surf, sid: previous if sid == "old-sess" else set())
    monkeypatch.setattr(cf, "fetch_curated_candidates", lambda cid, surf, limit=60: [
        normalize_curated_item(_dummy_curated_row(1)),
        normalize_curated_item(_dummy_curated_row(3)),
    ])
    monkeypatch.setattr(cf, "fetch_social_candidates", lambda cid, surf, limit=60: [
        normalize_social_item(_dummy_social_row(2)),
        normalize_social_item(_dummy_social_row(4)),
    ])
    monkeypatch.setattr(cf, "get_recent_impression_keys", lambda *a, **k: set())

    import services.recommendation as rec
    monkeypatch.setattr(rec, "rank_candidates", lambda cid, rows: rows)
    monkeypatch.setattr(rec, "apply_diversity_and_balance", lambda rows, max_consecutive=2: rows)

    writes = []
    monkeypatch.setattr(cf, "execute", lambda sql, params=(), returning=False: {"session_id": "new-sess"} if returning else writes.append((sql, params)))

    class _Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): return False
    class _Conn:
        def cursor(self): return _Cursor()
        def commit(self): pass
        def rollback(self): pass
        def close(self): pass

    monkeypatch.setattr(cf, "get_db_connection", lambda: _Conn())
    monkeypatch.setattr("psycopg2.extras.execute_values", lambda cur, sql, records: writes.append((sql, records)))

    sess, rows = cf.get_or_create_feed_session(1, "FEED", None, exclude_session_id="old-sess")
    keys = {(r["source_type"], int(r["source_id"])) for r in rows}
    assert sess == "new-sess"
    assert ("CURATED", 1) not in keys
    assert ("SOCIAL", 2) not in keys
    assert ("CURATED", 3) in keys
    assert ("SOCIAL", 4) in keys
