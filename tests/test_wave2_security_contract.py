from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _text(path):
    return (ROOT / path).read_text(encoding='utf-8')


def test_parent_liveness_page_and_mediapipe_module_are_removed():
    # Parent face/liveness verification was removed by explicit product
    # decision. The page, its self-hosted MediaPipe module, and every
    # reference to them must be gone (child face flows are unaffected).
    assert not (ROOT / 'auth/templates/parent_liveness_verify.html').exists()
    assert not (ROOT / 'static/js/parent_liveness_mediapipe.js').exists()
    routes = _text('auth/routes.py')
    service = _text('auth/service.py')
    assert 'verify_parent_liveness_page' not in routes
    assert 'parent_liveness_verify.html' not in routes
    assert 'parent_liveness_mediapipe' not in routes
    assert 'verify_adult_face' not in routes
    assert 'verify_adult_face' not in service


def test_mediapipe_liveness_assets_are_fully_removed():
    # Parent liveness verification was removed by explicit product decision:
    # no build step may install the MediaPipe assets, no healthcheck may look
    # for them, and the vendored directory must be gone. (The installer script
    # tools/install_mediapipe_assets.py was deleted with the rest of the chain.)
    assert not (ROOT / 'static/vendor/mediapipe').exists()
    ci = _text('.github/workflows/ci.yml')
    docker = _text('Dockerfile.web')
    modal = _text('modal_web.py')
    assert 'install_mediapipe_assets' not in ci
    assert 'install_mediapipe_assets' not in docker
    assert 'install_mediapipe_assets' not in modal
    assert 'mediapipe' not in ci.lower()
    assert 'mediapipe' not in docker.lower()
    assert 'mediapipe' not in modal.lower()


def test_message_notes_only_select_active_parent_approved_friends():
    routes = _text('childMessage/routes.py')
    notes_start = routes.index('peers = fetch_all(')
    notes_end = routes.index('sample_notes =', notes_start)
    notes = routes[notes_start:notes_end]
    assert 'FROM followers f' in notes
    assert "f.approved=TRUE" in notes
    assert "f.approval_stage='ACTIVE'" in notes
    assert 'blocked_users' in notes
    assert 'muted_users' in notes
    assert "FROM users u\n        JOIN child_profiles" not in notes


def test_direct_media_route_reuses_canonical_social_visibility():
    app = _text('app.py')
    route_start = app.index("@app.route('/uploads/<path:filename>')")
    route_end = app.index("@app.route('/healthz')", route_start)
    route = app[route_start:route_end]
    assert 'post_visible_to' in route
    assert 'story_visible_to' in route
    assert 'can_interact' in route
    assert 'can_discover_child' in route
    assert "filename.startswith('profile_pictures/')" not in route
    signing = route.index("if stored.startswith('uploads/r2/')")
    assert route.index('post_visible_to') < signing
    assert route.index('can_interact') < signing
    assert route.index('can_discover_child') < signing


def test_friendship_trigger_cannot_promote_replayed_sender_approval():
    sql = _text('database/friendship_upgrade.sql')
    assert "ELSIF OLD.approval_stage='SENDER_PARENT_APPROVED'" in sql
    replay_guard = sql.index("ELSIF OLD.approval_stage='SENDER_PARENT_APPROVED'")
    tail = sql[replay_guard:]
    assert 'NEW.approved=FALSE' in tail or 'RETURN OLD' in tail or 'RETURN NEW' in tail
