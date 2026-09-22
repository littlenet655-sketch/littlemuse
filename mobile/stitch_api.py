from __future__ import annotations

from flask import g, jsonify, request

from child.service import can_discover_child, counts, is_follow_pending, is_following
from childMessage.service import conversation
from database.connection import execute, fetch_all, fetch_one
from extensions import csrf, limiter
from mobile.api import _child_gate, _clean, _post_json, _profile_json, _require_mobile
from services.social import can_interact, notify, parent_notify, post_visible_to, visible_profile_posts
from services.recommendation_signals import record_signal


def _gate():
    return _child_gate()


def _target_child(target_id: int):
    return fetch_one(
        """SELECT u.user_id,u.username,u.full_name,cp.bio,cp.profile_picture
           FROM users u
           LEFT JOIN child_profiles cp ON cp.child_id=u.user_id
           WHERE u.user_id=%s AND u.role='CHILD' AND u.account_status='ACTIVE'""",
        (target_id,),
    )


def _can_view_profile(viewer_id: int, target_id: int) -> bool:
    if viewer_id == target_id:
        return True
    return can_discover_child(viewer_id, target_id) or can_interact(viewer_id, target_id)


def _comment_rows(viewer_id: int, post_id: int):
    rows = fetch_all(
        """SELECT c.comment_id,c.post_id,c.child_id,c.comment_text,c.created_at,
                  u.full_name,u.username,cp.profile_picture
           FROM comments c
           JOIN users u ON u.user_id=c.child_id
           LEFT JOIN child_profiles cp ON cp.child_id=c.child_id
           WHERE c.post_id=%s AND c.moderation_status='ALLOWED'
           ORDER BY c.created_at ASC""",
        (post_id,),
    )
    out = []
    for row in rows:
        cid = int(row['child_id'])
        if cid != viewer_id and not _can_view_profile(viewer_id, cid):
            continue
        out.append(_profile_json(row))
    return out


def _validate_report_target(viewer_id: int, target_type: str, target_id: int):
    if target_type == 'USER':
        target = _target_child(target_id)
        if not target or target_id == viewer_id:
            return None
        return {'owner_id': target_id, 'content_type': 'USER', 'content_id': target_id}
    if target_type == 'POST':
        row = post_visible_to(viewer_id, target_id)
        if not row:
            return None
        ctype = 'VIDEO' if row.get('media_type') == 'VIDEO' else ('IMAGE' if row.get('media_type') == 'IMAGE' else 'TEXT')
        return {'owner_id': int(row['child_id']), 'content_type': ctype, 'content_id': target_id}
    if target_type == 'COMMENT':
        row = fetch_one('SELECT comment_id,post_id,child_id FROM comments WHERE comment_id=%s', (target_id,))
        if not row or not post_visible_to(viewer_id, int(row['post_id'])):
            return None
        return {'owner_id': int(row['child_id']), 'content_type': 'COMMENT', 'content_id': target_id}
    if target_type == 'MESSAGE':
        row = fetch_one(
            """SELECT child_message_id,sender_child_id,receiver_child_id
               FROM child_messages WHERE child_message_id=%s""",
            (target_id,),
        )
        if not row or viewer_id not in {int(row['sender_child_id']), int(row['receiver_child_id'])}:
            return None
        return {'owner_id': int(row['sender_child_id']), 'content_type': 'MESSAGE', 'content_id': target_id}
    return None


def register_mobile_stitch_api(bp):
    # Post detail is defined by mobile.api.register_mobile_api().  Keep this
    # stitch module limited to endpoints that are otherwise absent from the
    # canonical mobile API so registering it cannot create duplicate Flask
    # URL rules.

    @bp.route('/api/mobile/v1/kids/friends')
    @_require_mobile('CHILD')
    def mobile_kids_friends():
        blocked = _gate()
        if blocked:
            return blocked
        uid = int(g.mobile_user['user_id'])
        rows = fetch_all(
            """SELECT u.user_id,u.full_name,u.username,cp.profile_picture
               FROM followers f
               JOIN users u ON u.user_id=CASE WHEN f.child_id=%s THEN f.following_child_id ELSE f.child_id END
               LEFT JOIN child_profiles cp ON cp.child_id=u.user_id
               WHERE f.approved=TRUE AND f.approval_stage='ACTIVE'
                 AND (f.child_id=%s OR f.following_child_id=%s)
               ORDER BY u.full_name,u.user_id""",
            (uid, uid, uid),
        )
        return jsonify(ok=True, friends=[_profile_json(row) for row in rows])

    @bp.route('/api/mobile/v1/kids/chat/<int:peer_id>/share', methods=['POST'])
    @csrf.exempt
    @limiter.limit('30 per minute')
    @_require_mobile('CHILD')
    def mobile_kids_share_post(peer_id):
        blocked = _child_gate('messaging')
        if blocked:
            return blocked
        uid = int(g.mobile_user['user_id'])
        if not can_interact(uid, peer_id):
            return jsonify(error='approved_connection_required'), 403
        data = request.get_json(silent=True) or {}
        try:
            post_id = int(data.get('post_id'))
        except (TypeError, ValueError):
            return jsonify(error='invalid_post'), 400
        if not post_visible_to(uid, post_id) or not post_visible_to(peer_id, post_id):
            return jsonify(error='post_not_shareable'), 404
        cid = conversation(uid, peer_id)
        if not cid:
            return jsonify(error='approved_connection_required'), 403
        row = execute(
            """INSERT INTO child_messages(
                   conversation_id,sender_child_id,receiver_child_id,message_type,message_text,
                   shared_post_id,moderation_status,delivered_at
               ) VALUES(%s,%s,%s,'SHARED_POST','Shared a LittleNet post',%s,'ALLOWED',NOW())
               RETURNING child_message_id""",
            (cid, uid, peer_id, post_id),
            returning=True,
        )
        record_signal(uid, 'SOCIAL', post_id, 'SHARE')
        notify(peer_id, 'MESSAGE', f"{g.mobile_user.get('full_name') or 'A friend'} shared a post with you", f'/chat/{uid}/', uid)
        return jsonify(ok=True, message_id=int(row['child_message_id']))

    @bp.route('/api/mobile/v1/kids/saved')
    @_require_mobile('CHILD')
    def mobile_kids_saved():
        blocked = _gate()
        if blocked:
            return blocked
        uid = int(g.mobile_user['user_id'])
        rows = fetch_all(
            """SELECT p.*,u.full_name,u.username,cp.profile_picture,
                      (SELECT COUNT(*) FROM likes l WHERE l.post_id=p.post_id) likes,
                      (SELECT COUNT(*) FROM comments c WHERE c.post_id=p.post_id AND c.moderation_status='ALLOWED') comments_count
               FROM saved_posts s
               JOIN posts p ON p.post_id=s.post_id
               JOIN users u ON u.user_id=p.child_id
               LEFT JOIN child_profiles cp ON cp.child_id=p.child_id
               WHERE s.child_id=%s AND p.moderation_status='ALLOWED' AND p.is_safe=TRUE
               ORDER BY s.created_at DESC""",
            (uid,),
        )
        visible = []
        for row in rows:
            if post_visible_to(uid, int(row['post_id'])):
                visible.append(_post_json(row, uid))
        return jsonify(
            ok=True,
            posts=[p for p in visible if not p.get('is_reel')],
            reels=[p for p in visible if p.get('is_reel')],
            learning=[],
        )

    @bp.route('/api/mobile/v1/kids/profiles/<int:target_id>')
    @_require_mobile('CHILD')
    def mobile_kids_other_profile(target_id):
        blocked = _gate()
        if blocked:
            return blocked
        uid = int(g.mobile_user['user_id'])
        target = _target_child(target_id)
        if not target or not _can_view_profile(uid, target_id):
            return jsonify(error='profile_not_found'), 404
        interests = fetch_all(
            'SELECT interest_name FROM child_interests WHERE child_id=%s AND approved=TRUE ORDER BY interest_name LIMIT 12',
            (target_id,),
        )
        relationship = {
            'connected': is_following(uid, target_id) if uid != target_id else False,
            'pending': is_follow_pending(uid, target_id) if uid != target_id else False,
            'can_message': can_interact(uid, target_id) if uid != target_id else False,
        }
        return jsonify(
            ok=True,
            profile=_profile_json(target),
            counts=_clean(counts(target_id)),
            interests=[row['interest_name'] for row in interests],
            relationship=relationship,
            posts=[_post_json(row, uid) for row in visible_profile_posts(uid, target_id, 30)],
        )

    @bp.route('/api/mobile/v1/kids/profiles/<int:target_id>/actions', methods=['POST'])
    @csrf.exempt
    @limiter.limit('60 per minute')
    @_require_mobile('CHILD')
    def mobile_kids_profile_action(target_id):
        blocked = _gate()
        if blocked:
            return blocked
        uid = int(g.mobile_user['user_id'])
        if target_id == uid or not _target_child(target_id):
            return jsonify(error='invalid_target'), 400
        action = str((request.get_json(silent=True) or {}).get('action') or '').upper()
        if action == 'BLOCK':
            execute(
                'INSERT INTO blocked_users(blocker_id,blocked_id) VALUES(%s,%s) ON CONFLICT(blocker_id,blocked_id) DO NOTHING',
                (uid, target_id),
            )
            execute(
                'DELETE FROM followers WHERE (child_id=%s AND following_child_id=%s) OR (child_id=%s AND following_child_id=%s)',
                (uid, target_id, target_id, uid),
            )
        elif action == 'UNBLOCK':
            execute('DELETE FROM blocked_users WHERE blocker_id=%s AND blocked_id=%s', (uid, target_id))
        elif action == 'MUTE':
            execute(
                'INSERT INTO muted_users(muter_id,muted_id) VALUES(%s,%s) ON CONFLICT(muter_id,muted_id) DO NOTHING',
                (uid, target_id),
            )
        elif action == 'UNMUTE':
            execute('DELETE FROM muted_users WHERE muter_id=%s AND muted_id=%s', (uid, target_id))
        else:
            return jsonify(error='invalid_action'), 400
        return jsonify(ok=True, action=action)

    @bp.route('/api/mobile/v1/kids/reports', methods=['GET', 'POST'])
    @csrf.exempt
    @limiter.limit('30 per minute')
    @_require_mobile('CHILD')
    def mobile_kids_reports():
        blocked = _gate()
        if blocked:
            return blocked
        uid = int(g.mobile_user['user_id'])
        if request.method == 'GET':
            rows = fetch_all(
                """SELECT report_id,target_type,target_id,reason,details,status,created_at
                   FROM reports WHERE reporter_id=%s ORDER BY created_at DESC LIMIT 100""",
                (uid,),
            )
            return jsonify(ok=True, reports=_clean(rows))

        data = request.get_json(silent=True) or {}
        requested_type = str(data.get('target_type') or '').upper()
        target_type = 'POST' if requested_type in {'REEL', 'STORY'} else requested_type
        try:
            target_id = int(data.get('target_id'))
        except (TypeError, ValueError):
            return jsonify(error='invalid_target'), 400
        reason = str(data.get('reason') or '').strip()[:100]
        details = str(data.get('details') or '').strip()[:2000]
        if not reason:
            return jsonify(error='reason_required'), 400
        target = _validate_report_target(uid, target_type, target_id)
        if not target:
            return jsonify(error='report_target_not_found'), 404
        row = execute(
            """INSERT INTO reports(reporter_id,target_type,target_id,reason,details)
               VALUES(%s,%s,%s,%s,%s) RETURNING report_id""",
            (uid, target_type, target_id, reason, details or None),
            returning=True,
        )
        execute(
            """INSERT INTO moderation_events(child_id,content_type,content_id,risk_score,decision,reason,signals,status)
               VALUES(%s,%s,%s,50,'REVIEW',%s,%s::jsonb,'OPEN')""",
            (
                target['owner_id'],
                target['content_type'],
                target['content_id'],
                f'User report: {reason}',
                '{"source":"child_report"}',
            ),
        )
        parent_notify(uid, 'REPORT_SUBMITTED', 'A LittleNet safety report was submitted and is being reviewed.', '/parent/safety/')
        return jsonify(ok=True, report_id=int(row['report_id']), status='OPEN'), 201

    @bp.route('/api/mobile/v1/kids/safety')
    @_require_mobile('CHILD')
    def mobile_kids_safety():
        blocked = _gate()
        if blocked:
            return blocked
        uid = int(g.mobile_user['user_id'])
        events = fetch_all(
            """SELECT event_id,content_type,content_id,risk_score,decision,reason,status,created_at
               FROM moderation_events WHERE child_id=%s ORDER BY created_at DESC LIMIT 50""",
            (uid,),
        )
        reports = fetch_all(
            """SELECT report_id,target_type,target_id,reason,status,created_at
               FROM reports WHERE reporter_id=%s ORDER BY created_at DESC LIMIT 50""",
            (uid,),
        )
        return jsonify(
            ok=True,
            events=_clean(events),
            reports=_clean(reports),
            tips=[
                'Keep personal contact information private.',
                'Only message approved friends you know.',
                'If something feels wrong, keep it hidden and ask a parent for help.',
            ],
        )
