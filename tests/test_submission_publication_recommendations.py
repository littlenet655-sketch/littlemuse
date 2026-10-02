from pathlib import Path

from services import publication_lifecycle
from services.curated_feed import _materialize_session_items, fetch_social_candidates
from services.recommendation import _safe_rank_candidates


def test_ranking_filters_review_block_and_parent_age_before_scoring(monkeypatch):
    monkeypatch.setattr("services.recommendation.effective_categories", lambda _cid: ["Science"])
    monkeypatch.setattr("services.recommendation._age_group", lambda _cid: "9-11")
    monkeypatch.setattr("services.recommendation._child_real_age", lambda _cid: 10)
    monkeypatch.setattr("services.recommendation.fetch_all", lambda *_args, **_kwargs: [])
    rows = [
        {"source_type": "SOCIAL", "source_id": 1, "category": "Science",
         "moderation_status": "ALLOWED", "is_safe": True, "audience_age_group": "9-11"},
        {"source_type": "SOCIAL", "source_id": 2, "category": "Science",
         "moderation_status": "REVIEW", "is_safe": False, "audience_age_group": "9-11"},
        {"source_type": "SOCIAL", "source_id": 3, "category": "Science",
         "moderation_status": "BLOCKED", "is_safe": False, "audience_age_group": "9-11"},
        {"source_type": "SOCIAL", "source_id": 4, "category": "Science",
         "moderation_status": "ALLOWED", "is_safe": True, "audience_age_group": "14-18"},
        {"source_type": "SOCIAL", "source_id": 5, "category": "Sports",
         "moderation_status": "ALLOWED", "is_safe": True, "audience_age_group": "9-11"},
    ]
    assert [row["source_id"] for row in _safe_rank_candidates(7, rows)] == [1]


def test_allow_refresh_invalidates_feed_and_reel_sessions(monkeypatch):
    calls = []
    monkeypatch.setattr(publication_lifecycle, "execute", lambda sql, params: calls.append((sql, params)))
    assert publication_lifecycle.refresh_publication_visibility(42, 9, is_reel=True)
    assert "DELETE FROM feed_session_items" in calls[0][0]
    assert "DELETE FROM feed_sessions" in calls[1][0]
    assert calls[1][1] == (True,)


def test_review_is_creator_private_and_block_has_no_public_visibility_predicate():
    source = (Path(__file__).parents[1] / "services" / "social.py").read_text(encoding="utf-8")
    assert "p.moderation_status='ALLOWED' AND p.is_safe=TRUE" in source
    assert "(p.child_id=%s AND p.moderation_status='REVIEW')" in source
    visibility = source.split("def post_visible_to", 1)[1].split("def visible_profile_posts", 1)[0]
    assert "p.moderation_status='BLOCKED'" not in visibility


def test_reels_candidates_use_discoverability_boundary(monkeypatch):
    import child.service as child_service
    import services.curated_feed as curated

    monkeypatch.setattr(child_service, "discoverable_child_ids", lambda _cid: [42])
    monkeypatch.setattr(curated, "effective_categories", lambda _cid: ["Science"])
    monkeypatch.setattr(curated, "_age_group", lambda _cid: "9-11")
    seen = {}
    monkeypatch.setattr(curated, "fetch_all", lambda sql, params: seen.update(sql=sql, params=params) or [])
    assert fetch_social_candidates(7, surface="REELS") == []
    assert "p.child_id = ANY(%s::int[])" in seen["sql"]
    assert [42] in seen["params"]


def test_persisted_session_hydration_rechecks_current_visibility(monkeypatch):
    import child.service as child_service
    import services.curated_feed as curated

    monkeypatch.setattr(curated, "controls_for_child", lambda _cid: {"allow_reels": True})
    monkeypatch.setattr(curated, "effective_categories", lambda _cid: ["Science"])
    monkeypatch.setattr(curated, "_age_group", lambda _cid: "9-11")
    monkeypatch.setattr(curated, "_child_real_age", lambda _cid: 10)
    monkeypatch.setattr(child_service, "discoverable_child_ids", lambda _cid: [42])
    social_rows = [
        {"post_id": 1, "child_id": 42, "content_category": "Science", "media_type": "IMAGE",
         "media_path": "uploads/r2/posts/1.jpg", "is_reel": True, "is_story": False,
         "audience_age_group": "9-11", "moderation_status": "ALLOWED", "is_safe": True},
        {"post_id": 2, "child_id": 99, "content_category": "Science", "media_type": "IMAGE",
         "media_path": "uploads/r2/posts/2.jpg", "is_reel": True, "is_story": False,
         "audience_age_group": "9-11", "moderation_status": "ALLOWED", "is_safe": True},
        {"post_id": 3, "child_id": 42, "content_category": "Sports", "media_type": "IMAGE",
         "media_path": "uploads/r2/posts/3.jpg", "is_reel": True, "is_story": False,
         "audience_age_group": "9-11", "moderation_status": "ALLOWED", "is_safe": True},
    ]

    def fake_fetch(sql, _params):
        if "FROM posts" in sql:
            return social_rows
        if "blocked_users" in sql:
            return [{"creator_id": 99}]
        return []

    monkeypatch.setattr(curated, "fetch_all", fake_fetch)
    raw = [{"source_type": "SOCIAL", "source_id": 1},
           {"source_type": "SOCIAL", "source_id": 2},
           {"source_type": "SOCIAL", "source_id": 3}]
    hydrated = _materialize_session_items(raw, child_id=7, surface="REELS")
    assert [item["post_id"] for item in hydrated] == [1]


def test_mobile_review_approval_refreshes_text_posts_after_commit():
    source = (Path(__file__).parents[1] / "mobile" / "api.py").read_text(encoding="utf-8")
    approval = source.split("# Commit DB state FIRST", 1)[1].split("return True, requested", 1)[0]
    assert "if p_row:" in approval
    assert "refresh_publication_visibility" in approval
    assert "if p_row.get(\"source_media_path\"):" in approval