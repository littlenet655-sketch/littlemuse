import os,uuid
from flask import Blueprint,render_template,request,session,jsonify
from decorators import child_required
from database.connection import fetch_all,fetch_one,execute
from services.social import can_interact,parent_notify,post_visible_to,notify
from childMessage.service import conversation,messages
from extensions import limiter
from safety.moderation_service import evaluate,record
from safety.policy import Decision
from services.audit import log

child_message_bp=Blueprint('child_message',__name__,template_folder='templates')
@child_message_bp.route('/messages/')
@child_required
def list_messages():
    uid = session['user_id']
    rows = fetch_all('''
        SELECT c.*,
               CASE WHEN c.child1_id = %s THEN u2.full_name ELSE u1.full_name END AS peer_name,
               CASE WHEN c.child1_id = %s THEN u2.username ELSE u1.username END AS peer_username,
               CASE WHEN c.child1_id = %s THEN c.child2_id ELSE c.child1_id END AS peer_id,
               CASE WHEN c.child1_id = %s THEN cp2.profile_picture ELSE cp1.profile_picture END AS peer_avatar
        FROM child_conversations c
        JOIN users u1 ON u1.user_id = c.child1_id
        JOIN users u2 ON u2.user_id = c.child2_id
        LEFT JOIN child_profiles cp1 ON cp1.child_id = u1.user_id
        LEFT JOIN child_profiles cp2 ON cp2.child_id = u2.user_id
        WHERE (c.child1_id = %s OR c.child2_id = %s)
    ''', (uid, uid, uid, uid, uid, uid))

    valid_rows = [r for r in rows if can_interact(uid, r['peer_id'])]

    import datetime
    now = datetime.datetime.now(datetime.timezone.utc) if hasattr(datetime, 'timezone') else datetime.datetime.utcnow()

    conv_list = []
    for r in valid_rows:
        c = dict(r)
        last_msg = fetch_one('''
            SELECT message_text, message_type, sent_at, sender_child_id, is_seen
            FROM child_messages
            WHERE conversation_id = %s AND moderation_status = 'ALLOWED'
            ORDER BY sent_at DESC LIMIT 1
        ''', (c['conversation_id'],))

        if last_msg:
            mtype = last_msg.get('message_type')
            is_mine = (last_msg.get('sender_child_id') == uid)
            if mtype == 'SHARED_POST':snippet = "Sent a reel/post" if is_mine else f"Sent a reel by {c['peer_name'].split(' ')[0]}"
            elif mtype == 'IMAGE':snippet = "Sent a photo"
            else:snippet = last_msg.get('message_text') or "Sent a message"
            c['last_snippet'] = snippet
            c['is_unread'] = (not is_mine and not last_msg.get('is_seen'))
            sent = last_msg.get('sent_at')
            if sent:
                if hasattr(sent, 'tzinfo') and sent.tzinfo is not None:delta = now - sent
                else:delta = datetime.datetime.utcnow() - sent
                secs = max(0, int(delta.total_seconds()))
                if secs < 60:c['time_ago'] = 'just now'
                elif secs < 3600:c['time_ago'] = f"{secs // 60}m"
                elif secs < 86400:c['time_ago'] = f"{secs // 3600}h"
                else:c['time_ago'] = f"{delta.days}d"
            else:c['time_ago'] = ''
        else:
            c['last_snippet'] = "Active on LittleNet";c['is_unread'] = False;c['time_ago'] = ''
        conv_list.append(c)

    conv_list.sort(key=lambda x: (not x['is_unread'], x['time_ago'] == ''))
    peers = fetch_all('''
        SELECT DISTINCT u.user_id, u.username, u.full_name, cp.profile_picture, cp.bio, u.created_at
        FROM followers f
        JOIN users u ON u.user_id = CASE WHEN f.child_id=%s THEN f.following_child_id ELSE f.child_id END
        JOIN child_profiles cp ON cp.child_id = u.user_id
        WHERE f.approved=TRUE AND f.approval_stage='ACTIVE'
          AND (f.child_id=%s OR f.following_child_id=%s)
          AND u.role='CHILD' AND u.account_status='ACTIVE' AND u.user_id<>%s
          AND NOT EXISTS(SELECT 1 FROM blocked_users b WHERE (b.blocker_id=%s AND b.blocked_id=u.user_id) OR (b.blocker_id=u.user_id AND b.blocked_id=%s))
          AND NOT EXISTS(SELECT 1 FROM muted_users mu WHERE mu.muter_id=%s AND mu.muted_id=u.user_id)
        ORDER BY u.created_at DESC LIMIT 8
    ''', (uid, uid, uid, uid, uid, uid, uid))

    sample_notes = ["Ready for...", "Vibe 🎵", "Coding 💻", "Exploring 🌟", "Reading 📚", "Game on! 🎮"]
    notes_tray = []
    for i, p in enumerate(peers):
        p_dict = dict(p);bio = (p_dict.get('bio') or '').strip()
        p_dict['note_text'] = (bio[:14] + '...') if (bio and len(bio) > 14) else (bio if bio else sample_notes[i % len(sample_notes)])
        notes_tray.append(p_dict)
    current_profile = fetch_one('SELECT profile_picture FROM child_profiles WHERE child_id = %s', (uid,))
    return render_template('chat_list.html',conversations=conv_list,notes_tray=notes_tray,my_avatar=(current_profile or {}).get('profile_picture'))

@child_message_bp.route('/chat/<int:child_id>/')
@child_required
def chat(child_id):
    cid=conversation(session['user_id'],child_id)
    if not cid:return ('Parent-approved connection required',403)
    execute('UPDATE child_messages SET is_seen=TRUE,seen_at=NOW(),delivered_at=COALESCE(delivered_at,NOW()) WHERE conversation_id=%s AND receiver_child_id=%s AND moderation_status=\'ALLOWED\'',(cid,session['user_id']))
    peer=fetch_one('SELECT full_name FROM users WHERE user_id=%s',(child_id,));peer_name=peer['full_name'] if peer else 'Classmate'
    return render_template('chat.html',messages=messages(cid,session['user_id']),peer_id=child_id,conversation_id=cid,peer_name=peer_name)

@child_message_bp.route('/send-message/<int:child_id>/',methods=['POST'])
@limiter.limit('60 per minute')
@child_required
def send_text(child_id):
    if not can_interact(session['user_id'],child_id):return jsonify(error='approved connection required'),403
    text=(request.form.get('message_text') or '').strip()
    if not text:return jsonify(error='empty message'),400
    from safety.pii_service import scan_pii
    pii_res = scan_pii(text)
    if pii_res['detected'] and pii_res['policy_action'] == 'BLOCK':
        parent_notify(session['user_id'],'MESSAGE_BLOCKED','Blocked attempt to share phone/contact info','/parent/safety/')
        log(session['user_id'],'MESSAGE_PII_BLOCKED',{'to':child_id,'categories':pii_res['categories']})
        return jsonify(blocked=True,error="This message can't be sent for safety.",reason="CONTACT_SHARING_BLOCKED"),400
    sig,d=evaluate(session['user_id'],'TEXT',text)
    if d.action=='BLOCK':
        parent_notify(session['user_id'],'MESSAGE_BLOCKED',d.reason,'/parent/safety/')
        return jsonify(blocked=True,error="This message can't be sent for safety.",reason=d.reason),400
    cid=conversation(session['user_id'],child_id)
    if not cid:return jsonify(error='approved connection required'),403
    final_decision=d
    high_risk_triggers = ('secret',"don't tell","dont tell",'meet','photo','pic','picture','selfie','wear','wearing','private','snap','insta','telegram','phone','number','address','alone')
    recent = fetch_all("SELECT sender_child_id, message_text FROM child_messages WHERE conversation_id=%s ORDER BY sent_at DESC LIMIT 20", (cid,))
    from safety.chat_context import contextual_chat_risk
    context_risk = contextual_chat_risk(recent, text)
    needs_contextual_eval = any(t in text.lower() for t in high_risk_triggers) or d.action == 'REVIEW' or context_risk['suspicious']
    from services.ai import get_ai_client
    ai_client = None
    if needs_contextual_eval:
        if context_risk['suspicious'] and d.action == 'ALLOW':
            final_decision=Decision('REVIEW',50.0,'multi-turn grooming pattern requires review')
            sig['contextual_cue_families']=context_risk['cue_families']
            sig['contextual_reason_code']=context_risk['reason_code']
        # Fail closed: an AI outage must never 500 the send and must never
        # downgrade to ALLOW — hold the message for parent review instead.
        ai_res=None
        try:
            ai_client=get_ai_client()
            ai_res=ai_client.evaluate_chat_safety(recent, session['user_id'], child_id, text)
        except Exception as exc:
            log(session['user_id'],'MESSAGE_AI_EVAL_FAILED',{'to':child_id,'error':type(exc).__name__})
            final_decision=Decision('REVIEW',max(float(d.risk),70.0),'AI safety unavailable - parent review')
        if ai_res is not None:
            if ai_res.action == 'BLOCK':
                parent_notify(session['user_id'],'MESSAGE_BLOCKED',f"AI detected {ai_res.primary_category}",'/parent/safety/')
                return jsonify(blocked=True,error="This message can't be sent for safety.",reason=ai_res.reason_code),400
            if ai_res.action == 'REVIEW' and d.action == 'ALLOW':
                contextual_risk=max(float(d.risk),float(ai_res.risk_score)*100.0)
                final_decision=Decision('REVIEW',contextual_risk,f'contextual safety review: {ai_res.reason_code}')
    final_action=final_decision.action
    row=execute("INSERT INTO child_messages(conversation_id,sender_child_id,receiver_child_id,message_type,message_text,moderation_status) VALUES(%s,%s,%s,'TEXT',%s,%s) RETURNING child_message_id",(cid,session['user_id'],child_id,text,'ALLOWED' if final_action=='ALLOW' else 'REVIEW'),returning=True)
    record(session['user_id'],'MESSAGE',row['child_message_id'],sig,final_decision)
    if final_action=='REVIEW':parent_notify(session['user_id'],'REVIEW_REQUIRED','A message needs safety review','/parent/safety/')
    else:notify(child_id,'MESSAGE',f'{session.get("full_name","Someone")} sent you a message',f'/chat/{session["user_id"]}/',session['user_id'])
    log(session['user_id'],'MESSAGE_SENT',{'to':child_id,'status':final_action})
    return jsonify(ok=True,status=final_action)

@child_message_bp.route('/share-post/<int:child_id>/<int:post_id>/',methods=['POST'])
@limiter.limit('30 per minute')
@child_required
def share_post(child_id,post_id):
    from services.social import is_post_shareable_to
    ok, reason = is_post_shareable_to(post_id, session['user_id'], child_id)
    if not ok:return jsonify(error=reason),403
    cid=conversation(session['user_id'],child_id)
    if not cid:return jsonify(error='approved connection required'),403
    execute("INSERT INTO child_messages(conversation_id,sender_child_id,receiver_child_id,message_type,shared_post_id,moderation_status) VALUES(%s,%s,%s,'SHARED_POST',%s,'ALLOWED')",(cid,session['user_id'],child_id,post_id))
    notify(child_id,'MESSAGE',f'{session.get("full_name","Someone")} shared a post with you',f'/chat/{session["user_id"]}/',session['user_id'])
    return jsonify(ok=True)

@child_message_bp.route('/send-media/<int:child_id>/',methods=['POST'])
@limiter.limit('30 per minute')
@child_required
def send_media(child_id):
    if not can_interact(session['user_id'],child_id):return jsonify(error='approved connection required'),403
    media=request.files.get('media')
    if not media or not media.filename:return jsonify(error='no file'),400
    if request.content_length and request.content_length>40*1024*1024:return jsonify(error='file too large'),413
    name=media.filename.lower();ext=name.rsplit('.',1)[-1] if '.' in name else '';mime=(media.mimetype or '').lower()
    if mime.startswith('audio/') or ext in {'mp3','wav','m4a','ogg','aac','flac','opus'}:
        return jsonify(error='Audio and voice messages are disabled in LittleNet'),400
    if ext in {'jpg','jpeg','png','webp'}:kind='IMAGE';folder='images'
    elif ext in {'mp4','mov','avi','mkv','webm'}:kind='VIDEO';folder='videos'
    elif ext in {'txt','pdf','docx'}:kind='FILE';folder='files'
    else:return jsonify(error='unsupported file type'),400
    base=os.path.join('uploads/messages',folder);os.makedirs(base,exist_ok=True);path=os.path.join(base,f'{uuid.uuid4().hex}.{ext}');media.save(path)
    reference=None
    try:
        if kind=='FILE':
            from safety.document_service import check_document
            from safety.policy import decide
            from safety.moderation_service import safety_level
            sig=check_document(path,ext);d=decide(sig,safety_level(session['user_id']))
        else:sig,d=evaluate(session['user_id'],kind,path)
        if d.action=='BLOCK':
            try:os.remove(path)
            except OSError:pass
            parent_notify(session['user_id'],'MESSAGE_MEDIA_BLOCKED',d.reason,'/parent/safety/');return jsonify(blocked=True,reason=d.reason),400
        from services.media_persistence import persist_before_db,rollback_reference
        reference=persist_before_db(path,'messages',session['user_id'])
        cid=conversation(session['user_id'],child_id)
        if not cid:
            rollback_reference(reference)
            return jsonify(error='approved connection required'),403
        try:
            row=execute('INSERT INTO child_messages(conversation_id,sender_child_id,receiver_child_id,message_type,media_path,moderation_status) VALUES(%s,%s,%s,%s,%s,%s) RETURNING child_message_id',(cid,session['user_id'],child_id,kind,reference,'ALLOWED' if d.action=='ALLOW' else 'REVIEW'),returning=True)
        except Exception:
            rollback_reference(reference);raise
        record(session['user_id'],'MESSAGE',row['child_message_id'],sig,d)
        if d.action=='REVIEW':parent_notify(session['user_id'],'REVIEW_REQUIRED','A media message needs review','/parent/safety/')
        else:notify(child_id,'MESSAGE',f'{session.get("full_name","Someone")} sent you {kind.lower()} media',f'/chat/{session["user_id"]}/',session['user_id'])
        return jsonify(ok=True,status=d.action)
    except Exception:
        try:os.remove(path)
        except OSError:pass
        return jsonify(error='media safety or secure persistence failed'),503

@child_message_bp.route('/api/chat/<int:child_id>/messages/')
@child_required
def api_chat_messages(child_id):
    cid=conversation(session['user_id'],child_id)
    if not cid:return jsonify(error='approved connection required'),403
    rows=messages(cid,session['user_id'])
    return jsonify([{k:(str(v) if k=='sent_at' else v) for k,v in r.items()} for r in rows])
