from pathlib import Path

import pytest
from flask import Flask, session

import decorators

ROOT = Path(__file__).parents[1]


def text(path):
    return (ROOT / path).read_text(encoding='utf-8')


def _bare_view(fn):
    while hasattr(fn, '__wrapped__'):
        fn = fn.__wrapped__
    return fn


def test_suspended_child_session_is_revoked(monkeypatch):
    app = Flask(__name__)
    app.secret_key = 'test-only'
    monkeypatch.setattr(decorators, 'fetch_one', lambda *_a, **_k: {'role': 'CHILD', 'account_status': 'SUSPENDED'})

    @decorators.child_required
    def protected():
        return 'should-not-run'

    with app.test_request_context('/child/dashboard/'):
        session.update(user_id=7, role='CHILD')
        response = protected()
        assert response.status_code == 302
        assert 'user_id' not in session


def test_suspended_admin_session_is_revoked(monkeypatch):
    app = Flask(__name__)
    app.secret_key = 'test-only'
    monkeypatch.setattr(decorators, 'fetch_one', lambda *_a, **_k: {'role': 'ADMIN', 'account_status': 'SUSPENDED'})

    @decorators.admin_required
    def protected():
        return 'should-not-run'

    with app.test_request_context('/admin/'):
        session.update(user_id=9, role='ADMIN')
        response = protected()
        assert response.status_code == 302
        assert 'user_id' not in session


def test_parent_ownership_requires_approved_mapping():
    src = text('parent/service.py')
    assert "approved=TRUE" in src
    assert "approval_status='APPROVED'" in src
    assert 'LOWER(m.parent_email)' not in src


def test_legacy_guardian_shortcuts_fail_closed():
    src = text('decorators.py')
    assert "'/parent/quick-approve-child'" in src
    assert 'Legacy quick approval is disabled' in src
    assert "request.method=='GET' and request.path.startswith('/parent/confirm-child/')" in src


def test_story_caption_edit_has_pii_gate():
    src = text('decorators.py')
    assert "request.path.startswith('/api/edit-story-caption/')" in src
    assert 'scan_pii' in src


def test_discover_parent_control_covers_direct_surfaces():
    src = text('decorators.py')
    for path in ('/api/search/suggestions/','/child/view-profile/','/follow/','/recommended/'):
        assert path in src
    assert "feature_allowed(uid,'discover')" in src


def test_recommendations_use_canonical_discovery_and_active_friendship():
    src = text('services/recommendation.py')
    assert 'discoverable_child_ids(cid)' in src
    assert "approval_stage='ACTIVE'" in src
    assert 'p.child_id=ANY(%s)' in src


def test_teen_quiz_band_and_notification_compatibility_migration_exist():
    src = text('db/migrations/20260907142000_audit_p0_p1_hardening.sql')
    assert "'14-18'" in src
    assert 'ADD COLUMN IF NOT EXISTS media_url' in src
    assert 'ADD COLUMN IF NOT EXISTS thumbnail_url' in src
    assert 'idx_posts_media_path' in src
    assert 'trg_littlenet_guard_parent_child_approval' in src


def test_live_safety_never_injects_model_reason_as_html():
    src = text('static/js/live_safety.js')
    assert 'result.innerHTML' not in src
    assert 'span.textContent=reason' in src
    assert 'if(!res.ok)' in src


def test_release_workflow_uploads_verified_zip():
    src = text('.github/workflows/package-release.yml')
    assert 'python tools/verify_release.py' in src
    assert 'cp ../LittleNet-complete-release.zip ./LittleNet-complete-release.zip' in src
    assert 'path: LittleNet-complete-release.zip' in src
    assert 'path: ../LittleNet-complete-release.zip' not in src
    assert 'path: release/' not in src


def test_production_secret_is_not_predictable_default():
    src = text('config.py')
    assert 'secrets.token_urlsafe(48)' in src
    assert 'Production SECRET_KEY must be explicitly configured' in src
    assert 'Production DATABASE_URL must be explicitly configured' in src
