from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text(encoding='utf-8')


def test_friendship_migration_is_part_of_every_database_init():
    init_db = text('tools/init_db.py')
    migration = text('database/friendship_upgrade.sql')
    assert "database/friendship_upgrade.sql" in init_db
    assert "ADD COLUMN IF NOT EXISTS approval_stage" in migration
    assert "'REQUESTED','SENDER_PARENT_APPROVED','RECEIVER_PARENT_PENDING','ACTIVE'" in migration


def test_legacy_single_parent_approval_is_intercepted_not_activated():
    migration = text('database/friendship_upgrade.sql')
    assert "OLD.approval_stage='REQUESTED'" in migration
    assert "NEW.approved=FALSE" in migration
    assert "NEW.approval_stage='SENDER_PARENT_APPROVED'" in migration
    assert "'RECEIVER_PARENT_PENDING'" in migration
    assert "INCOMING_FRIEND_REQUEST" in migration


def test_receiver_parent_is_required_to_activate_both_directions():
    migration = text('database/friendship_upgrade.sql')
    assert "OLD.approval_stage='RECEIVER_PARENT_PENDING'" in migration
    assert "NEW.approval_stage='ACTIVE'" in migration
    assert "approval_stage='ACTIVE'" in migration
    assert "WHERE child_id=OLD.following_child_id" in migration
    assert "AND following_child_id=OLD.child_id" in migration
    assert "FRIENDSHIP_ACTIVE" in migration


def test_existing_approved_friendships_are_grandfathered_and_mirrored():
    migration = text('database/friendship_upgrade.sql')
    assert "WHERE approved=TRUE" in migration
    assert "INSERT INTO followers(child_id,following_child_id,approved,approval_stage" in migration
    assert "SELECT following_child_id,child_id,TRUE,'ACTIVE'" in migration


def test_reject_unfriend_removes_symmetric_pair():
    migration = text('database/friendship_upgrade.sql')
    assert 'littlenet_friendship_delete_pair' in migration
    assert 'AFTER DELETE ON followers' in migration
    assert 'child_id=OLD.following_child_id' in migration
    assert 'following_child_id=OLD.child_id' in migration


def test_child_helpers_treat_friendship_as_symmetric_active_state():
    service = text('child/service.py')
    assert "approved=TRUE AND approval_stage='ACTIVE'" in service
    assert "((child_id=%s AND following_child_id=%s) OR (child_id=%s AND following_child_id=%s))" in service
    assert "VALUES(%s,%s,FALSE,'REQUESTED')" in service
    assert "DELETE FROM followers WHERE (child_id=%s AND following_child_id=%s) OR" in service


def test_chat_and_sharing_require_active_friendship():
    # One-to-one chat and internal sharing are gated on the ACTIVE two-parent
    # handshake via can_interact (server-side). Public content visibility must
    # NOT be gated on friendship (mission rule: approved content is visible to
    # all children, subject to age/category/block/mute).
    social = text('services/social.py')
    assert "approved=TRUE AND approval_stage='ACTIVE'" in social
    assert "Both parents must approve this friendship before sharing or messaging." in social
    # The ACTIVE gate lives in can_interact (chat/sharing path); the public
    # feed/reel/story/profile queries carry no friendship condition.
    can_interact_body = social.split('def _can_interact_uncached')[1].split('def visible_posts')[0]
    assert "approval_stage='ACTIVE'" in can_interact_body
    for fn in ('def visible_posts', 'def discoverable_posts', 'def active_stories',
               'def story_visible_to', 'def post_visible_to', 'def visible_profile_posts'):
        body = social.split(fn)[1]
        body = body.split('\ndef ')[0]
        assert 'followers' not in body and 'approval_stage' not in body, fn


def test_initial_request_is_not_notified_to_target_child_before_parent_one_approves():
    social = text('services/social.py')
    assert "if str(kind).upper()=='FOLLOW_REQUEST':" in social
    assert 'return None' in social


def test_parent_queue_has_outgoing_incoming_and_waiting_stages():
    service = text('parent/service.py')
    template = text('parent/templates/follow_requests.html')
    assert "approval_stage='REQUESTED'" in service
    assert "approval_stage='RECEIVER_PARENT_PENDING'" in service
    assert "approval_stage='SENDER_PARENT_APPROVED'" in service
    assert "'OUTGOING' AS approval_direction" in service
    assert "'INCOMING' AS approval_direction" in service
    assert "'WAITING' AS approval_direction" in service
    assert 'both children’s parents approve' in template
    assert '1 of 2 · Your approval' in template
    assert '2 of 2 · Final parent approval' in template
    assert 'Waiting for other parent' in template


def test_legacy_parent_route_remains_compatible_with_database_state_machine():
    routes = text('parent/routes.py')
    assert "UPDATE followers SET approved=TRUE" in routes
    assert "if not owns(session['user_id'],a)" in routes
    # Receiver approval is represented by the reciprocal row, whose child_id is
    # the receiving parent's own child, so the same ownership guard remains valid.
    migration = text('database/friendship_upgrade.sql')
    assert 'OLD.following_child_id,OLD.child_id' in migration


def test_mobile_first_parent_approval_never_claims_friendship_active():
    mobile = text('mobile/api.py')
    body = mobile.split('def mobile_parent_follow_action')[1].split('def mobile_parent_notifications')[0]
    assert '"FRIEND_ADDED"' not in body
    assert 'FRIEND_REQUEST_WAITING' in body
    assert 'Waiting for the other child\'s parent.' in body
    assert 'approval_stage' in body and '"ACTIVE"' in body
