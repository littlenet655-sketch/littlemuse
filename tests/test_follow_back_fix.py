"""Regression tests for the follow-back / parentless-target fixes (defects C15, P5).

Covers, by source assertion (same pattern as test_two_parent_friendship.py):
1. BUG 1: tapping Follow Back on an incoming request must never delete the
   other child's request; the toggle is directional and the UI copy follows
   the server-returned status.
2. BUG 2: a follow request to a child with no approving parent/guardian is
   rejected with 400 instead of deadlocking at RECEIVER_PARENT_PENDING.
3. P5: stale follow-request resolutions surface a real error on both
   surfaces instead of failing silently.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text(encoding='utf-8')


def test_follow_toggle_is_directional_not_symmetric():
    api = text('mobile/api.py')
    service = text('child/service.py')
    # Directional helpers exist and query a single orientation.
    assert 'def outgoing_follow_pending(a,b):' in service
    assert 'def incoming_follow_pending(a,b):' in service
    assert 'WHERE approved=FALSE AND child_id=%s AND following_child_id=%s' in service
    # The endpoint branches on the directional checks, not the old symmetric
    # "is_following or is_follow_pending -> delete both" shortcut.
    assert 'if outgoing_follow_pending(uid, child_id):' in api
    assert 'if is_following(uid, child_id) or is_follow_pending(uid, child_id):' not in api


def test_follow_back_never_deletes_incoming_request():
    api = text('mobile/api.py')
    service = text('child/service.py')
    # Cancelling only ever touches my outgoing row plus trigger-generated
    # handshake rows; a genuine REQUESTED incoming row is never deleted.
    assert 'def cancel_outgoing_follow(a,b):' in service
    assert "approval_stage IN ('SENDER_PARENT_APPROVED','RECEIVER_PARENT_PENDING')" in service
    # Follow-back path creates my own request and reports it distinctly.
    assert 'if incoming_follow_pending(uid, child_id):' in api
    assert 'status="follow_back_pending"' in api
    assert 'status="cancelled"' in api


def test_parentless_target_is_rejected_not_deadlocked():
    api = text('mobile/api.py')
    service = text('child/service.py')
    assert 'def child_has_guardian(cid):' in service
    assert "approval_status='APPROVED'" in service
    assert 'if not child_has_guardian(child_id):' in api
    assert 'target_has_no_guardian' in api
    assert ", 400" in api  # rejected, not created


def test_client_copy_follows_server_status():
    screen = text('mobile_app/src/screens/kids/OtherProfileScreen.tsx')
    # Button state is directional: an incoming request must not read as
    # "Requested" (which would invite cancelling THEIR request).
    assert 'outgoingPending' in screen
    assert 'follow_back_pending' in screen
    # Toast copy comes from the server-returned status, never a hardcoded lie.
    assert 'FOLLOW_STATUS_COPY[res.status]' in screen
    assert 'Request sent! Both parents need to approve.' in screen


def test_stale_resolutions_surface_errors():
    routes = text('parent/routes.py')
    template = text('parent/templates/follow_requests.html')
    mobile_screen = text('mobile_app/src/screens/parent/ParentScreens.tsx')
    # Web: zero changed rows -> visible error banner, not a silent redirect.
    assert 'execute_count' in routes
    assert 'error=request_not_found' in routes
    assert "request.args.get('error') == 'request_not_found'" in template
    assert 'no longer pending' in template
    # Mobile: the approve/reject mutation reports failures to the parent.
    assert 'onError' in mobile_screen
    assert 'already have been handled' in mobile_screen
