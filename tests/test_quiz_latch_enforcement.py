"""Server-side quiz latch enforcement: backend is the final authority.

When the compulsory quiz latch is active for a child:
- Reels list endpoints (v1/v2) return empty items with quiz_required=True
- Playback endpoints return 428 with error=quiz_required
- Quiz fetch/answer endpoints remain accessible (not blocked)

This prevents a client from bypassing the quiz by ignoring the signal.
"""
from flask import Blueprint, Flask
from unittest.mock import MagicMock, patch
from mobile.api import register_mobile_api


def _make_client():
    """Create a test client with the mobile API registered."""
    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.config['TESTING'] = True
    bp = Blueprint("mobile_test", __name__)
    register_mobile_api(bp)
    app.register_blueprint(bp)
    return app.test_client()


def _auth_patches(uid=123):
    """Mock auth stack to simulate an authenticated CHILD user."""
    return [
        patch("mobile.api._load_claims", return_value={"uid": uid, "role": "CHILD", "sver": 1}),
        patch("mobile.api._mobile_token_revoked", return_value=False),
        patch("mobile.api.fetch_one", return_value={
            "user_id": uid, "username": "testkid", "full_name": "Test Kid",
            "email": "kid@test.com", "role": "CHILD", "age": 10,
            "account_status": "ACTIVE", "session_version": 1,
            "parent_paused": False, "demo_unlimited": False,
        }),
    ]


class TestQuizLatchEnforcement:
    def test_v1_reels_blocked_when_latch_active(self):
        """v1 reels returns empty with quiz_required=True when latch active."""
        client = _make_client()
        patches = _auth_patches() + [
            patch("mobile.api._child_gate", return_value=None),
            patch("mobile.api.feed_quiz_state", return_value={"required": True, "required_quiz_id": 999}),
        ]
        for p in patches:
            p.start()
        try:
            resp = client.get("/api/mobile/v1/kids/reels?page=1")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["ok"] is True
            assert data["reels"] == []
            assert data["quiz_required"] is True
        finally:
            for p in patches:
                p.stop()

    def test_v1_reels_served_when_latch_inactive(self):
        """v1 reels serves normally when latch not active."""
        client = _make_client()
        patches = _auth_patches() + [
            patch("mobile.api._child_gate", return_value=None),
            patch("mobile.api.feed_quiz_state", return_value={"required": False}),
            patch("mobile.api.visible_posts", return_value=[{"id": 1}]),
            patch("mobile.api._post_json", return_value={"id": 1}),
        ]
        for p in patches:
            p.start()
        try:
            resp = client.get("/api/mobile/v1/kids/reels?page=1")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["ok"] is True
            assert len(data["reels"]) == 1
            assert data.get("quiz_required") is not True
        finally:
            for p in patches:
                p.stop()

    def test_v2_reels_blocked_when_latch_active(self):
        """v2 reels returns empty items with quiz_required=True when latch active."""
        client = _make_client()
        patches = _auth_patches() + [
            patch("mobile.api._child_gate", return_value=None),
            patch("mobile.api.feed_quiz_state", return_value={"required": True, "required_quiz_id": 999}),
        ]
        for p in patches:
            p.start()
        try:
            resp = client.get("/api/mobile/v2/kids/reels?cursor=0&limit=10")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["ok"] is True
            assert data["items"] == []
            assert data["quiz_required"] is True
        finally:
            for p in patches:
                p.stop()

    def test_v2_playback_blocked_when_latch_active(self):
        """v2 playback returns 428 quiz_required when latch active."""
        client = _make_client()
        patches = _auth_patches() + [
            patch("mobile.api._child_gate", return_value=None),
            patch("mobile.api.feed_quiz_state", return_value={"required": True}),
        ]
        for p in patches:
            p.start()
        try:
            resp = client.get("/api/mobile/v2/kids/reels/123/playback")
            assert resp.status_code == 428
            data = resp.get_json()
            assert data["ok"] is False
            assert data["error"] == "quiz_required"
        finally:
            for p in patches:
                p.stop()

    def test_v2_curated_playback_blocked_when_latch_active(self):
        """v2 curated playback returns 428 quiz_required when latch active."""
        client = _make_client()
        patches = _auth_patches() + [
            patch("mobile.api._child_gate", return_value=None),
            patch("mobile.api.feed_quiz_state", return_value={"required": True}),
        ]
        for p in patches:
            p.start()
        try:
            resp = client.get("/api/mobile/v2/kids/reels/curated/456/playback")
            assert resp.status_code == 428
            data = resp.get_json()
            assert data["ok"] is False
            assert data["error"] == "quiz_required"
        finally:
            for p in patches:
                p.stop()

    def test_enforcement_scoped_to_reels_only(self):
        """Enforcement is scoped to reels endpoints, not global.
        
        The latch must pause Reels but NOT globally gate the app.
        Verify the check appears only in reels/playback endpoints.
        """
        import mobile.api as api_module
        import inspect
        source = inspect.getsource(api_module)
        # 4 reels endpoints + 1 pre-existing use in impression handler + 1 shared
        # helper (_reel_quiz_latch_block) used by the generic playback routes = 6
        count = source.count('feed_quiz_state(uid).get("required")')
        assert count == 6, f"Expected 6 scoped checks, found {count}"


class TestGenericPlaybackEndpointsCannotBypassLatch:
    """/v2/media/playback and /v2/curated/media serve ordinary media too, so the
    latch applies only when the target is a Reel."""

    def _run(self, url, latch, is_reel, extra=()):
        client = _make_client()
        patches = _auth_patches() + [
            patch("mobile.api._child_gate", return_value=None),
            patch("mobile.api.feed_quiz_state", return_value={"required": latch}),
            patch("mobile.api._target_is_reel", return_value=is_reel),
        ] + list(extra)
        for p in patches:
            p.start()
        try:
            return client.get(url)
        finally:
            for p in patches:
                p.stop()

    def test_generic_post_playback_blocked_for_reel_when_latched(self):
        resp = self._run("/api/mobile/v2/media/playback/77", latch=True, is_reel=True)
        assert resp.status_code == 428
        assert resp.get_json()["error"] == "quiz_required"

    def test_generic_post_playback_allowed_for_non_reel_when_latched(self):
        playback = {"playback_url": "https://cdn.test/v.mp4", "delivery_mode": "SIGNED"}
        resp = self._run(
            "/api/mobile/v2/media/playback/77", latch=True, is_reel=False,
            extra=[patch("services.video_delivery.resolve_video_playback", return_value=playback)],
        )
        assert resp.status_code == 200

    def test_generic_post_playback_allowed_for_reel_when_not_latched(self):
        playback = {"playback_url": "https://cdn.test/v.mp4", "delivery_mode": "SIGNED"}
        resp = self._run(
            "/api/mobile/v2/media/playback/77", latch=False, is_reel=True,
            extra=[patch("services.video_delivery.resolve_video_playback", return_value=playback)],
        )
        assert resp.status_code == 200

    def test_generic_curated_media_blocked_for_reel_when_latched(self):
        resp = self._run("/api/mobile/v2/curated/media/5", latch=True, is_reel=True)
        assert resp.status_code == 428
        assert resp.get_json()["error"] == "quiz_required"

    def test_generic_curated_media_allowed_for_non_reel_when_latched(self):
        payload = {"media_url": "https://cdn.test/c.mp4", "poster_url": None}
        resp = self._run(
            "/api/mobile/v2/curated/media/5", latch=True, is_reel=False,
            extra=[patch("mobile.api.authorize_curated_media", return_value=payload)],
        )
        assert resp.status_code == 200

    def test_generic_curated_media_allowed_for_reel_when_not_latched(self):
        payload = {"media_url": "https://cdn.test/c.mp4", "poster_url": None}
        resp = self._run(
            "/api/mobile/v2/curated/media/5", latch=False, is_reel=True,
            extra=[patch("mobile.api.authorize_curated_media", return_value=payload)],
        )
        assert resp.status_code == 200
