from pathlib import Path

ROOT=Path(__file__).parents[1]

def text(path):
    return (ROOT/path).read_text(encoding='utf-8')


def test_discovery_scope_has_no_global_minor_fallback():
    s=text('child/service.py')
    assert 'def discoverable_child_ids' in s
    assert "same school AND same class" in s
    assert "TRIM(LOWER(cp.school_name))" in s
    assert "TRIM(LOWER(cp.current_class))" in s
    assert "approval_stage='ACTIVE'" in s
    assert 'approved_friends AS' in s
    assert 'pending_peers AS' in s
    assert 'network AS' in s
    assert 'LittleNet Classmate' not in s


def test_name_suggestions_use_trusted_cohort_only():
    s=text('child/routes.py')
    block=s[s.index('def search_suggestions():'):s.index("@child_bp.route('/follow/")]
    assert "discoverable_children(session['user_id'],clean,5)" in block
    assert "FROM users\n        WHERE role='CHILD' AND account_status='ACTIVE'" not in block


def test_direct_profile_and_follow_are_discovery_gated():
    s=text('child/routes.py')
    profile=s[s.index('def view_profile(user_id):'):s.index("@child_bp.route('/discover/')")]
    follow=s[s.index('def follow(child_id):'):s.index("@child_bp.route('/block/")]
    assert "can_discover_child(session['user_id'],user_id)" in profile
    assert "can_discover_child(session['user_id'],child_id)" in follow


def test_discover_posts_are_not_platform_global():
    s=text('child/routes.py')
    block=s[s.index('def discover():'):s.index("@child_bp.route('/api/search/suggestions/')")]
    assert 'allowed_child_ids = [viewer_id] + discoverable_child_ids(viewer_id)' in block
    assert block.count('p.child_id = ANY(%s)') >= 2


def test_child_cannot_advance_parent_friendship_approval():
    s=text('child/routes.py')
    block=s[s.index('def accept_follow_request(requester_id):'):s.index('def decline_follow_request(requester_id):')]
    assert "Parent approval required" in block
    assert ',403' in block
    assert 'UPDATE followers SET approved=TRUE' not in block


def test_notifications_have_no_child_confirm_button():
    t=text('child/templates/notifications.html')
    assert '/accept/' not in t
    assert 'Parents decide' in t
    assert 'Parent approval required' in t
    assert 'Confirm</button>' not in t


def test_user_reports_cannot_target_hidden_children():
    s=text('child/routes.py')
    block=s[s.index('def report_content():'):s.index('def _check_live_frame(frame):')]
    assert "can_discover_child(session['user_id'],tid)" in block
