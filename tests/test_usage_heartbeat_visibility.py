from flask import Flask, session

from child import routes


def _app():
    app = Flask(__name__)
    app.secret_key = 'test-only'
    return app


def test_hidden_child_page_closes_usage_segment(monkeypatch):
    closed = []
    monkeypatch.setattr(routes, 'close_session', closed.append)

    with _app().test_request_context('/api/usage/heartbeat/', method='POST', json={'active': False}):
        session.update(user_id=7, role='CHILD', usage_session_key='old-session')
        response = routes.usage_heartbeat()

        assert response.get_json() == {'ok': True, 'active': False}
        assert closed == ['old-session']
        assert 'usage_session_key' not in session


def test_visible_child_page_restarts_a_closed_usage_segment(monkeypatch):
    monkeypatch.setattr(routes, 'quiet_hours_state', lambda _: {'active': False})
    monkeypatch.setattr(routes, 'heartbeat', lambda _: None)
    monkeypatch.setattr(routes, 'start_session', lambda _: {'session_key': 'new-session'})
    monkeypatch.setattr(routes, 'lock_state', lambda _: (False, 42))

    with _app().test_request_context('/api/usage/heartbeat/', method='POST', json={'active': True}):
        session.update(user_id=7, role='CHILD', usage_session_key='stale-session')
        response = routes.usage_heartbeat()

        assert response.get_json()['remaining_minutes'] == 42
        assert session['usage_session_key'] == 'new-session'


def test_child_heartbeat_rejects_non_boolean_activity_state():
    with _app().test_request_context('/api/usage/heartbeat/', method='POST', json={'active': 'false'}):
        session.update(user_id=7, role='CHILD')
        response, status = routes.usage_heartbeat()

        assert status == 400
        assert response.get_json() == {'error': 'invalid active state'}
