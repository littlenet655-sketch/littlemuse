import json
from flask import Blueprint, render_template, request, redirect, session, jsonify
from decorators import admin_required
from auth.service import parent_verification_complete
from database.connection import fetch_all, fetch_one, execute, get_db_connection

admin_bp = Blueprint('admin', __name__, template_folder='templates')


def _admin_audit(action, target_type=None, target_id=None, details=None):
    execute('''INSERT INTO admin_audit_logs(admin_id,action,target_type,target_id,details)
               VALUES(%s,%s,%s,%s,%s::jsonb)''',
            (session['user_id'], action, target_type, target_id,
             json.dumps(details or {})))


def _admin_audit_cursor(cur, action, target_type=None, target_id=None, details=None):
    """Write an admin transition into the same transaction as the state change."""
    cur.execute('''INSERT INTO admin_audit_logs(admin_id,action,target_type,target_id,details)
                   VALUES(%s,%s,%s,%s,%s::jsonb)''',
                (session['user_id'], action, target_type, target_id,
                 json.dumps(details or {})))


def _stats():
    return {
        'children': (fetch_one("SELECT COUNT(*) n FROM users WHERE role='CHILD'") or {'n':0})['n'],
        'parents': (fetch_one("SELECT COUNT(*) n FROM users WHERE role='PARENT'") or {'n':0})['n'],
        'active': (fetch_one("SELECT COUNT(*) n FROM users WHERE account_status='ACTIVE'") or {'n':0})['n'],
        'suspended': (fetch_one("SELECT COUNT(*) n FROM users WHERE account_status='SUSPENDED'") or {'n':0})['n'],
        'open_reports': (fetch_one("SELECT COUNT(*) n FROM reports WHERE status IN ('OPEN','REVIEWING')") or {'n':0})['n'],
        'open_reviews': (fetch_one("SELECT COUNT(*) n FROM moderation_events WHERE decision='REVIEW' AND status='OPEN'") or {'n':0})['n'],
        'blocked_7d': (fetch_one("SELECT COUNT(*) n FROM moderation_events WHERE decision='BLOCK' AND created_at>NOW()-INTERVAL '7 days'") or {'n':0})['n'],
        'adult_blocks_7d': (fetch_one("SELECT COUNT(*) n FROM moderation_events WHERE decision='BLOCK' AND adult_score>=40 AND created_at>NOW()-INTERVAL '7 days'") or {'n':0})['n'],
    }


@admin_bp.route('/admin/')
@admin_required
def dashboard():
    decisions = fetch_all("""SELECT decision,COUNT(*) n FROM moderation_events
                           WHERE created_at>NOW()-INTERVAL '7 days' GROUP BY decision ORDER BY decision""")
    return render_template('admin_dashboard.html', stats=_stats(), decisions=decisions,
        reports=fetch_all("""SELECT r.*,u.full_name reporter_name FROM reports r
                           JOIN users u ON u.user_id=r.reporter_id
                           WHERE r.status IN ('OPEN','REVIEWING') ORDER BY r.created_at DESC LIMIT 8"""),
        events=fetch_all("""SELECT e.*,u.full_name FROM moderation_events e
                          LEFT JOIN users u ON u.user_id=e.child_id
                          ORDER BY e.created_at DESC LIMIT 12"""),
        audit=fetch_all("""SELECT a.*,u.full_name admin_name FROM admin_audit_logs a
                         JOIN users u ON u.user_id=a.admin_id ORDER BY a.created_at DESC LIMIT 10"""))


@admin_bp.route('/admin/users/')
@admin_required
def users():
    q=(request.args.get('q') or '').strip(); role=(request.args.get('role') or '').upper(); status=(request.args.get('status') or '').upper()
    sql="SELECT user_id,username,full_name,email,role,account_status,created_at FROM users WHERE 1=1"; params=[]
    if q:
        sql += " AND (full_name ILIKE %s OR email ILIKE %s OR username ILIKE %s)"; params += [f'%{q}%']*3
    if role in {'CHILD','PARENT','ADMIN'}: sql += ' AND role=%s'; params.append(role)
    if status in {'ACTIVE','PENDING_APPROVAL','REJECTED','SUSPENDED'}: sql += ' AND account_status=%s'; params.append(status)
    sql += ' ORDER BY created_at DESC LIMIT 250'
    return render_template('admin_users.html', users=fetch_all(sql,tuple(params)), q=q, role=role, status=status)


@admin_bp.route('/admin/reports/')
@admin_required
def reports():
    rows=fetch_all("""SELECT r.*,u.full_name reporter_name FROM reports r
                    JOIN users u ON u.user_id=r.reporter_id ORDER BY r.created_at DESC LIMIT 250""")
    return render_template('admin_reports.html', reports=rows)


@admin_bp.route('/admin/moderation/')
@admin_required
def moderation():
    rows=fetch_all("""SELECT e.*,u.full_name FROM moderation_events e LEFT JOIN users u ON u.user_id=e.child_id
                    ORDER BY CASE WHEN e.status='OPEN' THEN 0 ELSE 1 END,e.created_at DESC LIMIT 300""")
    return render_template('admin_moderation.html', events=rows)


@admin_bp.route('/admin/audit/')
@admin_required
def audit():
    rows=fetch_all("""SELECT a.*,u.full_name admin_name FROM admin_audit_logs a JOIN users u ON u.user_id=a.admin_id
                    ORDER BY a.created_at DESC LIMIT 300""")
    return render_template('admin_audit.html', rows=rows)


@admin_bp.route('/admin/report/<int:report_id>/', methods=['POST'])
@admin_required
def report_action(report_id):
    status=request.form.get('status','').upper()
    if status not in {'REVIEWING','RESOLVED','DISMISSED'}: return ('Invalid',400)
    row=fetch_one('SELECT status FROM reports WHERE report_id=%s',(report_id,))
    if not row: return ('Not found',404)
    execute('UPDATE reports SET status=%s WHERE report_id=%s',(status,report_id))
    _admin_audit('REPORT_STATUS','REPORT',report_id,{'from':row['status'],'to':status})
    return redirect(request.referrer or '/admin/reports/')


@admin_bp.route('/admin/user/<int:user_id>/', methods=['POST'])
@admin_required
def user_action(user_id):
    action=request.form.get('action','').upper()
    if action not in {'SUSPEND','ACTIVATE','DELETE'}: return ('Invalid',400)
    row=fetch_one("SELECT role,account_status FROM users WHERE user_id=%s AND role<>'ADMIN'",(user_id,))
    if not row: return ('Not found',404)
    if action == 'DELETE':
        execute('DELETE FROM users WHERE user_id=%s',(user_id,))
        _admin_audit('USER_DELETE','USER',user_id,{'role':row['role'],'status':row['account_status']})
    else:
        new='SUSPENDED' if action=='SUSPEND' else 'ACTIVE'
        if new == 'ACTIVE' and row['role'] == 'PARENT' and not parent_verification_complete(user_id):
            # Server-side enforcement: an admin must not activate a parent
            # that never completed identity verification (email OTP only).
            # UI hiding is not security.
            _admin_audit('USER_ACTIVATE_BLOCKED','USER',user_id,{'role':row['role'],'status':row['account_status'],'reason':'parent_verification_incomplete'})
            return ('Parent identity verification is incomplete: activation blocked. The parent must complete email OTP verification first.',403)
        execute('UPDATE users SET account_status=%s, session_version = COALESCE(session_version, 1) + 1 WHERE user_id=%s',(new,user_id))
        _admin_audit('USER_'+action,'USER',user_id,{'from':row['account_status'],'to':new})
    return redirect(request.referrer or '/admin/users/')



@admin_bp.route('/admin/moderation/<int:event_id>/block/', methods=['POST'])
@admin_required
def block_review_event(event_id):
    conn=get_db_connection()
    try:
        cur=conn.cursor();cur.execute("SELECT * FROM moderation_events WHERE event_id=%s AND status='OPEN' FOR UPDATE",(event_id,));e=cur.fetchone()
        if not e: conn.rollback(); return ('Not found or already resolved',404)
        if e['decision']!='REVIEW': conn.rollback(); return ('Only open REVIEW items can be moderator-blocked',400)
        if e['content_type'] in {'IMAGE','VIDEO','AUDIO','TEXT'} and e['content_id']:
            cur.execute("UPDATE posts SET moderation_status='BLOCKED',is_safe=FALSE WHERE post_id=%s",(e['content_id'],))
        elif e['content_type']=='COMMENT' and e['content_id']:
            cur.execute("UPDATE comments SET moderation_status='BLOCKED' WHERE comment_id=%s",(e['content_id'],))
        elif e['content_type']=='MESSAGE' and e['content_id']:
            cur.execute("UPDATE child_messages SET moderation_status='BLOCKED' WHERE child_message_id=%s",(e['content_id'],))
        cur.execute("UPDATE moderation_events SET status='RESOLVED' WHERE event_id=%s",(event_id,))
        _admin_audit_cursor(cur,'MODERATOR_BLOCK','MODERATION_EVENT',event_id,{'child_id':e['child_id'],'content_type':e['content_type']})
        conn.commit()
        if e['child_id']:
            from services.social import parent_notify
            parent_notify(e['child_id'],'MODERATOR_BLOCK','A moderator blocked a reviewed item.','/parent/safety/')
        return redirect('/admin/moderation/')
    except Exception:
        conn.rollback();raise
    finally:conn.close()


@admin_bp.route('/admin/post/<int:post_id>/remove/', methods=['POST'])
@admin_required
def remove_post(post_id):
    conn=get_db_connection()
    try:
        cur=conn.cursor();cur.execute('SELECT post_id,child_id,moderation_status,is_safe FROM posts WHERE post_id=%s FOR UPDATE',(post_id,));row=cur.fetchone()
        if not row:conn.rollback();return ('Not found',404)
        if row['moderation_status']!='BLOCKED' or row['is_safe']:
            cur.execute("UPDATE posts SET moderation_status='BLOCKED',is_safe=FALSE,moderation_reason=COALESCE(moderation_reason,'Removed by moderator') WHERE post_id=%s",(post_id,))
        _admin_audit_cursor(cur,'POST_REMOVED','POST',post_id,{'child_id':row['child_id'],'previous_status':row['moderation_status']})
        conn.commit()
    except Exception:
        conn.rollback();raise
    finally:conn.close()
    from services.social import parent_notify
    parent_notify(row['child_id'],'MODERATOR_POST_BLOCK','A moderator removed a post from Kids Mode.','/parent/notifications/')
    return redirect(request.referrer or '/admin/moderation/')
