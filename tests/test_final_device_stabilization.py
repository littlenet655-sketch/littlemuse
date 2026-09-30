from pathlib import Path

import pytest
from flask import g

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def app():
    from app import create_app
    instance = create_app()
    instance.config.update(TESTING=True)
    return instance


def test_parent_email_login_preserves_mode_and_local_event(app):
    from urllib.parse import parse_qs, urlsplit
    with app.test_client() as client:
        response = client.get('/parent/safety/?event=123')
        query = parse_qs(urlsplit(response.location).query)
        assert query == {'mode': ['parent'], 'next': ['/parent/safety/?event=123']}
        response = client.post('/login/', data={'mode': 'parent', 'next': '/parent/safety/?event=123'})
        query = parse_qs(urlsplit(response.location).query)
        assert query['mode'] == ['parent']
        assert query['next'] == ['/parent/safety/?event=123']
        assert 'session was refreshed' in query['error'][0]
        assert response.headers['Cache-Control'] == 'private, no-store'


@pytest.mark.parametrize('target,expected', [
    ('/parent/safety/?event=123', '/parent/safety/?event=123'),
    ('https://evil.invalid/', '/parent/dashboard/'),
    ('//evil.invalid/', '/parent/dashboard/'),
    ('/parent/\\evil.invalid/', '/parent/dashboard/'),
])
def test_parent_login_redirect_is_local(app, monkeypatch, target, expected):
    from auth import routes
    monkeypatch.setattr(routes, 'login_user', lambda *_: {'role': 'PARENT', 'account_status': 'ACTIVE'})
    monkeypatch.setattr(routes, '_set_session', lambda *_: None)
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_client() as client:
        assert client.post('/login/', data={'email': 'fixture', 'password': 'fixture', 'next': target}).location == expected


@pytest.mark.parametrize('owned', [True, False])
def test_review_preview_is_owned_private_and_short_lived(app, monkeypatch, owned):
    from parent import routes
    from services import object_storage
    queries = iter([
        {'event_id': 123, 'child_id': 7, 'content_id': 9, 'content_type': 'IMAGE'},
        {'source_media_path': 'uploads/r2/quarantine/fixture.jpg', 'media_path': None},
    ])
    monkeypatch.setattr(routes, 'fetch_one', lambda *_: next(queries))
    monkeypatch.setattr(routes, 'owns', lambda *_: owned)
    signed = []
    monkeypatch.setattr(object_storage, 'signed_download_url', lambda ref, expires_seconds: signed.append(expires_seconds) or 'https://private.invalid/signed')
    with app.test_request_context('/parent/review/123/preview/'):
        from flask import session
        session['user_id'] = 1
        result = routes.review_preview.__wrapped__(123)
        if owned:
            assert result.status_code == 302
            assert signed == [60]
            assert result.headers['Cache-Control'] == 'private, no-store'
        else:
            assert result[1] == 404
            assert signed == []


def test_foreign_review_event_cannot_be_focused(app, monkeypatch):
    from parent import routes
    monkeypatch.setattr(routes, 'fetch_all', lambda *_: [{'event_id': 1}])
    with app.test_request_context('/parent/safety/?event=999'):
        from flask import session
        session['user_id'] = 1
        assert routes.safety.__wrapped__()[1] == 404


@pytest.mark.parametrize('visible', [True, False])
def test_post_detail_route_uses_shared_visibility(app, monkeypatch, visible):
    from mobile import api
    rule = next(r for r in app.url_map.iter_rules() if r.rule == '/api/mobile/v1/kids/posts/<int:post_id>' and 'GET' in r.methods)
    monkeypatch.setattr(api, '_child_gate', lambda: None)
    monkeypatch.setattr(api, 'post_visible_to', lambda uid, pid: {'post_id': pid} if visible else None)
    monkeypatch.setattr(api, '_post_json', lambda row, uid: row)
    with app.test_request_context('/api/mobile/v1/kids/posts/9'):
        g.mobile_user = {'user_id': 7}
        response = app.view_functions[rule.endpoint].__wrapped__(9)
        if visible:
            assert response.get_json()['post']['post_id'] == 9
        else:
            assert response[1] == 404


def test_practice_exhaustion_fills_locally_without_paid_ai(monkeypatch):
    from quiz import service, learning_service
    monkeypatch.setattr(service, 'age_group', lambda _: '9-11')
    queries = iter([[{'quiz_id': 1}], [{'quiz_id': 99}]])
    monkeypatch.setattr(service, 'fetch_all', lambda *_: next(queries))
    monkeypatch.setattr(learning_service, '_procedural_fallback_quizzes', lambda **_: [{'quiz_id': 2}, {'quiz_id': 99}])
    monkeypatch.setattr(learning_service, 'generate_and_insert_fresh_quizzes', lambda **_: pytest.fail('paid generator called'))
    assert [q['quiz_id'] for q in service.quizzes(7, 3)] == [1, 2]


def test_healthy_ocr_does_not_invent_partial_model_failure(monkeypatch):
    from safety import visual_service, text_service, pii_service
    from safety.policy import decide
    neutral = {'errors': [], 'partial_safety_failure': False, 'total_safety_failure': False, 'ran': 3,
               'adult_score': 0.01, 'sexual_score': 0, 'weapon_score': 0, 'violence_score': 0, 'toxicity_score': 0.32, 'general_score': 0}
    monkeypatch.setattr(visual_service, '_ocr_extract_text', lambda _: ('A sunny day', None))
    monkeypatch.setattr(text_service, 'check_text', lambda _: dict(neutral))
    monkeypatch.setattr(pii_service, 'scan_pii', lambda _: {'detected': False, 'redacted_text': 'A sunny day'})
    result = visual_service._apply_ocr_stage(dict(neutral), 'fixture', True, 3)
    assert result['errors'] == []
    assert result['partial_safety_failure'] is False
    assert decide(result).action == 'ALLOW'
    monkeypatch.setattr(visual_service, '_ocr_extract_text', lambda _: (None, 'ocr_timeout'))
    result = visual_service._apply_ocr_stage(dict(neutral, errors=[]), 'fixture', True, 3)
    assert decide(result).action == 'REVIEW'


def test_exact_lookup_and_suggestions_are_separate(monkeypatch):
    from child import service
    monkeypatch.setattr(service, 'fetch_all', lambda *_: [{'user_id': 2, 'username': 'fixture'}])
    monkeypatch.setattr(service, 'can_discover_child', lambda *_: True)
    monkeypatch.setattr(service, 'discoverable_child_ids', lambda _: [])
    assert service.discoverable_children(1) == []
    assert service.discoverable_children(1, 'fixture')[0]['user_id'] == 2


def test_deploy_images_exclude_local_credentials_and_quarantine_not_in_html():
    for name in ['modal_ai.py', 'modal_web.py']:
        source = (ROOT / name).read_text(encoding='utf-8')
        for excluded in ('".env.*"', '"scratch/**"', '"walkthrough.md"'):
            assert excluded in source
    assert 'e.preview.media_path' not in (ROOT / 'parent/templates/safety_review.html').read_text(encoding='utf-8')


@pytest.mark.parametrize('active,expected', [(False, 'pending'), (True, 'following')])
def test_explicit_follow_request_retry_preserves_relationship(app, monkeypatch, active, expected):
    import inspect
    from mobile import api
    state = {'pending': False}
    monkeypatch.setattr(api, '_child_gate', lambda *_: None)
    monkeypatch.setattr(api, 'can_discover_child', lambda *_: True)
    monkeypatch.setattr(api, 'is_following', lambda *_: active)
    monkeypatch.setattr(api, 'outgoing_follow_pending', lambda *_: state['pending'])
    monkeypatch.setattr(api, 'incoming_follow_pending', lambda *_: False)
    monkeypatch.setattr(api, 'child_has_guardian', lambda *_: True)
    monkeypatch.setattr(api, 'follow_child', lambda *_: state.update(pending=True))
    monkeypatch.setattr(api, 'unfollow_child', lambda *_: pytest.fail('retry removed friendship'))
    monkeypatch.setattr(api, 'cancel_outgoing_follow', lambda *_: pytest.fail('retry cancelled request'))
    monkeypatch.setattr(api, 'record_signal', lambda *_: None)
    monkeypatch.setattr(api, 'parent_notify', lambda *_: None)
    rule = next(r for r in app.url_map.iter_rules() if r.rule == '/api/mobile/v1/kids/follow/<int:child_id>')
    view = inspect.unwrap(app.view_functions[rule.endpoint])
    for _ in range(2):
        with app.test_request_context('/api/mobile/v1/kids/follow/8', method='POST', json={'action': 'request'}):
            g.mobile_user = {'user_id': 7}
            assert view(8).get_json()['status'] == expected


def test_connection_request_lists_execute_with_real_follower_key(app, monkeypatch):
    import inspect
    import sqlite3
    from mobile import api
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript('''
        CREATE TABLE followers(follower_id INTEGER,child_id INTEGER,following_child_id INTEGER,
                               approved BOOLEAN,created_at TEXT,approval_stage TEXT);
        CREATE TABLE users(user_id INTEGER,full_name TEXT,username TEXT);
        CREATE TABLE child_profiles(child_id INTEGER,profile_picture TEXT,school_name TEXT);
        INSERT INTO users VALUES(8,'Fixture','fixture');
        INSERT INTO followers VALUES(1,7,8,FALSE,'2026-09-30','REQUESTED');
        INSERT INTO followers VALUES(2,8,7,FALSE,'2026-09-30','RECEIVER_PARENT_PENDING');
    ''')
    monkeypatch.setattr(api, '_child_gate', lambda *_: None)
    monkeypatch.setattr(api, 'fetch_all', lambda sql, params: [dict(r) for r in conn.execute(sql.replace('%s','?'), params)])
    monkeypatch.setattr(api, '_asset_url', lambda _: None)
    with app.test_request_context('/api/mobile/v1/kids/connections/requests'):
        g.mobile_user = {'user_id': 7}
        rule = next(r for r in app.url_map.iter_rules() if r.rule == '/api/mobile/v1/kids/connections/requests')
        payload = inspect.unwrap(app.view_functions[rule.endpoint])().get_json()
        assert payload['incoming'][0]['id'] == 2
        assert payload['outgoing'][0]['id'] == 1
    conn.close()
