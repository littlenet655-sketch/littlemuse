"""Parent-upload visibility must be wired end-to-end without leaking quarantine."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_mobile_parent_child_upload_history_is_bearer_scoped_and_bounded():
    src = (ROOT / "mobile" / "api.py").read_text(encoding="utf-8")
    body = src.split('def mobile_parent_child_posts(child_id):', 1)[1].split('def mobile_parent_safety():', 1)[0]
    assert '@_require_mobile("PARENT")' in src.split('def mobile_parent_child_posts(child_id):', 1)[0].rsplit('    @bp.route(', 1)[-1]
    assert 'if not owns(pid, child_id)' in body
    assert 'WHERE child_id=%s AND (%s::bigint IS NULL OR post_id < %s::bigint)' in body
    assert 'max(1, min(25,' in body
    assert 'ORDER BY post_id DESC LIMIT %s' in body
    assert 'next_cursor' in body


def test_parent_history_does_not_expose_quarantine_references_or_unapproved_images():
    src = (ROOT / "mobile" / "api.py").read_text(encoding="utf-8")
    body = src.split('def mobile_parent_child_posts(child_id):', 1)[1].split('def mobile_parent_safety():', 1)[0]
    assert 'item.pop("media_path", None)' in body
    assert 'item.pop("poster_path", None)' in body
    assert 'source_media_path' not in body.split('params = (',1)[1]
    assert '"media_url"] = _asset_url(media_path) if fully_published' in body
    assert '"poster_url"] = _asset_url(poster_path) if fully_published' in body
    assert 'item.get("processing_status") or "") == "ALLOWED"' in body


def test_parent_native_screen_wires_history_and_review_navigates_existing_safety_queue():
    src = (ROOT / "mobile_app" / "src" / "screens" / "parent" / "ParentScreens.tsx").read_text(encoding="utf-8")
    assert 'function ParentChildUploadsPanel(' in src
    assert "fetchParentChildPosts(token ?? '', childId, cursor)" in src
    assert "childId={child.user_id}" in src
    assert "onReview={() => navigation.navigate('ParentSafety')}" in src
    panel = src.split("function ParentChildUploadsPanel(", 1)[1].split("/** Last five watched Reels", 1)[0]
    assert "const preview = safe ?" in panel
    assert "item.needs_review ?" in panel
    assert "Older uploads" in panel
    assert "Back to latest uploads" in panel


def test_web_parent_review_checks_double_approved_friendship():
    src = (ROOT / "parent" / "routes.py").read_text(encoding="utf-8")
    body = src.split("def review(event_id):", 1)[1].split("@parent_bp.route('/parent/controls/'", 1)[0]
    assert "approved=TRUE AND approval_stage='ACTIVE'" in body
