from flask import Blueprint,render_template,request,redirect,session,jsonify
from extensions import limiter
from decorators import parent_required
from parent.service import children,owns,pending_follows
from database.connection import fetch_one,fetch_all,execute,execute_count,get_db_connection
from services.usage import minutes_today, online_state
from services.social import notify
from services.behavior import behavior_summary
from services.controls import controls_for_child, save_controls, SAFE_CATEGORIES
from services.audit import log
from auth.service import create_child_by_parent
from safety.text_service import check_text
from safety.policy import decide
parent_bp=Blueprint('parent',__name__,template_folder='templates')
@parent_bp.route('/parent/dashboard/')
@parent_required
def dashboard():
    kids=children(session['user_id'])
    for k in kids:
        cid=k['user_id']
        k['minutes_today']=minutes_today(cid)
        k['limit']=fetch_one('SELECT * FROM child_time_limits WHERE child_id=%s',(cid,))
        k['safety']=fetch_one('SELECT safety_level FROM parent_safety_settings WHERE child_id=%s',(cid,)) or {'safety_level':'STRICT'}
        # Badge must agree with the safety queue (same approved-mapping filter),
        # matching the mobile dashboard open_reviews filter.
        k['open_reviews']=(fetch_one("SELECT COUNT(*) n FROM moderation_events e WHERE e.child_id=%s AND e.decision='REVIEW' AND e.status='OPEN' AND EXISTS (SELECT 1 FROM parent_child_map m JOIN users p ON p.user_id=%s AND p.role='PARENT' AND p.account_status='ACTIVE' WHERE m.child_id=e.child_id AND m.approved=TRUE AND m.approval_status='APPROVED' AND (m.parent_id=%s OR m.verified_parent_id=%s))",(cid,session['user_id'],session['user_id'],session['user_id'])) or {'n':0})['n']
        k['controls']=controls_for_child(cid)
        k['presence']=online_state(cid)
        k['behavior']=behavior_summary(cid)
        quiz=fetch_one("""SELECT COUNT(*) attempted,COUNT(*) FILTER (WHERE is_correct) correct
            FROM child_quiz_attempts WHERE child_id=%s AND attempted_at>=NOW()-INTERVAL '7 days'""",(cid,)) or {'attempted':0,'correct':0}
        attempted=int(quiz.get('attempted') or 0);correct=int(quiz.get('correct') or 0)
        k['quiz_7d']={'attempted':attempted,'correct':correct,'accuracy':round(correct*100/attempted) if attempted else 0}
    parent_user = fetch_one("SELECT email FROM users WHERE user_id=%s", (session['user_id'],))
    p_email = (parent_user.get('email') or '').lower() if parent_user else ''
    pending_children = fetch_all("""
        SELECT pcm.approval_token, pcm.verification_token, pcm.child_id, u.username, u.full_name, u.created_at
        FROM parent_child_map pcm
        JOIN users u ON u.user_id = pcm.child_id
        WHERE (pcm.parent_id = %s OR LOWER(pcm.parent_email) = %s)
          AND pcm.approved = FALSE
          AND u.account_status = 'PENDING_APPROVAL'
          AND pcm.approval_status <> 'PENDING_EMAIL_CONFIRMATION'
        ORDER BY u.created_at DESC
    """, (session['user_id'], p_email))
    awaiting_email_confirmation = fetch_all("""
        SELECT pcm.child_id, u.username, u.full_name, u.created_at
        FROM parent_child_map pcm
        JOIN users u ON u.user_id = pcm.child_id
        WHERE pcm.parent_id = %s
          AND pcm.approved = FALSE
          AND pcm.approval_status = 'PENDING_EMAIL_CONFIRMATION'
        ORDER BY u.created_at DESC
    """, (session['user_id'],))
    unread=(fetch_one('SELECT COUNT(*) n FROM parent_notifications WHERE parent_id=%s AND is_read=FALSE',(session['user_id'],)) or {'n':0})['n']
    return render_template('parent_dashboard.html',children=kids,pending=pending_follows(session['user_id']),unread=unread,pending_children=pending_children,awaiting_email_confirmation=awaiting_email_confirmation)

@parent_bp.route('/parent/quick-approve-child/', methods=['POST'])
@parent_required
def quick_approve_child():
    try:
        child_id = int(request.form.get('child_id', 0))
    except (TypeError, ValueError):
        return ('Invalid child', 400)
    action = request.form.get('action', 'approve')
    parent_id = session['user_id']
    # Must be the parent this child actually named (by account link or by the
    # parent_email they registered with) -- never let any logged-in parent
    # approve/activate an arbitrary child_id.
    parent_row = fetch_one('SELECT email FROM users WHERE user_id=%s', (parent_id,))
    parent_email = (parent_row.get('email') or '').lower() if parent_row else ''
    mapping = fetch_one(
        "SELECT map_id,approval_status FROM parent_child_map WHERE child_id=%s AND approved=FALSE AND (parent_id=%s OR LOWER(parent_email)=%s)",
        (child_id, parent_id, parent_email)
    )
    if not mapping:
        return ('Forbidden: this child is not linked to your account', 403)
    if mapping.get('approval_status') == 'PENDING_EMAIL_CONFIRMATION':
        # This child was created by a parent and requires the emailed
        # confirmation link, not this legacy quick-approve shortcut.
        return ('This account requires email confirmation. Check your inbox for the confirmation link.', 403)
    if action == 'approve':
        execute("UPDATE users SET account_status = 'ACTIVE' WHERE user_id = %s", (child_id,))
        execute("""
            UPDATE parent_child_map 
            SET approved = TRUE, 
                approved_at = NOW(), 
                approval_status = 'APPROVED',
                parent_id = %s,
                verified_parent_id = COALESCE(verified_parent_id, %s)
            WHERE child_id = %s
        """, (parent_id, parent_id, child_id))
        execute("""
            INSERT INTO parent_safety_settings(child_id, parent_id, safety_level)
            VALUES(%s, %s, 'STRICT')
            ON CONFLICT (child_id) DO UPDATE SET parent_id = EXCLUDED.parent_id
        """, (child_id, parent_id))
        execute("""
            INSERT INTO child_time_limits(child_id, daily_limit_minutes, strict_mode)
            VALUES(%s, 60, TRUE)
            ON CONFLICT (child_id) DO NOTHING
        """, (child_id,))
        execute("""
            INSERT INTO parent_control_settings(child_id, parent_id, allow_reels, allow_stories, allow_messaging, allow_posting, allow_discover, educational_only_feed)
            VALUES(%s, %s, TRUE, TRUE, TRUE, TRUE, TRUE, FALSE)
            ON CONFLICT (child_id) DO NOTHING
        """, (child_id, parent_id))
    else:
        execute("UPDATE users SET account_status = 'REJECTED' WHERE user_id = %s", (child_id,))
        execute("UPDATE parent_child_map SET approval_status = 'DECLINED' WHERE child_id = %s", (child_id,))
    return redirect('/parent/dashboard/')
@parent_bp.route('/parent/create-child/',methods=['GET','POST'])
@parent_required
def create_child():
    if request.method=='POST':
        public_text=' '.join(str(request.form.get(k,'') or '') for k in ['full_name','school_name','location','current_class','bio'])
        signals=check_text(public_text);decision=decide(signals,'STRICT')
        if decision.action!='ALLOW':
            return render_template('parent_create_child.html',error='Child profile text could not be published under LittleNet safety rules.'),400
        try:
            child_id,_token=create_child_by_parent(session['user_id'],request.form)
            child=fetch_one('SELECT full_name FROM users WHERE user_id=%s',(child_id,)) or {'full_name':'Your child'}
            return render_template(
                'approval_success.html',
                title='Check your email to activate the account',
                message=f"We created {child['full_name']}'s LittleNet account, but it will not work until you confirm it. Open the confirmation email we just sent to your parent account's inbox and tap Confirm & activate account.",
                button_url='/parent/dashboard/',
                button_text='Go to Parent Dashboard'
            )
        except Exception:
            return render_template('parent_create_child.html',error='Child account could not be created. Check duplicate email/username and all required values.'),400
    return render_template('parent_create_child.html')

@parent_bp.route('/parent/confirm-child/<token>/', methods=['GET'])
@parent_required
def confirm_child(token):
    mapping=fetch_one(
        "SELECT map_id,child_id FROM parent_child_map WHERE approval_token=%s AND parent_id=%s AND approved=FALSE AND approval_status='PENDING_EMAIL_CONFIRMATION'",
        (token, session['user_id'])
    )
    if not mapping:
        return render_template(
            'approval_success.html', is_error=True,
            title='Link invalid or already used',
            message='This confirmation link is invalid, expired, or the account is already active.',
            button_url='/parent/dashboard/', button_text='Go to Parent Dashboard'
        ), 400
    execute("UPDATE users SET account_status='ACTIVE' WHERE user_id=%s", (mapping['child_id'],))
    execute("UPDATE parent_child_map SET approved=TRUE,approved_at=NOW(),is_token_used=TRUE,approval_status='APPROVED' WHERE map_id=%s", (mapping['map_id'],))
    log(mapping['child_id'],'ACCOUNT_EMAIL_CONFIRMED',{'confirmed_by':session['user_id']})
    child=fetch_one('SELECT full_name FROM users WHERE user_id=%s',(mapping['child_id'],)) or {'full_name':'Your child'}
    return render_template(
        'approval_success.html', is_verified=True,
        title='Account activated!',
        message=f"{child['full_name']}'s LittleNet account is now active and ready to log in under your Parent Mode controls.",
        button_url='/parent/dashboard/', button_text='Go to Parent Dashboard'
    )

@parent_bp.route('/parent/follow-requests/')
@parent_required
def follows():return render_template('follow_requests.html',pending=pending_follows(session['user_id']))
@parent_bp.route('/parent/follow-action/',methods=['POST'])
@parent_required
def follow_action():
    try:a=int(request.form['child_id']);b=int(request.form['target_id'])
    except:return jsonify(error='invalid ids'),400
    if not owns(session['user_id'],a):return jsonify(error='forbidden'),403
    action=request.form.get('action')
    if action=='approve':changed=execute_count("UPDATE followers SET approved=TRUE WHERE child_id=%s AND following_child_id=%s AND approved=FALSE AND approval_stage IN ('REQUESTED','RECEIVER_PARENT_PENDING')",(a,b))
    elif action=='reject':changed=execute_count("DELETE FROM followers WHERE approved=FALSE AND ((child_id=%s AND following_child_id=%s) OR (child_id=%s AND following_child_id=%s AND approval_stage IN ('SENDER_PARENT_APPROVED','RECEIVER_PARENT_PENDING')))",(a,b,b,a))
    else:return jsonify(error='invalid action'),400
    if not changed:
        # Stale or already-handled request: say so instead of redirecting silently.
        return redirect('/parent/follow-requests/?error=request_not_found')
    return redirect('/parent/follow-requests/')
@parent_bp.route('/parent/time-limit/',methods=['GET','POST'])
@parent_required
def time_limit():
    kids=children(session['user_id']);cid=int(request.values.get('child_id') or (kids[0]['user_id'] if kids else 0))
    if not owns(session['user_id'],cid):return ('Forbidden',403)
    if request.method=='POST':
        action=request.form.get('action') or 'save_limit'
        if action=='approve_extension':
            return _web_extension_decide(cid,'APPROVED')
        if action=='reject_extension':
            return _web_extension_decide(cid,'REJECTED')
        try:mins=int(request.form['daily_limit'])
        except:return ('Invalid limit',400)
        if not 1<=mins<=1440:return ('Limit must be 1-1440 minutes',400)
        execute('INSERT INTO child_time_limits(child_id,daily_limit_minutes,strict_mode) VALUES(%s,%s,%s) ON CONFLICT(child_id) DO UPDATE SET daily_limit_minutes=EXCLUDED.daily_limit_minutes,strict_mode=EXCLUDED.strict_mode,updated_at=NOW()',(cid,mins,'strict_mode' in request.form));return redirect(f'/parent/time-limit/?child_id={cid}')
    execute("UPDATE screen_time_extension_requests SET status='EXPIRED' WHERE status='PENDING' AND created_at::date < CURRENT_DATE")
    pending=fetch_all('''SELECT r.request_id,r.requested_minutes,r.created_at,u.full_name AS child_name
        FROM screen_time_extension_requests r JOIN users u ON u.user_id=r.child_id
        WHERE r.child_id=%s AND r.status='PENDING' ORDER BY r.created_at ASC''',(cid,)) or []
    return render_template('time_limit.html',child_id=cid,limit=fetch_one('SELECT * FROM child_time_limits WHERE child_id=%s',(cid,)),extension_requests=pending)


def _web_extension_decide(cid, decision):
    pid=session['user_id']
    try:req_id=int(request.form['request_id'])
    except:return ('Invalid request',400)
    req=fetch_one("SELECT request_id,child_id,requested_minutes FROM screen_time_extension_requests WHERE request_id=%s AND status='PENDING'",(req_id,))
    if not req or int(req['child_id'])!=cid or not owns(pid,cid):return ('Forbidden',403)
    if decision=='APPROVED':
        try:granted=int(request.form.get('granted_minutes') or req['requested_minutes'])
        except:return ('Invalid minutes',400)
        if not 1<=granted<=720:return ('Grant 1-720 minutes',400)
        moved=execute_count("UPDATE screen_time_extension_requests SET status='APPROVED',decided_at=NOW(),decided_by=%s,granted_minutes=%s WHERE request_id=%s AND status='PENDING'",(pid,granted,req_id))
        if not moved:return redirect(f'/parent/time-limit/?child_id={cid}')
        execute('''INSERT INTO child_time_limits(child_id,daily_limit_minutes,strict_mode,bonus_minutes,bonus_date)
                   VALUES(%s,60,TRUE,%s,CURRENT_DATE)
                   ON CONFLICT(child_id) DO UPDATE SET
                     bonus_minutes=CASE WHEN child_time_limits.bonus_date=CURRENT_DATE THEN child_time_limits.bonus_minutes ELSE 0 END+EXCLUDED.bonus_minutes,
                     bonus_date=CURRENT_DATE,updated_at=NOW()''',(cid,granted))
        execute("DELETE FROM activity_logs WHERE child_id=%s AND activity_type IN ('SCREEN_TIME_LIMIT_REACHED','SCREEN_TIME_WARNING') AND created_at::date=CURRENT_DATE",(cid,))
        log(cid,'SCREEN_TIME_EXTENSION_APPROVED',{'parent_id':pid,'request_id':req_id,'granted_minutes':granted})
        notify(cid,'SCREEN_TIME_EXTENSION_APPROVED',f'Your parent added {granted} minutes of screen time for today!','/child/dashboard/',pid)
    else:
        moved=execute_count("UPDATE screen_time_extension_requests SET status='REJECTED',decided_at=NOW(),decided_by=%s WHERE request_id=%s AND status='PENDING'",(pid,req_id))
        if moved:
            log(cid,'SCREEN_TIME_EXTENSION_REJECTED',{'parent_id':pid,'request_id':req_id})
            notify(cid,'SCREEN_TIME_EXTENSION_REJECTED','Your parent reviewed your extra-time request and said not right now.','/child/dashboard/',pid)
    return redirect(f'/parent/time-limit/?child_id={cid}')
@parent_bp.route('/parent/safety/',methods=['GET'])
@parent_required
def safety():
    # Only children under an approved Parent Mode mapping, matching the
    # canonical owns() check, so a pending/declined link never leaks review events.
    ev=fetch_all("SELECT e.*,u.full_name FROM moderation_events e JOIN users u ON u.user_id=e.child_id WHERE e.decision='REVIEW' AND e.status='OPEN' AND e.child_id IN (SELECT m.child_id FROM parent_child_map m WHERE m.approved=TRUE AND m.approval_status='APPROVED' AND (m.parent_id=%s OR m.verified_parent_id=%s)) ORDER BY e.created_at DESC",(session['user_id'],session['user_id']))
    focused = request.args.get('event', type=int)
    if 'event' in request.args and (focused is None or not any(e['event_id'] == focused for e in ev)):
        return ('Not available', 404)
    ev.sort(key=lambda e: e['event_id'] != focused)
    for e in ev:
        preview={}
        if e['content_type'] in {'IMAGE','VIDEO','AUDIO','TEXT'} and e['content_id']:
            preview=fetch_one('SELECT media_type,media_path,source_media_path,caption,story_music_path FROM posts WHERE post_id=%s',(e['content_id'],)) or {}
        elif e['content_type']=='COMMENT' and e['content_id']:
            preview=fetch_one('SELECT comment_text FROM comments WHERE comment_id=%s',(e['content_id'],)) or {}
        elif e['content_type']=='MESSAGE' and e['content_id']:
            preview=fetch_one('SELECT message_type,message_text,media_path,shared_post_id FROM child_messages WHERE child_message_id=%s',(e['content_id'],)) or {}
        if preview.get('source_media_path') or preview.get('media_path'):
            preview['preview_url']=f"/parent/review/{e['event_id']}/preview/"
        preview.pop('source_media_path', None)
        preview.pop('media_path', None)
        e['preview']=preview
    return render_template('safety_review.html',events=ev)

@parent_bp.route('/parent/review/<int:event_id>/preview/',methods=['GET'])
@parent_required
def review_preview(event_id):
    from services.object_storage import is_reference, signed_download_url
    e=fetch_one("SELECT * FROM moderation_events WHERE event_id=%s AND decision='REVIEW' AND status='OPEN'",(event_id,))
    if not e or not owns(session['user_id'],e['child_id']):return ('Not available',404)
    if e['content_type'] in {'IMAGE','VIDEO','AUDIO','TEXT'}:
        media=fetch_one("SELECT source_media_path,media_path FROM posts WHERE post_id=%s AND child_id=%s AND moderation_status='REVIEW'",(e['content_id'],e['child_id'])) or {}
    elif e['content_type']=='MESSAGE':
        media=fetch_one("SELECT media_path FROM child_messages WHERE child_message_id=%s AND sender_child_id=%s AND moderation_status='REVIEW'",(e['content_id'],e['child_id'])) or {}
    else:return ('Not available',404)
    ref=media.get('source_media_path') or media.get('media_path')
    if not ref or not is_reference(ref):return ('Not available',404)
    response=redirect(signed_download_url(ref,expires_seconds=60))
    response.headers['Cache-Control']='private, no-store'
    response.headers['Referrer-Policy']='no-referrer'
    return response
@parent_bp.route('/parent/review/<int:event_id>/',methods=['POST'])
@parent_required
def review(event_id):
    requested=request.form.get('action','').upper()
    if requested not in {'APPROVE','BLOCK'}:return jsonify(error='invalid action'),400
    conn=get_db_connection()
    try:
        cur=conn.cursor();cur.execute("SELECT * FROM moderation_events WHERE event_id=%s AND decision='REVIEW' AND status='OPEN' FOR UPDATE",(event_id,));e=cur.fetchone()
        if not e or not owns(session['user_id'],e['child_id']):conn.rollback();return jsonify(error='not found'),404
        effective=requested
        terminally_blocked=False
        if requested=='APPROVE' and e['content_id']:
            # Terminal-block guard (mirrors the mobile review path): a BLOCKED
            # decision is final — never resurrect already-blocked content via
            # a duplicate review event.
            ctype=e['content_type']
            if ctype in {'IMAGE','VIDEO','AUDIO','TEXT'}:cur.execute('SELECT moderation_status FROM posts WHERE post_id=%s',(e['content_id'],))
            elif ctype=='COMMENT':cur.execute('SELECT moderation_status FROM comments WHERE comment_id=%s',(e['content_id'],))
            elif ctype=='MESSAGE':cur.execute('SELECT moderation_status FROM child_messages WHERE child_message_id=%s',(e['content_id'],))
            else:cur.execute('SELECT 1 WHERE FALSE')
            srow=cur.fetchone()
            if str((srow or {}).get('moderation_status') or '').upper()=='BLOCKED':terminally_blocked=True;effective='BLOCK'
        if e['content_type']=='MESSAGE' and e['content_id'] and requested=='APPROVE' and not terminally_blocked:
            cur.execute('SELECT sender_child_id,receiver_child_id FROM child_messages WHERE child_message_id=%s',(e['content_id'],));m=cur.fetchone()
            if not m:effective='BLOCK'
            else:
                a,b=m['sender_child_id'],m['receiver_child_id']
                cur.execute('SELECT 1 FROM blocked_users WHERE (blocker_id=%s AND blocked_id=%s) OR (blocker_id=%s AND blocked_id=%s)',(a,b,b,a));blocked=cur.fetchone()
                cur.execute('SELECT 1 FROM followers WHERE approved=TRUE AND ((child_id=%s AND following_child_id=%s) OR (child_id=%s AND following_child_id=%s))',(a,b,b,a));connected=cur.fetchone()
                if blocked or not connected:effective='BLOCK'
        status='ALLOWED' if effective=='APPROVE' else 'BLOCKED'
        sanitize_failed=False
        # Tracked for post-commit work that must mirror the mobile review path:
        # quarantine bytes are deleted after the DB commits (never orphaned R2
        # objects), and an effective APPROVE refreshes feed/reel visibility.
        quarantine_key=None
        approved_post=None
        if e['content_type'] in {'IMAGE','VIDEO','AUDIO','TEXT'} and e['content_id']:
            # Mirror the mobile review path: approving a post must sanitize and
            # promote its media out of quarantine (metadata stripped, published
            # namespace) — not merely flip the status on the quarantine bytes.
            post_id=int(e['content_id'])
            cur.execute('SELECT post_id,child_id,media_type,is_reel,is_story,source_media_path FROM posts WHERE post_id=%s FOR UPDATE',(post_id,))
            p_row=cur.fetchone()
            kind='reel' if p_row and p_row.get('is_reel') else ('story' if p_row and p_row.get('is_story') else 'post')
            if p_row and p_row.get('source_media_path'):
                quarantine_key=p_row['source_media_path']
            if p_row and effective=='APPROVE' and p_row.get('source_media_path'):
                from services.media_processor import sanitize_and_promote_media
                try:
                    pub_media,pub_poster=sanitize_and_promote_media(post_id,int(p_row['child_id']),p_row['source_media_path'],kind,p_row.get('media_type') or 'IMAGE')
                    cur.execute("UPDATE posts SET media_path=%s,poster_path=%s,moderation_status='ALLOWED',processing_status='ALLOWED',is_safe=TRUE,processing_completed_at=NOW(),processing_error=NULL WHERE post_id=%s",(pub_media,pub_poster,post_id))
                    approved_post=(post_id,int(p_row['child_id']),bool(p_row.get('is_reel')),kind)
                except Exception as exc:
                    # Fail closed: never publish unsanitized media.
                    sanitize_failed=True;effective='BLOCK';status='BLOCKED'
                    cur.execute("UPDATE posts SET moderation_status='BLOCKED',processing_status='FAILED',is_safe=FALSE,processing_completed_at=NOW(),processing_error=%s WHERE post_id=%s",(f'sanitization_failed: {exc}',post_id))
            elif p_row and effective=='APPROVE':
                cur.execute("UPDATE posts SET moderation_status='ALLOWED',processing_status='ALLOWED',is_safe=TRUE,processing_completed_at=NOW(),processing_error=NULL WHERE post_id=%s",(post_id,))
                approved_post=(post_id,int(p_row['child_id']),bool(p_row.get('is_reel')),kind)
            elif p_row:
                cur.execute("UPDATE posts SET moderation_status='BLOCKED',processing_status='BLOCKED',is_safe=FALSE,media_path=NULL,processing_completed_at=NOW(),processing_error=NULL WHERE post_id=%s",(post_id,))
        elif e['content_type']=='COMMENT' and e['content_id']:cur.execute('UPDATE comments SET moderation_status=%s WHERE comment_id=%s',(status,e['content_id']))
        elif e['content_type']=='MESSAGE' and e['content_id']:cur.execute('UPDATE child_messages SET moderation_status=%s WHERE child_message_id=%s',(status,e['content_id']))
        review_note=None
        if terminally_blocked:review_note='Content already blocked; approval safely converted to block.'
        elif effective!=requested:review_note='Sanitization failed; approval safely converted to block.' if sanitize_failed else 'Connection changed; approval safely converted to block.'
        cur.execute('INSERT INTO moderation_reviews(event_id,reviewer_id,action,notes) VALUES(%s,%s,%s,%s)',(event_id,session['user_id'],effective,review_note))
        cur.execute("UPDATE moderation_events SET status='RESOLVED' WHERE event_id=%s",(event_id,));conn.commit()
        # Post-commit storage/visibility work mirrors the mobile review path.
        # Quarantine bytes must be deleted on BOTH approve and block — the
        # review decision is terminal, so the quarantine object would otherwise
        # strand an orphaned R2 object on every web review action.
        if quarantine_key:
            try:
                from services.media_processor import block_and_cleanup_quarantine
                block_and_cleanup_quarantine(int(e['content_id']),quarantine_key)
            except Exception:
                pass
        if approved_post:
            try:
                from services.publication_lifecycle import refresh_publication_visibility
                from services.media_processor import _notify_approved_followers
                refresh_publication_visibility(approved_post[0],approved_post[1],is_reel=approved_post[2])
                _notify_approved_followers(approved_post[0],approved_post[1],approved_post[3])
            except Exception:
                pass
        if e['content_type']=='MESSAGE' and e['content_id'] and effective=='APPROVE':
            msg=fetch_one('SELECT sender_child_id,receiver_child_id FROM child_messages WHERE child_message_id=%s',(e['content_id'],))
            if msg:notify(msg['receiver_child_id'],'MESSAGE','A parent-reviewed message is now available',f'/chat/{msg["sender_child_id"]}/',msg['sender_child_id'])
        return redirect('/parent/safety/')
    except Exception:conn.rollback();raise
    finally:conn.close()

@parent_bp.route('/parent/controls/',methods=['GET','POST'])
@limiter.limit('30 per minute')
@parent_required
def parent_controls():
    kids=children(session['user_id']);cid=int(request.values.get('child_id') or (kids[0]['user_id'] if kids else 0))
    if not owns(session['user_id'],cid):return ('Forbidden',403)
    if request.method=='POST':
        before=controls_for_child(cid)
        try:after=save_controls(session['user_id'],cid,request.form)
        except ValueError:
            child=fetch_one('SELECT full_name FROM users WHERE user_id=%s',(cid,)) or {'full_name':'Child'}
            return render_template('parent_controls.html',child_id=cid,child=child,controls=before,categories=SAFE_CATEGORIES,error='Quiet hours must use a valid time.'),400
        log(cid,'PARENT_CONTROLS_UPDATED',{'before':before,'after':after})
        notify(cid,'PARENT_CONTROLS','Parent Mode updated your LittleNet permissions','/child/dashboard/',session['user_id'])
        return redirect(f'/parent/controls/?child_id={cid}')
    child=fetch_one('SELECT full_name FROM users WHERE user_id=%s',(cid,)) or {'full_name':'Child'}
    return render_template('parent_controls.html',child_id=cid,child=child,controls=controls_for_child(cid),categories=SAFE_CATEGORIES)

@parent_bp.route('/parent/safety-level/',methods=['POST'])
@parent_required
def safety_level():
    cid=int(request.form.get('child_id',0));level=request.form.get('safety_level','STRICT').upper()
    if not owns(session['user_id'],cid) or level not in {'STANDARD','STRICT','VERY_STRICT'}:return jsonify(error='invalid'),400
    execute('INSERT INTO parent_safety_settings(child_id,parent_id,safety_level) VALUES(%s,%s,%s) ON CONFLICT(child_id) DO UPDATE SET safety_level=EXCLUDED.safety_level,updated_at=NOW()',(cid,session['user_id'],level));return redirect('/parent/dashboard/')
@parent_bp.route('/parent/notifications/')
@parent_required
def notifications():return render_template('parent_notifications.html',items=fetch_all('SELECT * FROM parent_notifications WHERE parent_id=%s ORDER BY created_at DESC',(session['user_id'],)),role='PARENT')

@parent_bp.route('/parent/notifications/read/',methods=['POST'])
@parent_required
def notifications_read():
    execute('UPDATE parent_notifications SET is_read=TRUE WHERE parent_id=%s',(session['user_id'],));return jsonify(ok=True)

@parent_bp.route('/api/parent/notifications/unread/')
@parent_required
def notifications_unread():
    row=fetch_one('''SELECT COUNT(*) n, MAX(notification_id) latest_id
      FROM parent_notifications WHERE parent_id=%s AND is_read=FALSE''',(session['user_id'],)) or {'n':0,'latest_id':None}
    latest=None
    if row.get('latest_id'):
        latest=fetch_one('''SELECT notification_id,notification_type,notification_message,target_url,created_at
          FROM parent_notifications WHERE parent_id=%s AND notification_id=%s''',(session['user_id'],row['latest_id']))
    return jsonify(count=int(row.get('n') or 0),latest=latest)

@parent_bp.route('/parent/content-approval/',methods=['GET','POST'])
@parent_required
def content_approval():
    kids=children(session['user_id']);cid=int(request.values.get('child_id') or (kids[0]['user_id'] if kids else 0))
    if not owns(session['user_id'],cid):return ('Forbidden',403)
    if request.method=='POST':
        for table,col in [('child_skills','skill_id'),('child_interests','interest_id'),('child_ambitions','ambition_id')]:
            execute(f'UPDATE {table} SET approved=FALSE WHERE child_id=%s',(cid,))
            selected={int(x) for x in request.form.getlist(table) if x.isdigit()}
            for item in selected:execute(f'UPDATE {table} SET approved=TRUE WHERE child_id=%s AND {col}=%s',(cid,item))
        return redirect(f'/parent/content-approval/?child_id={cid}')
    return render_template('content_approval.html',child_id=cid,skills=fetch_all('SELECT * FROM child_skills WHERE child_id=%s',(cid,)),interests=fetch_all('SELECT * FROM child_interests WHERE child_id=%s',(cid,)),ambitions=fetch_all('SELECT * FROM child_ambitions WHERE child_id=%s',(cid,)))

@parent_bp.route('/parent/child-posts/')
@parent_required
def child_posts():
    kids=children(session['user_id']);cid=int(request.args.get('child_id') or (kids[0]['user_id'] if kids else 0))
    if not owns(session['user_id'],cid):return ('Forbidden',403)
    return render_template('child_posts.html',posts=fetch_all('SELECT * FROM posts WHERE child_id=%s ORDER BY created_at DESC',(cid,)),child_id=cid)

@parent_bp.route('/parent/deleted-posts/')
@parent_required
def deleted_posts():
    return render_template('deleted_posts.html',posts=fetch_all("SELECT d.*,u.full_name FROM deleted_posts d JOIN users u ON u.user_id=d.child_id WHERE d.child_id IN (SELECT m.child_id FROM parent_child_map m WHERE m.approved=TRUE AND m.approval_status='APPROVED' AND (m.parent_id=%s OR m.verified_parent_id=%s)) ORDER BY d.deleted_at DESC",(session['user_id'],session['user_id'])))

@parent_bp.route('/parent/usage-report/')
@parent_required
def usage_report():
    kids=children(session['user_id']);cid=int(request.args.get('child_id') or (kids[0]['user_id'] if kids else 0))
    if not owns(session['user_id'],cid):return ('Forbidden',403)
    return render_template('usage_report.html',rows=fetch_all('SELECT usage_date,SUM(duration_minutes) total_minutes FROM child_usage_logs WHERE child_id=%s GROUP BY usage_date ORDER BY usage_date DESC LIMIT 7',(cid,)),child_id=cid)

@parent_bp.route('/parent/behavior/')
@parent_required
def behavior():
    kids=children(session['user_id']);cid=int(request.args.get('child_id') or (kids[0]['user_id'] if kids else 0))
    if not owns(session['user_id'],cid):return ('Forbidden',403)
    summary=behavior_summary(cid)
    child=fetch_one('SELECT full_name FROM users WHERE user_id=%s',(cid,)) or {'full_name':'Child'}
    return render_template('behavior.html',summary=summary,child=child,child_id=cid)

@parent_bp.route('/parent/activity/')
@parent_required
def activity():
    kids=children(session['user_id']);cid=int(request.args.get('child_id') or (kids[0]['user_id'] if kids else 0))
    if not owns(session['user_id'],cid):return ('Forbidden',403)
    # Same liked snapshot the mobile ParentActivityScreen shows (saves excluded:
    # saved content is private to the child); lazy import keeps the web
    # blueprint free of mobile-api import-order coupling.
    from mobile.api import _liked_saved_snapshot, _SAVE_ACTIVITY_SQL
    return render_template('activity.html',rows=fetch_all('SELECT * FROM activity_logs WHERE child_id=%s AND '+_SAVE_ACTIVITY_SQL+' ORDER BY created_at DESC LIMIT 100',(cid,)),liked_saved=_liked_saved_snapshot(cid, include_saved=False),child_id=cid)

@parent_bp.route('/parent/child/<int:child_id>/')
@parent_required
def child_profile_view(child_id):
    if not owns(session['user_id'],child_id):return ('Forbidden',403)
    return render_template('child_profile_view.html',profile=fetch_one('SELECT * FROM child_profiles WHERE child_id=%s',(child_id,)))
@parent_bp.route('/parent/approve-content/')
@parent_required
def approve_content_alias():return redirect('/parent/content-approval/')
@parent_bp.route('/parent/save-approval/',methods=['POST'])
@parent_required
def save_approval_alias():return content_approval()
@parent_bp.route('/parent/child-connections/')
@parent_required
def child_connections():
    kids=children(session['user_id']);cid=int(request.args.get('child_id') or (kids[0]['user_id'] if kids else 0))
    if not owns(session['user_id'],cid):return ('Forbidden',403)
    return render_template('child_connections.html',followers=fetch_all('SELECT u.full_name FROM followers f JOIN users u ON u.user_id=f.child_id WHERE f.following_child_id=%s AND f.approved=TRUE',(cid,)),following=fetch_all('SELECT u.full_name FROM followers f JOIN users u ON u.user_id=f.following_child_id WHERE f.child_id=%s AND f.approved=TRUE',(cid,)),pending=pending_follows(session['user_id']))
@parent_bp.route('/parent/approve-follow/',methods=['POST'])
@parent_required
def approve_follow_compat():
    d=request.get_json(silent=True) or {}
    try:a=int(d.get('child_id'));b=int(d.get('target_id'))
    except:return jsonify(error='invalid ids'),400
    if not owns(session['user_id'],a):return jsonify(error='forbidden'),403
    changed=execute_count("UPDATE followers SET approved=TRUE WHERE child_id=%s AND following_child_id=%s AND approved=FALSE AND approval_stage IN ('REQUESTED','RECEIVER_PARENT_PENDING')",(a,b))
    if not changed:return jsonify(error='request_not_found'),404
    return jsonify(ok=True)
@parent_bp.route('/parent/reject-follow/',methods=['POST'])
@parent_required
def reject_follow_compat():
    d=request.get_json(silent=True) or {}
    try:a=int(d.get('child_id'));b=int(d.get('target_id'))
    except:return jsonify(error='invalid ids'),400
    if not owns(session['user_id'],a):return jsonify(error='forbidden'),403
    execute("DELETE FROM followers WHERE approved=FALSE AND ((child_id=%s AND following_child_id=%s) OR (child_id=%s AND following_child_id=%s AND approval_stage IN ('SENDER_PARENT_APPROVED','RECEIVER_PARENT_PENDING')))",(a,b,b,a));return jsonify(ok=True)

@parent_bp.route('/parent/settings/', methods=['GET', 'POST'])
@parent_required
def parent_settings():
    kids = children(session['user_id'])
    if not kids:
        return render_template('parent_settings.html', children=[], child=None, error='No children linked to this parent account.')
    
    try:
        cid = int(request.values.get('child_id') or kids[0]['user_id'])
    except (TypeError, ValueError):
        cid = kids[0]['user_id']
        
    if not owns(session['user_id'], cid):
        return ('Forbidden', 403)
        
    child = fetch_one("SELECT user_id, full_name, username, account_status FROM users WHERE user_id=%s", (cid,)) or {'user_id': cid, 'full_name': 'Child', 'account_status': 'ACTIVE'}
    
    success_msg = None
    error_msg = None
    
    if request.method == 'POST':
        # 1. Emergency Pause / Account Status
        is_paused = 'pause_account' in request.form
        new_status = 'SUSPENDED' if is_paused else 'ACTIVE'
        execute("UPDATE users SET account_status=%s WHERE user_id=%s", (new_status, cid))
        child['account_status'] = new_status
        
        # 2. Daily screen time limit
        try:
            limit_mins = int(request.form.get('daily_limit', 60))
            strict = 'strict_mode' in request.form
            if 1 <= limit_mins <= 1440:
                execute('''INSERT INTO child_time_limits(child_id, daily_limit_minutes, strict_mode)
                           VALUES(%s,%s,%s)
                           ON CONFLICT(child_id) DO UPDATE SET daily_limit_minutes=EXCLUDED.daily_limit_minutes, strict_mode=EXCLUDED.strict_mode, updated_at=NOW()''',
                        (cid, limit_mins, strict))
        except Exception:
            pass
            
        # 3. AI Safety Level
        lvl = request.form.get('safety_level', 'STRICT').upper()
        if lvl in {'STANDARD', 'STRICT', 'VERY_STRICT'}:
            execute('''INSERT INTO parent_safety_settings(child_id, parent_id, safety_level)
                       VALUES(%s,%s,%s)
                       ON CONFLICT(child_id) DO UPDATE SET safety_level=EXCLUDED.safety_level, updated_at=NOW()''',
                    (cid, session['user_id'], lvl))
                    
        # 4. Feature Permissions & Quiet Hours
        try:
            save_controls(session['user_id'], cid, request.form)
            success_msg = "Parent settings saved and enforced successfully!"
            log(cid, 'PARENT_SETTINGS_UPDATED', {'parent_id': session['user_id'], 'paused': is_paused, 'limit': request.form.get('daily_limit'), 'safety': lvl})
            notify(cid, 'PARENT_CONTROLS', 'Parent Mode updated your safety controls & limits', '/child/dashboard/', session['user_id'])
        except Exception as e:
            error_msg = str(e)
            
    controls = controls_for_child(cid)
    limit = fetch_one('SELECT * FROM child_time_limits WHERE child_id=%s', (cid,)) or {'daily_limit_minutes': 60, 'strict_mode': True}
    safety = fetch_one('SELECT safety_level FROM parent_safety_settings WHERE child_id=%s', (cid,)) or {'safety_level': 'STRICT'}
    
    return render_template(
        'parent_settings.html',
        children=kids,
        child_id=cid,
        child=child,
        controls=controls,
        limit=limit,
        safety=safety,
        success=success_msg,
        error=error_msg,
        categories=SAFE_CATEGORIES
    )

