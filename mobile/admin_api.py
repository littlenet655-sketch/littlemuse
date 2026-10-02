from __future__ import annotations

import json

from flask import g, jsonify, request

from database.connection import fetch_all, fetch_one, get_db_connection
from auth.service import parent_verification_complete
from extensions import csrf, limiter
from mobile.api import _asset_url, _clean, _json_dict, _require_mobile, _resolve_parent_review
from mobile.stitch_api import register_mobile_stitch_api


def register_mobile_admin_api(bp):
    # Register the additional React Native screen contracts on the same
    # bearer-token blueprint. Keeping this here avoids a second app blueprint
    # and preserves the existing /api/mobile/v1/* authentication boundary.
    register_mobile_stitch_api(bp)

    @bp.route('/api/mobile/v1/admin/reviews/<int:event_id>', methods=['GET', 'POST'])
    @csrf.exempt
    @limiter.limit('60 per minute')
    @_require_mobile('ADMIN')
    def mobile_admin_review_detail(event_id):
        event = fetch_one(
            """SELECT e.*,u.full_name,u.username
               FROM moderation_events e JOIN users u ON u.user_id=e.child_id
               WHERE e.event_id=%s""",
            (event_id,),
        )
        if not event:
            return jsonify(error='review_not_found'), 404

        if request.method == 'GET':
            preview = None
            ctype = event.get('content_type')
            cid = event.get('content_id')
            if cid and ctype in {'IMAGE', 'VIDEO', 'TEXT'}:
                preview = fetch_one(
                    'SELECT media_type,media_path,source_media_path,poster_path,caption,moderation_status FROM posts WHERE post_id=%s',
                    (cid,),
                )
            elif cid and ctype == 'COMMENT':
                preview = fetch_one(
                    'SELECT comment_text,moderation_status FROM comments WHERE comment_id=%s',
                    (cid,),
                )
            elif cid and ctype == 'MESSAGE':
                preview = fetch_one(
                    'SELECT message_type,message_text,media_path,moderation_status FROM child_messages WHERE child_message_id=%s',
                    (cid,),
                )
            elif cid and ctype == 'USER':
                preview = fetch_one(
                    """SELECT user_id,username,full_name,role,age,account_status,created_at
                       FROM users WHERE user_id=%s""",
                    (cid,),
                )
            if preview:
                preview = dict(preview)
                source_ref = preview.pop('source_media_path', None)
                published_ref = preview.pop('media_path', None)
                media_ref = source_ref or published_ref
                poster_ref = preview.pop('poster_path', None)
                if media_ref:
                    preview['media_url'] = _asset_url(media_ref)
                if poster_ref:
                    preview['poster_url'] = _asset_url(poster_ref)
            return jsonify(ok=True, event=_clean(event), preview=_clean(preview))

        data = _json_dict()
        requested = str(data.get('action') or '').upper()
        if requested not in {'APPROVE', 'BLOCK', 'ESCALATE'}:
            return jsonify(error='invalid_action'), 400

        if requested == 'ESCALATE':
            conn = get_db_connection()
            try:
                cur = conn.cursor()
                cur.execute(
                    "SELECT * FROM moderation_events WHERE event_id=%s AND decision='REVIEW' AND status='OPEN' FOR UPDATE",
                    (event_id,),
                )
                locked = cur.fetchone()
                if not locked:
                    conn.rollback()
                    return jsonify(error='review_already_resolved'), 409
                # Production migration 20260908093000 makes moderation_reviews
                # append-only and permits ESCALATE. Record the escalation while
                # deliberately leaving the event OPEN for a later final decision.
                cur.execute(
                    'INSERT INTO moderation_reviews(event_id,reviewer_id,action,notes) VALUES(%s,%s,%s,%s)',
                    (
                        event_id,
                        g.mobile_user['user_id'],
                        'ESCALATE',
                        str(data.get('notes') or 'Escalated by moderator'),
                    ),
                )
                cur.execute(
                    """INSERT INTO admin_audit_logs(admin_id,action,target_type,target_id,details)
                       VALUES(%s,'MODERATION_ESCALATE','MODERATION_EVENT',%s,%s::jsonb)""",
                    (g.mobile_user['user_id'], event_id, json.dumps({'child_id': locked['child_id']})),
                )
                conn.commit()
                return jsonify(ok=True, action='ESCALATE', status='OPEN')
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

        ok, result = _resolve_parent_review(
            int(g.mobile_user['user_id']),
            event_id,
            requested,
            is_admin=True,
            notes=str(data.get('notes') or '') or None,
        )
        status = 200 if ok else 404 if result == 'not_found' else 400
        return jsonify(ok=ok, action=result if ok else requested, status='RESOLVED' if ok else result), status

    @bp.route('/api/mobile/v1/admin/users')
    @_require_mobile('ADMIN')
    def mobile_admin_users():
        q = str(request.args.get('q') or '').strip()
        pattern = f'%{q}%'
        rows = fetch_all(
            """SELECT user_id,username,full_name,email,role,age,account_status,demo_unlimited,created_at
               FROM users
               WHERE (%s='' OR full_name ILIKE %s OR username ILIKE %s OR email ILIKE %s)
               ORDER BY created_at DESC LIMIT 100""",
            (q, pattern, pattern, pattern),
        )
        return jsonify(ok=True, users=_clean(rows))

    @bp.route('/api/mobile/v1/admin/users/<int:target_user_id>/demo-unlimited', methods=['POST'])
    @csrf.exempt
    @limiter.limit('30 per minute')
    @_require_mobile('ADMIN')
    def mobile_admin_demo_unlimited(target_user_id):
        data = _json_dict()
        enabled = data.get('enabled')
        if not isinstance(enabled, bool):
            return jsonify(error='enabled_boolean_required'), 400
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT role,account_status,demo_unlimited FROM users WHERE user_id=%s FOR UPDATE",
                (target_user_id,),
            )
            target = cur.fetchone()
            if not target:
                conn.rollback()
                return jsonify(error='user_not_found'), 404
            if target['role'] != 'CHILD':
                conn.rollback()
                return jsonify(error='demo_unlimited_child_only'), 400
            if target['account_status'] == 'DEACTIVATED':
                conn.rollback()
                return jsonify(error='account_inactive'), 400
            cur.execute(
                "UPDATE users SET demo_unlimited=%s WHERE user_id=%s",
                (enabled, target_user_id),
            )
            cur.execute(
                """INSERT INTO admin_audit_logs(admin_id,action,target_type,target_id,details)
                   VALUES(%s,'DEMO_UNLIMITED','USER',%s,%s::jsonb)""",
                (
                    g.mobile_user['user_id'],
                    target_user_id,
                    json.dumps({'enabled': enabled, 'previous': bool(target.get('demo_unlimited'))}),
                ),
            )
            conn.commit()
            return jsonify(ok=True, user_id=target_user_id, demo_unlimited=enabled)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @bp.route('/api/mobile/v1/admin/users/<int:target_user_id>/status', methods=['POST'])
    @csrf.exempt
    @limiter.limit('30 per minute')
    @_require_mobile('ADMIN')
    def mobile_admin_user_status(target_user_id):
        data = _json_dict()
        new_status = str(data.get('status') or '').upper()
        if new_status not in {'ACTIVE', 'SUSPENDED'}:
            return jsonify(error='invalid_status'), 400
        if int(target_user_id) == int(g.mobile_user['user_id']):
            return jsonify(error='cannot_modify_self'), 400
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT role,account_status FROM users WHERE user_id=%s AND role<>'ADMIN' FOR UPDATE", (target_user_id,))
            target = cur.fetchone()
            if not target:
                conn.rollback()
                return jsonify(error='user_not_found'), 404
            if new_status == 'ACTIVE' and target['role'] == 'PARENT' and not parent_verification_complete(int(target_user_id)):
                # Server-side enforcement: an admin must not activate a parent
                # that never completed identity verification (email OTP only).
                # UI hiding is not security.
                conn.rollback()
                cur.execute(
                    """INSERT INTO admin_audit_logs(admin_id,action,target_type,target_id,details)
                       VALUES(%s,'USER_STATUS_BLOCKED','USER',%s,%s::jsonb)""",
                    (
                        g.mobile_user['user_id'],
                        target_user_id,
                        json.dumps({'from': target['account_status'], 'to': new_status, 'role': target['role'], 'reason': 'parent_verification_incomplete'}),
                    ),
                )
                conn.commit()
                return jsonify(error='parent_verification_incomplete'), 403
            cur.execute("UPDATE users SET account_status=%s, session_version = COALESCE(session_version, 1) + 1 WHERE user_id=%s", (new_status, target_user_id))
            cur.execute(
                """INSERT INTO admin_audit_logs(admin_id,action,target_type,target_id,details)
                   VALUES(%s,'USER_STATUS','USER',%s,%s::jsonb)""",
                (
                    g.mobile_user['user_id'],
                    target_user_id,
                    json.dumps({'from': target['account_status'], 'to': new_status, 'role': target['role']}),
                ),
            )
            conn.commit()
            return jsonify(ok=True, user_id=target_user_id, status=new_status)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @bp.route('/api/mobile/v1/admin/users/<int:target_user_id>', methods=['DELETE'])
    @csrf.exempt
    @limiter.limit('20 per minute')
    @_require_mobile('ADMIN')
    def mobile_admin_delete_user(target_user_id):
        if int(target_user_id) == int(g.mobile_user['user_id']):
            return jsonify(error='cannot_delete_self'), 400
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT role,account_status FROM users WHERE user_id=%s AND role<>'ADMIN' FOR UPDATE",
                (target_user_id,),
            )
            target = cur.fetchone()
            if not target:
                conn.rollback()
                return jsonify(error='user_not_found'), 404
            cur.execute(
                """UPDATE users
                   SET account_status='DEACTIVATED',
                       session_version=COALESCE(session_version,1)+1
                   WHERE user_id=%s""",
                (target_user_id,),
            )
            cur.execute(
                """INSERT INTO admin_audit_logs(admin_id,action,target_type,target_id,details)
                   VALUES(%s,'USER_DEACTIVATE','USER',%s,%s::jsonb)""",
                (
                    g.mobile_user['user_id'],
                    target_user_id,
                    json.dumps({'from': target['account_status'], 'role': target['role']}),
                ),
            )
            conn.commit()
            return jsonify(ok=True, user_id=target_user_id, status='DEACTIVATED')
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @bp.route('/api/mobile/v1/admin/audit')
    @_require_mobile('ADMIN')
    def mobile_admin_audit():
        rows = fetch_all(
            """SELECT a.audit_id,a.admin_id,u.full_name AS admin_name,a.action,
                      a.target_type,a.target_id,a.details,a.created_at
               FROM admin_audit_logs a JOIN users u ON u.user_id=a.admin_id
               ORDER BY a.created_at DESC LIMIT 100"""
        )
        return jsonify(ok=True, events=_clean(rows))

