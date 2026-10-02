"""Source-contract regression tests for the Agent F domain.

These run without importing the Flask app (sandbox lacks some app deps), so
they assert the structural contracts that keep media authorization, the
/kids/home startup path, and the demo-boost schema consistent:

1. Batch media authorization must mirror _media_allowed / post_visible_to.
   Public approved content is visible app-wide (NOT friends-only), so the
   batched visibility query must not demand an ACTIVE follow relationship.
2. database/schema.sql is the maintained clean-schema baseline: every new
   persistent table (demo_boost_state) must appear there as well as in its
   dbmate migration.
3. /kids/home must authorize its whole payload in one batched pass
   (_media_allowed_many) instead of per-item per-reference DB round trips.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_batch_media_visibility_has_no_friendship_requirement():
    api = text("mobile/api.py")
    batch = api.split("def _media_allowed_many", 1)[1]
    # Cut at the next top-level def (nested defs use indentation).
    nxt = batch.find("\ndef ")
    batch = batch[:nxt]
    vis = batch.split("visible_post_ids = set()", 1)[1]
    assert "following_child_id" not in vis, (
        "batch visibility diverged from post_visible_to: public content is "
        "app-wide, not friends-only"
    )
    assert "approval_stage" not in vis


def test_batch_media_visibility_matches_post_visible_to_filters():
    api = text("mobile/api.py")
    batch = api.split("def _media_allowed_many", 1)[1]
    nxt = batch.find("\ndef ")
    batch = batch[:nxt]
    vis = batch.split("visible_post_ids = set()", 1)[1]
    for token in (
        "p.moderation_status='ALLOWED'",
        "p.is_safe=TRUE",
        "p.content_category = ANY",
        "audience_age_group",
        "blocked_users",
        "muted_users",
    ):
        assert token in vis, f"batch visibility lost filter: {token}"


def test_demo_boost_state_in_clean_schema_baseline():
    schema = text("database/schema.sql")
    assert "CREATE TABLE IF NOT EXISTS demo_boost_state" in schema
    assert "CHECK (state_id = 1)" in schema
    assert "'OFF','WARMING','READY'" in schema


def test_kids_home_batches_media_authorization():
    api = text("mobile/api.py")
    home = api.split('def mobile_kids_home', 1)[1].split("\n    @bp.route(", 1)[0]
    assert "_media_allowed_many(uid" in home
    assert "auth_decisions=_auth" in home
    for fn in ("def _post_json", "def _asset_url", "def _profile_json"):
        sig = api.split(fn, 1)[1].split("):", 1)[0]
        assert "auth_decisions" in sig, f"{fn} must accept auth_decisions"


def test_demo_boost_never_mints_permanent_media_access():
    service = text("services/demo_boost.py")
    # Demo Boost only touches the Modal autoscaler; it must never mint media
    # URLs or touch moderation state.
    assert "signed_download_url" not in service
    assert "moderation_status" not in service


def test_demo_boost_admin_actions_are_audit_logged():
    api = text("mobile/api.py")
    for action in ("DEMO_BOOST_START", "DEMO_BOOST_EXTEND", "DEMO_BOOST_STOP"):
        assert action in api, f"{action} must be written to admin_audit_logs"
    assert "def _audit_demo_boost" in api
