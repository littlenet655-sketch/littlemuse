"""Child-side read-only visibility of own Controls and Activity.

Covers by source assertion (no live Postgres in sandbox):
1. Both endpoints exist and are CHILD-role only.
2. Strict self-scoping: every query is keyed by the session uid; no
   child_id is accepted from the request, so child A cannot see child B.
3. Controls payload exposes the expected read-only fields and nothing
   parent-side (no parent account info, no sibling data, no moderation
   internals).
4. Activity payload reuses the own like/save snapshot and the child's own
   quiz attempts only.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text(encoding='utf-8')


def fn_body(src, name):
    """Source of one top-level function (up to the next top-level def)."""
    m = re.search(rf'\n    def {name}\(\):\n(.*?)(?=\n    def |\n    @bp\.route)', src, re.S)
    assert m, f'function {name} not found'
    return m.group(1)


# ---------- endpoint existence + role ----------

def test_my_controls_endpoint_is_child_only():
    api = text('mobile/api.py')
    assert '@bp.route("/api/mobile/v1/kids/my-controls")' in api
    assert 'def mobile_kids_my_controls():' in api
    body = fn_body(api, 'mobile_kids_my_controls')
    assert 'uid = int(g.mobile_user["user_id"])' in body


def test_my_activity_endpoint_is_child_only():
    api = text('mobile/api.py')
    assert '@bp.route("/api/mobile/v1/kids/my-activity")' in api
    assert 'def mobile_kids_my_activity():' in api
    body = fn_body(api, 'mobile_kids_my_activity')
    assert 'uid = int(g.mobile_user["user_id"])' in body


def test_endpoints_registered_before_functions():
    api = text('mobile/api.py')
    for route, fn in (('/api/mobile/v1/kids/my-controls', 'mobile_kids_my_controls'),
                      ('/api/mobile/v1/kids/my-activity', 'mobile_kids_my_activity')):
        route_pos = api.index(f'@bp.route("{route}")')
        fn_pos = api.index(f'def {fn}():')
        window = api[route_pos:fn_pos]
        assert '@_require_mobile("CHILD")' in window, f'{fn} is not CHILD-scoped'


# ---------- self-scoping: child A cannot see child B ----------

def test_my_controls_is_self_scoped():
    body = fn_body(text('mobile/api.py'), 'mobile_kids_my_controls')
    # No child identifier taken from the request — uid comes from the session.
    assert 'request.args' not in body
    assert 'request.get_json' not in body
    # Every direct fetch is keyed by the session uid.
    assert body.count('(uid,)') >= 2
    assert 'child_id=' not in body.replace('child_id=%s', '')


def test_my_activity_is_self_scoped():
    body = fn_body(text('mobile/api.py'), 'mobile_kids_my_activity')
    assert 'request.args' not in body
    assert 'request.get_json' not in body
    # Like/save snapshot and quiz attempts are both queried for uid only.
    assert '_liked_saved_snapshot(uid' in body
    assert 'WHERE child_id=%s' in body
    # Two direct fetches keyed by uid (quiz stats + recent attempts); the
    # like/save snapshot is also uid-keyed (see its own tests).
    assert body.count('(uid,)') >= 2


# ---------- payload contents ----------

def test_my_controls_payload_fields():
    body = fn_body(text('mobile/api.py'), 'mobile_kids_my_controls')
    for field in ('safety_level', 'daily_limit_minutes', 'strict_mode',
                  'quiet_hours', 'features', 'educational_only_feed'):
        assert field in body, f'missing field {field}'
    # All six feature flags resolved through the server-side control check.
    for feature in ('reels', 'stories', 'messaging', 'posting', 'discover', 'comments'):
        assert f'feature_allowed(uid, "{feature}")' in body, f'missing feature {feature}'
    # Quiet hours come from the server-side control service.
    assert 'quiet_hours_state(uid)' in body
    assert 'controls_for_child(uid)' in body


def test_my_controls_exposes_no_parent_or_sibling_data():
    body = fn_body(text('mobile/api.py'), 'mobile_kids_my_controls')
    # Settings tables keyed by the child's own id are fine; parent account
    # tables and sibling lookups are not.
    assert 'FROM users' not in body
    assert 'parent_child_map' not in body
    assert 'moderation_events' not in body
    assert 'password' not in body.lower()


def test_my_activity_payload_fields():
    body = fn_body(text('mobile/api.py'), 'mobile_kids_my_activity')
    assert 'liked_saved' in body
    assert 'quiz_7d' in body
    assert 'recent_quizzes' in body
    assert 'child_quiz_attempts' in body
    # Own quiz stats aggregate only the requesting child.
    assert "COUNT(*) FILTER (WHERE is_correct)" in body


# ---------- mobile wiring ----------

def test_mobile_wrappers_and_routes_exist():
    client = text('mobile_app/src/api/client.ts')
    assert "kidsMyControls: '/api/mobile/v1/kids/my-controls'" in client
    assert "kidsMyActivity: '/api/mobile/v1/kids/my-activity'" in client
    feed = text('mobile_app/src/api/kidsFeed.ts')
    assert 'export function fetchMyControls' in feed
    assert 'export function fetchMyActivity' in feed
    keys = text('mobile_app/src/query/keys.ts')
    assert 'myControls' in keys and 'myActivity' in keys


def test_child_navigation_registers_screens():
    types = text('mobile_app/src/navigation/types.ts')
    assert 'MyControls: undefined;' in types
    assert 'MyActivity: undefined;' in types
    root = text('mobile_app/src/navigation/RootNavigator.tsx')
    assert 'name="MyControls"' in root
    assert 'name="MyActivity"' in root
    profile = text('mobile_app/src/screens/kids/OwnProfileScreen.tsx')
    assert "nav.navigate('MyControls'" in profile
    assert "nav.navigate('MyActivity'" in profile
