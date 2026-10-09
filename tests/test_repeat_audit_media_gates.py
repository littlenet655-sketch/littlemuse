"""Release red-team: child lock/media signing and final-publication parity.

These tests exercise the central authorizers directly, including the batch
path used by the React Native home/feed and the direct URL auth path. They do
not require a production R2 bucket or mutate a real database.
"""
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from mobile.api import _media_allowed, _media_allowed_many
from services.social import child_surface_open
from child.service import counts


ROOT = Path(__file__).resolve().parents[1]


def test_parent_paused_closes_child_media_surfaces_even_when_timing_unlimited(monkeypatch):
    app = Flask(__name__)
    with app.test_request_context("/api/mobile/v1/media?ref=r2:curated/x.jpg"):
        monkeypatch.setattr(
            "services.social.fetch_one",
            lambda sql, params=None: {
                "role": "CHILD",
                "account_status": "ACTIVE",
                "parent_paused": True,
            },
        )
        # The parent pause is authoritative and takes precedence over the
        # demo-unlimited time exceptions and quiet-hours/usage computations.
        monkeypatch.setattr(
            "services.social.quiet_hours_state",
            lambda _cid: (_ for _ in ()).throw(AssertionError("lock ignored")),
        )
        assert child_surface_open(11) is False


def test_direct_child_media_auth_denies_locked_requests_before_fetch():
    with patch("services.social.child_surface_open", return_value=False), patch(
        "mobile.api.fetch_one",
        side_effect=AssertionError("no DB lookups after a child lock"),
    ):
        for ref in (
            "uploads/r2/curated/movie.mp4",
            "uploads/r2/private/message.jpg",
            "uploads/r2/avatars/a.jpg",
            "uploads/r2/posts/p.jpg",
        ):
            assert not _media_allowed(11, "CHILD", ref)


def test_batched_child_media_auth_denies_locked_requests_without_db_queries():
    with patch("services.social.child_surface_open", return_value=False), patch(
        "mobile.api.fetch_all",
        side_effect=AssertionError("no DB lookups after a child lock"),
    ):
        refs = ["uploads/r2/curated/movie.mp4", "uploads/r2/avatars/a.jpg"]
        assert _media_allowed_many(11, "CHILD", refs) == {
            ref: False for ref in refs
        }


def test_media_route_explicitly_checks_parent_gate_before_download():
    source = (ROOT / "mobile" / "api.py").read_text(encoding="utf-8")
    body = source.split("def mobile_media():", 1)[1].split("def mobile_kids_home():", 1)[0]
    assert 'if role.upper() == "CHILD":' in body
    assert "_child_gate(record_usage=False)" in body
    assert body.index("_child_gate(record_usage=False)") < body.index("_media_allowed(uid, role, ref)")


def test_batched_media_post_query_requires_final_processing_allow():
    source = (ROOT / "mobile" / "api.py").read_text(encoding="utf-8")
    batch = source.split("def _media_allowed_many(", 1)[1].split("def _merge_signals(", 1)[0]
    assert "p.processing_status='ALLOWED'" in batch
    assert "SELECT post_id, child_id, moderation_status, processing_status" in batch


def test_profile_post_count_requires_final_processing_allow(monkeypatch):
    queries = []
    def fake_fetch_one(sql, _params):
        queries.append(sql)
        return {"n": 0}
    monkeypatch.setattr("child.service.fetch_one", fake_fetch_one)
    assert counts(11)["posts"] == 0
    assert "processing_status='ALLOWED'" in queries[1]


def test_direct_media_auth_checks_child_surface_even_on_valid_curated_assets():
    with patch("services.social.child_surface_open", return_value=False) as gate:
        assert _media_allowed(11, "CHILD", "uploads/r2/curated/valid.jpg") is False
        gate.assert_called_once_with(11)
