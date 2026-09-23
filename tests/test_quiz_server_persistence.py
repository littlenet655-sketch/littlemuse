from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text(encoding='utf-8')


def test_quiz_progress_schema_persists_required_latch_and_seen_ids():
    schema = text('database/schema.sql')
    upgrade = text('database/upgrade.sql')
    for source in (schema, upgrade):
        assert 'quiz_required' in source
        assert 'required_quiz_id' in source
        assert 'required_at' in source
        assert 'viewed_post_ids' in source


def test_view_counter_is_server_authoritative_and_row_locked():
    service = text('quiz/service.py')
    assert 'FEED_QUIZ_INTERVAL = 5' in service
    assert 'def record_feed_view' in service
    assert 'FOR UPDATE' in service
    assert "post_id not in seen" in service
    assert 'quiz_required=%s' in service
    assert 'required_at=CASE WHEN %s' in service
    assert 'def required_feed_quiz' in service
    assert 'required_quiz_id IS NULL' in service
    assert 'def complete_required_feed_quiz' in service


def test_page_load_bump_no_longer_increments_progress():
    service = text('quiz/service.py')
    block = service.split('def bump(cid):', 1)[1].split('def reset(cid):', 1)[0]
    assert 'record_feed_view' in block
    assert 'execute(' not in block
    assert 'return feed_quiz_state(cid)' in block


def test_browser_reports_real_ids_and_has_no_refresh_reset_counter():
    js = text('static/js/feed_quiz.js')
    assert '/quiz/api/feed-view/' in js
    assert '/quiz/api/feed-quiz/status/' in js
    assert '/quiz/api/feed-quiz/' in js
    assert '/quiz/api/feed-quiz/answer/' in js
    assert 'post_id: postId' in js
    assert 'postsSinceLastQuiz' not in js
    assert 'postsSinceLastQuiz++' not in js
    assert "document.documentElement.style.overflow = 'hidden'" in js
    assert 'Retry quiz' in js
    assert 'Skip for now' not in js


def test_required_quiz_routes_live_under_quiz_exemption_and_match_assignment():
    routes = text('quiz/routes.py')
    assert "@quiz_bp.route('/quiz/api/feed-view/'" in routes
    assert "@quiz_bp.route('/quiz/api/feed-quiz/status/'" in routes
    assert "@quiz_bp.route('/quiz/api/feed-quiz/'" in routes
    assert "@quiz_bp.route('/quiz/api/feed-quiz/answer/'" in routes
    assert 'required_feed_quiz' in routes
    assert "return jsonify(error='required_quiz_mismatch'),409" in routes
    assert 'complete_required_feed_quiz' in routes


def test_app_gate_redirects_when_persistent_quiz_is_due():
    app = text('app.py')
    assert "if path.startswith('/quiz/'):" in app
    assert "if quiz_due(session['user_id']):return redirect('/quiz/start/')" in app
