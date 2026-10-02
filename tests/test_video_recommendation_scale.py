import time
import pytest
from unittest.mock import MagicMock, patch
from services.object_storage import get_playback_ttl
from services.media_delivery import resolve_media_delivery
from services.recommendation_signals import signal_scores
from services.recommendation import rank_candidates
from services.curated_feed import apply_category_diversity


# ---------------------------------------------------------------------------
# 1. P0 Signed URL TTL Consistency
# ---------------------------------------------------------------------------

def test_playback_ttl_clamping_and_consistency(monkeypatch):
    monkeypatch.delenv('R2_SIGNED_URL_TTL', raising=False)
    # Default is 600 (authoritative 10-minute maximum)
    assert get_playback_ttl() == 600
    # Clamping bounds: 60s min, 600s max
    assert get_playback_ttl(10) == 60
    assert get_playback_ttl(59) == 60
    assert get_playback_ttl(60) == 60
    assert get_playback_ttl(450) == 450
    assert get_playback_ttl(600) == 600
    assert get_playback_ttl(1200) == 600

    # With env override
    monkeypatch.setenv('R2_SIGNED_URL_TTL', '180')
    assert get_playback_ttl() == 180
    monkeypatch.setenv('R2_SIGNED_URL_TTL', '50')
    assert get_playback_ttl() == 60
    monkeypatch.setenv('R2_SIGNED_URL_TTL', '1000')
    assert get_playback_ttl() == 600


def test_resolve_media_delivery_ttl_matches_effective_ttl(monkeypatch):
    monkeypatch.setenv('R2_SIGNED_URL_TTL', '300')
    
    with patch('services.media_delivery.r2_enabled', return_value=True), \
         patch('services.media_delivery.is_authorized_viewer', return_value=True), \
         patch('services.media_delivery.signed_download_url') as mock_sign:
        
        mock_sign.return_value = 'https://r2.example.com/signed-url'
        
        now = int(time.time())
        info = resolve_media_delivery(
            'uploads/r2/posts/1/2/video.mp4',
            viewer_id=10,
            viewer_role='CHILD',
            expires_seconds=300
        )
        
        assert info['delivery_mode'] == 'DIRECT_SIGNED'
        assert info['url'] == 'https://r2.example.com/signed-url'
        # Effective TTL should be 300, and expires_at strictly matches now + effective_ttl
        mock_sign.assert_called_once_with('uploads/r2/posts/1/2/video.mp4', expires_seconds=300)
        assert abs(info['expires_at'] - (now + 300)) <= 2


# ---------------------------------------------------------------------------
# 2. P4 / Step 13 Curated Feedback & Signal Scores
# ---------------------------------------------------------------------------

def test_signal_scores_includes_curated_feedback():
    with patch('services.recommendation_signals.fetch_all') as mock_fetch:
        mock_fetch.return_value = [
            {'source_type': 'CURATED', 'source_id': 101, 'score': 5.5},
            {'source_type': 'CURATED', 'source_id': 102, 'score': -4.0},
            {'source_type': 'SOCIAL', 'source_id': 201, 'score': 1.5},
        ]
        
        items = [
            {'source_type': 'CURATED', 'source_id': 101},
            {'source_type': 'CURATED', 'source_id': 102},
            {'source_type': 'SOCIAL', 'source_id': 201},
        ]
        
        scores = signal_scores(child_id=42, items=items)
        
        assert scores[('CURATED', 101)] == 5.5
        assert scores[('CURATED', 102)] == -4.0
        assert scores[('SOCIAL', 201)] == 1.5


def test_rank_candidates_evaluates_curated_feedback():
    candidates = [
        {
            'source_type': 'CURATED',
            'source_id': 101,
            'content_id': 101,
            'title': 'Fun Physics',
            'caption': 'Learn gravity',
            'category': 'science',
            'created_at': '2026-09-19T00:00:00Z',
        },
        {
            'source_type': 'CURATED',
            'source_id': 102,
            'content_id': 102,
            'title': 'Boring Stuff',
            'caption': 'Skip this',
            'category': 'science',
            'created_at': '2026-09-19T00:00:00Z',
        },
    ]
    
    with patch('services.recommendation._safe_rank_candidates', side_effect=lambda cid, r: r), \
         patch('services.recommendation.signal_scores') as mock_signals, \
         patch('services.recommendation._profile_terms', return_value=(['science'], 'context')):
        
        mock_signals.return_value = {
            ('CURATED', 101): 5.0,   # Positive curated affinity
            ('CURATED', 102): -5.0,  # Negative curated affinity
        }
        
        ranked = rank_candidates(cid=42, rows=candidates)
        
        assert len(ranked) == 2
        # Positively engaged curated item 101 should rank ahead of negative 102
        assert ranked[0]['source_id'] == 101
        assert ranked[1]['source_id'] == 102


def test_rank_candidates_does_not_load_local_clip_by_default(monkeypatch):
    monkeypatch.delenv('LITTLENET_ENABLE_LOCAL_RECOMMENDATION_MODEL', raising=False)
    rows = [
        {
            'source_type': 'CURATED',
            'source_id': 1,
            'content_id': 1,
            'title': 'Space science',
            'caption': 'Planets and stars',
            'category': 'science',
            'moderation_status': 'ALLOWED',
            'is_safe': True,
        }
    ]

    with patch('services.recommendation._safe_rank_candidates', side_effect=lambda cid, r: r), \
         patch('services.recommendation.signal_scores', return_value={}), \
         patch('services.recommendation._profile_terms', return_value=(['science'], 'science')), \
         patch('safety.remote_client.enabled', return_value=False), \
         patch('safety.semantic_service.rank_texts') as local_rank:
        ranked = rank_candidates(cid=42, rows=rows)

    assert ranked[0]['source_id'] == 1
    local_rank.assert_not_called()


def test_cpu_fallback_prefers_fresh_relevant_content(monkeypatch):
    rows = [
        {
            'source_type': 'CURATED',
            'source_id': 1,
            'content_id': 1,
            'title': 'Science experiment',
            'caption': 'Fun science',
            'category': 'science',
            'created_at': '2026-09-20T00:00:00Z',
            'ranking_metadata': {'editorial_weight': 1.0, 'likes': 5, 'comments_count': 2},
        },
        {
            'source_type': 'CURATED',
            'source_id': 2,
            'content_id': 2,
            'title': 'Science experiment',
            'caption': 'Fun science',
            'category': 'science',
            'created_at': '2025-01-01T00:00:00Z',
            'ranking_metadata': {'editorial_weight': 1.0, 'likes': 5, 'comments_count': 2},
        },
    ]

    with patch('services.recommendation._safe_rank_candidates', side_effect=lambda cid, r: r), \
         patch('services.recommendation.signal_scores', return_value={}), \
         patch('services.recommendation._profile_terms', return_value=(['science'], 'science')), \
         patch('safety.remote_client.enabled', return_value=True), \
         patch('safety.remote_client.rank_texts', return_value=[]):
        ranked = rank_candidates(cid=42, rows=rows)

    assert ranked[0]['source_id'] == 1



def test_recent_category_feedback_personalizes_unseen_items():
    from services.recommendation import _category_affinities

    with patch('services.recommendation.fetch_all') as mock_fetch:
        mock_fetch.return_value = [
            {'category': 'Science', 'score': 8.0},
            {'category': 'Art', 'score': -8.0},
        ]
        affinities = _category_affinities(42)

    assert affinities['science'] > 2.0
    assert affinities['art'] < -2.0
    assert max(abs(value) for value in affinities.values()) <= 3.0


def test_rank_candidates_uses_behavior_category_affinity(monkeypatch):
    rows = [
        {
            'source_type': 'CURATED',
            'source_id': 11,
            'content_id': 11,
            'title': 'New lesson',
            'caption': '',
            'category': 'science',
            'created_at': '2026-09-20T00:00:00Z',
        },
        {
            'source_type': 'CURATED',
            'source_id': 12,
            'content_id': 12,
            'title': 'New lesson',
            'caption': '',
            'category': 'art',
            'created_at': '2026-09-20T00:00:00Z',
        },
    ]

    with patch('services.recommendation._safe_rank_candidates', side_effect=lambda cid, r: r), \
         patch('services.recommendation.signal_scores', return_value={}), \
         patch('services.recommendation._profile_terms', return_value=([], 'safe content')), \
         patch('services.recommendation._category_affinities', return_value={'science': 2.5, 'art': -1.0}), \
         patch('safety.remote_client.enabled', return_value=True), \
         patch('safety.remote_client.rank_texts', return_value=[]):
        ranked = rank_candidates(cid=42, rows=rows)

    assert ranked[0]['source_id'] == 11


def test_item_feedback_is_bounded_not_lexicographically_absolute(monkeypatch):
    rows = [
        {
            'source_type': 'SOCIAL',
            'source_id': 21,
            'post_id': 21,
            'title': 'Generic post',
            'caption': '',
            'category': 'general',
            'created_at': '2026-09-20T00:00:00Z',
            'ranking_metadata': {'child_id': 5},
        },
        {
            'source_type': 'SOCIAL',
            'source_id': 22,
            'post_id': 22,
            'title': 'Robotics science project',
            'caption': 'Robotics science coding',
            'category': 'science',
            'created_at': '2026-09-20T00:00:00Z',
            'ranking_metadata': {'child_id': 6},
        },
    ]

    with patch('services.recommendation._safe_rank_candidates', side_effect=lambda cid, r: r), \
         patch('services.recommendation.signal_scores', return_value={('SOCIAL', 21): 1.5}), \
         patch('services.recommendation._profile_terms', return_value=(['robotics', 'science', 'coding'], 'robotics science coding')), \
         patch('services.recommendation._category_affinities', return_value={}), \
         patch('safety.remote_client.enabled', return_value=True), \
         patch('safety.remote_client.rank_texts', return_value=[]):
        ranked = rank_candidates(cid=42, rows=rows)

    # A small past engagement signal must not permanently outrank a much more
    # relevant unseen item, unlike the old lexicographic feedback tuple.
    assert ranked[0]['source_id'] == 22


# ---------------------------------------------------------------------------
# 3. P8 Diversity and Balance Reranking
# ---------------------------------------------------------------------------

def test_apply_category_diversity_enforces_max_consecutive_categories():
    items = [
        {'source_type': 'social', 'source_id': 1, 'category': 'gaming'},
        {'source_type': 'social', 'source_id': 2, 'category': 'gaming'},
        {'source_type': 'social', 'source_id': 3, 'category': 'gaming'},
        {'source_type': 'social', 'source_id': 4, 'category': 'science'},
        {'source_type': 'social', 'source_id': 5, 'category': 'art'},
    ]
    
    balanced = apply_category_diversity(items, max_consecutive=2)
    categories = [it['category'] for it in balanced]
    
    # Should never have 3 consecutive gaming items
    for i in range(len(categories) - 2):
        assert not (categories[i] == 'gaming' and categories[i+1] == 'gaming' and categories[i+2] == 'gaming')


# ---------------------------------------------------------------------------
# 4. P10 Batch Impression Validation
# ---------------------------------------------------------------------------

def test_batch_impressions_contract(monkeypatch):
    from flask import Blueprint, Flask
    from mobile.api import register_mobile_api, _issue_token
    
    app = Flask(__name__)
    app.secret_key = "test-secret"
    bp = Blueprint("mobile_test", __name__)
    register_mobile_api(bp)
    app.register_blueprint(bp)
    
    user = {"user_id": 202, "role": "CHILD", "account_status": "ACTIVE", "full_name": "Test Child"}
    token = _issue_token(user)
    monkeypatch.setattr("mobile.api.fetch_one", lambda query, params=(): user if "FROM users" in query else None)
    monkeypatch.setattr("mobile.api._child_gate", lambda *args, **kwargs: None)
    
    with app.test_client() as client:
        # Without auth -> 401
        res = client.post('/api/mobile/v2/kids/impressions/batch', json={'events': []})
        assert res.status_code == 401
        
        # Test payload bounds (>50 items)
        giant_payload = {'events': [{'session_id': 's', 'source_type': 'REEL', 'source_id': i, 'surface': 'REELS'} for i in range(51)]}
        res = client.post(
            '/api/mobile/v2/kids/impressions/batch',
            json=giant_payload,
            headers={'Authorization': f'Bearer {token}'}
        )
        assert res.status_code == 400
        assert 'maximum 50' in res.get_json()['error']

        # Valid batch payload
        executed_impressions = []
        monkeypatch.setattr(
            "services.curated_feed.record_feed_impression",
            lambda *a, **kw: (executed_impressions.append((a, kw)) or True),
        )
        
        valid_payload = {'events': [
            {'session_id': 's1', 'source_type': 'REEL', 'source_id': 1, 'surface': 'REELS', 'watched_ms': 5000, 'completed': True},
            {'session_id': 's1', 'source_type': 'REEL', 'source_id': 2, 'surface': 'REELS', 'watched_ms': 2000, 'completed': False},
        ]}
        res = client.post(
            '/api/mobile/v2/kids/impressions/batch',
            json=valid_payload,
            headers={'Authorization': f'Bearer {token}'}
        )
        assert res.status_code == 200
        assert res.get_json()['ok'] is True
        assert res.get_json()['recorded'] == 2
        assert len(executed_impressions) == 2

# ---------------------------------------------------------------------------
# 5. Reel list uses JIT playback for social video credentials
# ---------------------------------------------------------------------------

def test_reels_page_defers_social_playback_credentials(monkeypatch):
    from flask import Blueprint, Flask
    from mobile.api import register_mobile_api, _issue_token

    app = Flask(__name__)
    app.secret_key = "test-secret"
    bp = Blueprint("mobile_reels_jit", __name__)
    register_mobile_api(bp)
    app.register_blueprint(bp)

    user = {
        "user_id": 202,
        "role": "CHILD",
        "account_status": "ACTIVE",
        "full_name": "Test Child",
        "session_version": 1,
    }
    token = _issue_token(user)

    monkeypatch.setattr("mobile.api._mobile_token_revoked", lambda _token: False)
    monkeypatch.setattr(
        "mobile.api.fetch_one",
        lambda query, params=(): user if "FROM users" in query else None,
    )
    monkeypatch.setattr("mobile.api._child_gate", lambda *args, **kwargs: None)
    # The reels handler pre-authorizes poster refs in one batched pass
    # (_media_allowed_many -> fetch_all); no rows match in this fixture.
    monkeypatch.setattr("mobile.api.fetch_all", lambda query, params=(): [])
    monkeypatch.setattr(
        "mobile.api.get_feed_page",
        lambda *args, **kwargs: {
            "items": [
                {
                    "source_type": "SOCIAL",
                    "source_id": 77,
                    "post_id": 77,
                    "media_type": "VIDEO",
                    "media_reference": "uploads/r2/published/77/clean.mp4",
                    "poster_reference": "uploads/r2/published/77/poster.jpg",
                },
                {
                    "source_type": "CURATED",
                    "source_id": 9,
                    "post_id": 9,
                    "media_type": "VIDEO",
                    "media_reference": "uploads/r2/littlenet/dataset/reels/safe.mp4",
                    "poster_reference": None,
                },
            ],
            "session_id": "sess-jit",
            "next_cursor": 1,
            "has_more": False,
        },
    )
    resolved = []
    monkeypatch.setattr(
        "services.media_delivery.resolve_media_delivery",
        lambda ref, **kwargs: (
            resolved.append(ref)
            or {
                "url": "https://signed.invalid/poster.jpg",
                "expires_at": 1700000600,
            }
        ),
    )

    with app.test_client() as client:
        response = client.get(
            "/api/mobile/v2/kids/reels?limit=8",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    item = response.get_json()["items"][0]
    assert item["media_url"] is None
    assert item["delivery_type"] == "JIT"
    assert item["playback_ready"] is True
    assert item["poster_url"] == "https://signed.invalid/poster.jpg"
    assert resolved == ["uploads/r2/published/77/poster.jpg"]
    curated = response.get_json()["items"][1]
    assert curated["media_url"] is None
    assert curated["delivery_type"] == "JIT_CURATED"
    assert curated["playback_ready"] is True


def test_curated_reel_playback_is_authorized_just_in_time(monkeypatch):
    from flask import Blueprint, Flask
    from mobile.api import register_mobile_api, _issue_token

    app = Flask(__name__)
    app.secret_key = "test-secret"
    bp = Blueprint("mobile_curated_reel_playback", __name__)
    register_mobile_api(bp)
    app.register_blueprint(bp)

    user = {
        "user_id": 202,
        "role": "CHILD",
        "account_status": "ACTIVE",
        "full_name": "Test Child",
        "session_version": 1,
    }
    token = _issue_token(user)
    monkeypatch.setattr("mobile.api._mobile_token_revoked", lambda _token: False)
    monkeypatch.setattr("mobile.api.fetch_one", lambda query, params=(): user if "FROM users" in query else None)
    monkeypatch.setattr("mobile.api._child_gate", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "services.curated_feed.authorize_curated_media",
        lambda child_id, content_id: {
            "content_id": content_id,
            "media_url": "https://signed.invalid/curated.mp4",
            "poster_url": None,
            "playback_expires_at": 1800000000,
        },
    )

    with app.test_client() as client:
        response = client.get(
            "/api/mobile/v2/kids/reels/curated/9/playback",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.get_json()["playback_url"] == "https://signed.invalid/curated.mp4"

