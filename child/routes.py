import os,uuid
from flask import Blueprint,render_template,request,redirect,session,jsonify
from extensions import limiter
from decorators import child_required
from child.service import *
from services.social import visible_posts,active_stories,story_visible_to,parent_notify,visible_profile_posts,can_interact,_age_group,post_visible_to
from services.usage import lock_state,heartbeat,minutes_today,start_session,close_session
from quiz.service import quiz_due
from database.connection import execute,fetch_one,fetch_all
from safety.moderation_service import evaluate,record
from services.audit import log
from services.controls import quiet_hours_state,effective_categories
from safety.pii_service import scan_pii
from services.recommendation_signals import record_signal

child_bp=Blueprint('child',__name__,template_folder='templates')
def _guard():
    if session.get('usage_session_key'): heartbeat(session['usage_session_key'])
    locked,remaining=lock_state(session['user_id'])
    if locked:return render_template('time_limit_reached.html'),403
    if quiz_due(session['user_id']) and request.path not in ['/quiz/start/','/quiz/submit/','/logout/']:return redirect('/quiz/start/')
    return None

def _public_profile_text(form):
    return ' '.join(str(form.get(k,'') or '') for k in ['full_name','school_name','location','current_class','bio'])

@child_bp.route('/child/dashboard/')
@child_required
def dashboard():
    g=_guard()
    if g:return g
    if not profile_exists(session['user_id']):
        try:
            create_child_profile(session['user_id'], {'full_name': session.get('full_name') or 'Student', 'bio': "Hey! I'm on LittleNet 🌟"})
        except Exception:
            pass
    suggs = get_random_children(session['user_id'])[:5]
    return render_template('child_dashboard.html',
                           profile=get_child_profile(session['user_id']),
                           stories=active_stories(session['user_id']),
                           posts=visible_posts(session['user_id'],False,12,0),
                           reels=visible_posts(session['user_id'],True,5,0),
                           suggested_users=suggs)

@child_bp.route('/stories/')
@child_required
def stories_viewer():
    g=_guard()
    if g:return g
    stories=active_stories(session['user_id'])
    try:start_id=int(request.args.get('start') or 0)
    except (TypeError,ValueError):start_id=0
    start_index=next((i for i,row in enumerate(stories) if row['post_id']==start_id),0)
    return render_template('stories_viewer.html',stories=stories,start_index=start_index)

@child_bp.route('/story/<int:post_id>/')
@child_required
def story_view(post_id):
    if not story_visible_to(session['user_id'],post_id):return ('Story unavailable',404)
    return redirect(f'/stories/?start={post_id}')

@child_bp.route('/api/story-view/<int:post_id>/',methods=['POST'])
@child_required
def record_story_view(post_id):
    story=story_visible_to(session['user_id'],post_id)
    if not story:return jsonify(error='Story unavailable'),404
    execute('INSERT INTO story_views(post_id,child_id) VALUES(%s,%s) ON CONFLICT(post_id,child_id) DO UPDATE SET viewed_at=NOW()',(post_id,session['user_id']))
    return jsonify(ok=True)

@child_bp.route('/child/create-profile/',methods=['GET','POST'])
@child_required
def create_profile():
    if request.method=='POST':
        from safety.pii_service import scan_pii
        if scan_pii(_public_profile_text(request.form))['detected']:
            return render_template('create_profile.html',error='Profile cannot contain phone numbers, addresses, or external contacts.'),400
        signals,d=evaluate(session['user_id'],'TEXT',_public_profile_text(request.form))
        if d.action!='ALLOW': return render_template('create_profile.html',error='Profile text could not be published under Kids Mode safety rules.'),400
        create_child_profile(session['user_id'],request.form);replace_profile_tags(session['user_id'],request.form.get('skills','').split(','),request.form.get('interests','').split(','),request.form.get('ambitions','').split(','));parent_notify(session['user_id'],'PROFILE_APPROVAL','Skills/interests/ambitions need approval','/parent/content-approval/');return redirect('/child/dashboard/')
    return render_template('create_profile.html')

@child_bp.route('/child/profile/')
@child_required
def profile():
    c=counts(session['user_id']);ps=visible_profile_posts(session['user_id'],session['user_id']);return render_template('profile.html',profile=get_child_profile(session['user_id']),counts=c,posts=ps)

@child_bp.route('/child/settings/')
@child_required
def child_settings():
    g = _guard()
    if g: return g
    try:prof = get_child_profile(session.get('user_id'))
    except Exception:prof = None
    try:used = minutes_today(session.get('user_id'))
    except Exception:used = 0
    try:
        lim = fetch_one('SELECT * FROM child_time_limits WHERE child_id=%s', (session.get('user_id'),))
        daily_limit = lim['daily_limit_minutes'] if lim else 60
    except Exception:daily_limit = 60
    return render_template('child_settings.html', profile=prof, used_minutes=used, daily_limit=daily_limit)

@child_bp.route('/child/view-profile/<int:user_id>/')
@child_required
def view_profile(user_id):
    if not can_discover_child(session['user_id'],user_id):return ('Not available',404)
    if fetch_one('SELECT 1 FROM blocked_users WHERE (blocker_id=%s AND blocked_id=%s) OR (blocker_id=%s AND blocked_id=%s)',(session['user_id'],user_id,user_id,session['user_id'])):return ('Not available',404)
    return render_template('view_profile.html',profile=get_child_profile(user_id),counts=counts(user_id),target_user_id=user_id,is_following=is_following(session['user_id'],user_id),is_pending=is_follow_pending(session['user_id'],user_id),posts=visible_profile_posts(session['user_id'],user_id),can_message=can_interact(session['user_id'],user_id))

@child_bp.route('/discover/')
@limiter.limit('60 per minute')
@child_required
def discover():
    viewer_id = session['user_id']
    q = (request.args.get('q') or '').strip()
    tag = (request.args.get('tag') or '').strip()
    search_term = tag if tag else q
    pii_res = scan_pii(search_term) if search_term else {'detected': False}
    if pii_res.get('detected'):
        return render_template('discover.html',children=[],recommended_posts=[],search_query="",active_tag="",pii_warning=True)
    person_term = q.lstrip('#').strip() if q and not q.startswith('#') and not tag else None
    kids = discoverable_children(viewer_id,person_term,30)
    for k in kids:
        k['is_following'] = is_following(viewer_id, k['user_id'])
        k['is_pending'] = is_follow_pending(viewer_id, k['user_id'])
    cats = effective_categories(viewer_id);age_grp = _age_group(viewer_id)
    allowed_child_ids = [viewer_id] + discoverable_child_ids(viewer_id)
    if search_term:
        clean_term = search_term.lstrip('#').strip();pattern = f"%{clean_term}%"
        posts = fetch_all('''
            SELECT p.*, u.full_name, u.username, cp.profile_picture
            FROM posts p JOIN users u ON p.child_id = u.user_id
            LEFT JOIN child_profiles cp ON cp.child_id = u.user_id
            WHERE p.moderation_status = 'ALLOWED' AND p.is_safe = TRUE
              AND p.child_id = ANY(%s) AND p.content_category = ANY(%s)
              AND (%s IS NULL OR p.audience_age_group='ALL' OR p.audience_age_group=%s)
              AND p.child_id NOT IN (
                SELECT blocked_id FROM blocked_users WHERE blocker_id=%s
                UNION SELECT blocker_id FROM blocked_users WHERE blocked_id=%s
                UNION SELECT muted_id FROM muted_users WHERE muter_id=%s)
              AND (p.caption ILIKE %s OR p.content_category ILIKE %s OR u.full_name ILIKE %s OR u.username ILIKE %s)
            ORDER BY p.created_at DESC LIMIT 50
        ''', (allowed_child_ids,cats,age_grp,age_grp,viewer_id,viewer_id,viewer_id,pattern,pattern,pattern,pattern))
    else:
        posts = fetch_all('''
            SELECT p.*, u.full_name, u.username, cp.profile_picture
            FROM posts p JOIN users u ON p.child_id = u.user_id
            LEFT JOIN child_profiles cp ON cp.child_id = u.user_id
            WHERE p.moderation_status = 'ALLOWED' AND p.is_safe = TRUE
              AND p.child_id = ANY(%s) AND p.content_category = ANY(%s)
              AND (%s IS NULL OR p.audience_age_group='ALL' OR p.audience_age_group=%s)
              AND p.child_id NOT IN (
                SELECT blocked_id FROM blocked_users WHERE blocker_id=%s
                UNION SELECT blocker_id FROM blocked_users WHERE blocked_id=%s
                UNION SELECT muted_id FROM muted_users WHERE muter_id=%s)
            ORDER BY p.created_at DESC LIMIT 30
        ''', (allowed_child_ids,cats,age_grp,age_grp,viewer_id,viewer_id,viewer_id))
    return render_template('discover.html',children=kids,recommended_posts=posts,search_query=search_term,active_tag=tag)

@child_bp.route('/api/search/suggestions/')
@child_required
def search_suggestions():
    q = (request.args.get('q') or '').strip().lower()
    if not q or scan_pii(q).get('detected'):return jsonify(suggestions=[])
    clean = q.lstrip('#');suggestions = []
    if any(k in clean for k in ('mr', 'bean', 'com', 'fun')):suggestions.append({'type':'hashtag','label':'#mrbean','sub':'Mr. Bean Comedy & Fun Safe Clips','url':'/discover/?q=%23mrbean'})
    if any(k in clean for k in ('sci', 'space', 'ast')):suggestions.append({'type':'hashtag','label':'#science','sub':'Science, Space & Astronomy','url':'/discover/?q=%23science'})
    if any(k in clean for k in ('rob', 'ard', 'stem', 'tech')):suggestions.append({'type':'hashtag','label':'#robotics','sub':'Robotics & Coding Projects','url':'/discover/?q=%23robotics'})
    if any(k in clean for k in ('art', 'draw', 'paint')):suggestions.append({'type':'hashtag','label':'#art','sub':'Drawing & Creativity','url':'/discover/?q=%23art'})
    if any(k in clean for k in ('cod', 'dev', 'py')):suggestions.append({'type':'hashtag','label':'#coding','sub':'Kid Coding & Python','url':'/discover/?q=%23coding'})
    classmates = discoverable_children(session['user_id'],clean,5)
    for c in classmates:suggestions.append({'type':'user','label':c['full_name'],'sub':f"@{c['username']} · {c.get('recommendation_reason','Allowed network')}",'url':f"/child/view-profile/{c['user_id']}/"})
    return jsonify(suggestions=suggestions)

@child_bp.route('/follow/<int:child_id>/',methods=['POST'])
@child_required
def follow(child_id):
    if child_id==session['user_id']:return jsonify(status='self'),400
    if not can_discover_child(session['user_id'],child_id):return jsonify(error='child unavailable'),404
    if is_following(session['user_id'],child_id) or is_follow_pending(session['user_id'],child_id):
        unfollow_child(session['user_id'],child_id);return jsonify(status='removed')
    follow_child(session['user_id'],child_id);record_signal(session['user_id'],'CREATOR',child_id,'FOLLOW');log(session['user_id'],'FOLLOW_REQUEST',{'target':child_id})
    parent_notify(session['user_id'],'FOLLOW_REQUEST','A new connection request needs approval','/parent/follow-requests/')
    try:
        sender=fetch_one('SELECT full_name FROM users WHERE user_id=%s',(session['user_id'],));s_name=(sender or {}).get('full_name') or 'A LittleNet friend'
        notify(child_id,'FOLLOW_REQUEST',f"{s_name} sent you a parent-mediated friend request.",'/notifications/',session['user_id'])
    except Exception:pass
    return jsonify(status='pending')

@child_bp.route('/block/<int:user_id>/',methods=['POST'])
@child_required
def block(user_id):
    if user_id!=session['user_id']:log(session['user_id'],'USER_BLOCKED',{'target':user_id});execute('INSERT INTO blocked_users(blocker_id,blocked_id) VALUES(%s,%s) ON CONFLICT DO NOTHING',(session['user_id'],user_id));record_signal(session['user_id'],'CREATOR',user_id,'BLOCK');execute('DELETE FROM followers WHERE (child_id=%s AND following_child_id=%s) OR (child_id=%s AND following_child_id=%s)',(session['user_id'],user_id,user_id,session['user_id']))
    return redirect('/discover/')

@child_bp.route('/mute/<int:user_id>/',methods=['POST'])
@child_required
def mute(user_id):
    if user_id!=session['user_id']:execute('INSERT INTO muted_users(muter_id,muted_id) VALUES(%s,%s) ON CONFLICT DO NOTHING',(session['user_id'],user_id));record_signal(session['user_id'],'CREATOR',user_id,'MUTE')
    return redirect(request.referrer or '/child/dashboard/')

@child_bp.route('/api/recommendation-action/',methods=['POST'])
@limiter.limit('60 per minute')
@child_required
def recommendation_action():
    """Record NOT_INTERESTED / HIDE feedback from the web client.

    Mirrors the mobile recommendation-actions endpoint so web kids get the same
    behavior: a hidden item is hard-excluded from future recommendations.
    The item must be currently visible to the child; signals are only recorded
    for content the child could actually see.
    """
    data=request.get_json(silent=True) or {}
    action=str(data.get('action') or '').upper()
    if action not in {'NOT_INTERESTED','HIDE'}:return jsonify(error='invalid_action'),400
    source_type=str(data.get('source_type') or 'SOCIAL').upper()
    source_type='CURATED' if source_type=='CURATED' else 'SOCIAL'
    try:source_id=int(data.get('source_id'))
    except (TypeError,ValueError):return jsonify(error='invalid_source_id'),400
    if source_id<=0:return jsonify(error='invalid_source_id'),400
    if source_type=='SOCIAL':
        if not post_visible_to(session['user_id'],source_id):return jsonify(error='not_found'),404
    else:
        from services.curated_feed import curated_item_visible_to
        if not curated_item_visible_to(session['user_id'],source_id):return jsonify(error='not_found'),404
    record_signal(session['user_id'],source_type,source_id,action)
    return jsonify(ok=True,action=action)

@child_bp.route('/notifications/')
@child_required
def notifications():
    user_id=session['user_id']
    pending=fetch_all('''SELECT CASE WHEN f.child_id=%s THEN f.following_child_id ELSE f.child_id END AS requester_id,
       u.full_name,u.username,cp.profile_picture,f.created_at,f.approval_stage
       FROM followers f JOIN users u ON u.user_id=CASE WHEN f.child_id=%s THEN f.following_child_id ELSE f.child_id END
       LEFT JOIN child_profiles cp ON cp.child_id=u.user_id
       WHERE (f.child_id=%s OR f.following_child_id=%s) AND f.approved=FALSE ORDER BY f.created_at DESC''',(user_id,user_id,user_id,user_id))
    raw_items=fetch_all('''SELECT n.*,u.username actor_username,u.full_name actor_name,cp.profile_picture actor_avatar
       FROM notifications n LEFT JOIN users u ON u.user_id=n.actor_id LEFT JOIN child_profiles cp ON cp.child_id=n.actor_id
       WHERE n.user_id=%s ORDER BY n.created_at DESC LIMIT 100''',(user_id,))
    post_ids=[]
    for it in raw_items:
        url=it.get('target_url') or ''
        if url.startswith('/post/'):
            parts=url.strip('/').split('/')
            if len(parts)>=2 and parts[1].isdigit():post_ids.append(int(parts[1]))
    post_thumbs={}
    if post_ids:
        # `posts` has media_path/poster_path (no media_url/thumbnail_url columns);
        # a thumbnail failure must never 500 the whole notifications page.
        try:
            rows=fetch_all('SELECT post_id, media_path, poster_path FROM posts WHERE post_id = ANY(%s)',(list(set(post_ids)),))
            for r in rows:post_thumbs[r['post_id']]=r.get('poster_path') or r.get('media_path')
        except Exception:
            post_thumbs={}
    import datetime
    now=datetime.datetime.now(datetime.timezone.utc) if hasattr(datetime,'timezone') else datetime.datetime.utcnow()
    sections={'today':[],'yesterday':[],'this_week':[],'earlier':[]};items=[]
    for it in raw_items:
        item=dict(it);url=item.get('target_url') or ''
        if url.startswith('/post/'):
            parts=url.strip('/').split('/');item['thumbnail']=post_thumbs.get(int(parts[1])) if len(parts)>=2 and parts[1].isdigit() else None
        else:item['thumbnail']=None
        ntype=item.get('notification_type','')
        if 'COMMENT' in ntype:item['filter_category']='comments'
        elif 'FOLLOW' in ntype or 'FRIEND' in ntype:item['filter_category']='follows'
        elif item.get('actor_id'):item['filter_category']='people'
        else:item['filter_category']='all'
        msg=item.get('message') or '';actor_name=item.get('actor_name') or '';actor_user=item.get('actor_username') or '';clean_msg=msg
        for prefix in [f"{actor_name} ",f"{actor_user} ","Someone "]:
            if clean_msg.startswith(prefix):clean_msg=clean_msg[len(prefix):];break
        item['action_text']=clean_msg;created=item.get('created_at');time_str='1m';group='earlier'
        if created:
            delta=(now-created) if hasattr(created,'tzinfo') and created.tzinfo is not None else (datetime.datetime.utcnow()-created)
            secs=max(0,int(delta.total_seconds()));days=delta.days
            if secs<60:time_str=f"{secs}s";group='today'
            elif secs<3600:time_str=f"{secs//60}m";group='today'
            elif secs<86400:time_str=f"{secs//3600}h";group='today'
            elif days==1:time_str='1d';group='yesterday'
            elif days<7:time_str=f"{days}d";group='this_week'
            elif days<14:time_str='1w';group='earlier'
            else:time_str=f"{days//7}w";group='earlier'
        item['time_ago']=time_str;item['time_group']=group;sections[group].append(item);items.append(item)
    return render_template('notifications.html',pending_requests=pending,items=items,sections=sections,role='CHILD')

@child_bp.route('/child/follow-requests/<int:requester_id>/accept/',methods=['POST'])
@child_required
def accept_follow_request(requester_id):
    return jsonify(error='Parent approval required'),403

@child_bp.route('/child/follow-requests/<int:requester_id>/decline/',methods=['POST'])
@child_required
def decline_follow_request(requester_id):
    execute('DELETE FROM followers WHERE approved=FALSE AND ((child_id=%s AND following_child_id=%s) OR (child_id=%s AND following_child_id=%s))',(requester_id,session['user_id'],session['user_id'],requester_id));return redirect('/notifications/')

@child_bp.route('/notifications/read/',methods=['POST'])
@child_required
def notifications_read():execute('UPDATE notifications SET is_read=TRUE WHERE user_id=%s',(session['user_id'],));return jsonify(ok=True)

@child_bp.route('/api/time-remaining/')
@child_required
def api_time_remaining():
    locked,remaining=lock_state(session['user_id']);return jsonify(remaining_minutes=remaining,locked=locked)

@child_bp.route('/recommended/')
@child_required
def recommended():
    g=_guard()
    if g:return g
    return render_template('recommended.html',posts=recommended_posts(session['user_id'],30,0),stories=active_stories(session['user_id']))

@child_bp.route('/child/upload-profile-picture/',methods=['POST'])
@child_required
def upload_profile_picture():
    photo=request.files.get('photo')
    if not photo or not photo.filename:return jsonify(error='No photo'),400
    if request.content_length and request.content_length>8*1024*1024:return jsonify(error='Photo too large'),413
    os.makedirs('uploads/profile_pictures',exist_ok=True);path=os.path.join('uploads/profile_pictures',f'profile_{session["user_id"]}_{uuid.uuid4().hex}.jpg');photo.save(path)
    try:
        from PIL import Image
        Image.open(path).verify();sig,d=evaluate(session['user_id'],'IMAGE',path)
        if d.action!='ALLOW':
            try:os.remove(path)
            except OSError:pass
            parent_notify(session['user_id'],'PROFILE_PHOTO_BLOCKED',d.reason,'/parent/safety/');return jsonify(status=d.action),400
        execute('UPDATE child_profiles SET profile_picture=%s,updated_at=NOW() WHERE child_id=%s',(path,session['user_id']));session['_avatar']=path;return jsonify(ok=True,path='/'+path)
    except Exception:
        try:os.remove(path)
        except OSError:pass
        return jsonify(error='Invalid or unsafe photo'),400

@child_bp.route('/api/usage/heartbeat/',methods=['POST'])
@child_required
def usage_heartbeat():
    active=(request.get_json(silent=True) or {}).get('active',True)
    if not isinstance(active,bool):return jsonify(error='invalid active state'),400
    key=session.get('usage_session_key')
    if not active:
        if key:close_session(key)
        session.pop('usage_session_key',None);return jsonify(ok=True,active=False)
    quiet=quiet_hours_state(session['user_id'])
    if quiet['active']:return jsonify(ok=True,locked=False,quiet_hours=True,quiet_start=quiet['start'],quiet_end=quiet['end'],redirect='/quiet-hours/')
    if not key or heartbeat(key) is None:session['usage_session_key']=str(start_session(session['user_id'])['session_key'])
    locked,remaining=lock_state(session['user_id']);return jsonify(ok=True,locked=locked,remaining_minutes=remaining,quiet_hours=False,redirect='/child/dashboard/' if not locked else None)

@child_bp.route('/quiet-hours/')
@child_required
def quiet_hours_page():
    quiet=quiet_hours_state(session['user_id'])
    if not quiet['active']:return redirect('/child/dashboard/')
    return render_template('quiet_hours.html',quiet=quiet)

@child_bp.route('/report/',methods=['POST'])
@limiter.limit('15 per hour')
@child_required
def report_content():
    kind=(request.form.get('target_type') or '').upper();reason=(request.form.get('reason') or '').strip()
    try:tid=int(request.form.get('target_id',0))
    except:return jsonify(error='invalid target'),400
    if kind not in {'USER','POST','COMMENT','MESSAGE'} or not reason:return jsonify(error='invalid report'),400
    valid=False
    if kind=='USER':valid=bool(fetch_one("SELECT 1 FROM users WHERE user_id=%s AND role='CHILD' AND user_id<>%s",(tid,session['user_id']))) and can_discover_child(session['user_id'],tid)
    elif kind=='POST':
        from services.social import post_visible_to
        valid=bool(post_visible_to(session['user_id'],tid))
    elif kind=='COMMENT':
        row=fetch_one("SELECT post_id FROM comments WHERE comment_id=%s AND moderation_status='ALLOWED'",(tid,));valid=bool(row and post_visible_to(session['user_id'],row['post_id']))
    elif kind=='MESSAGE':valid=bool(fetch_one('SELECT 1 FROM child_messages WHERE child_message_id=%s AND (sender_child_id=%s OR receiver_child_id=%s)',(tid,session['user_id'],session['user_id'])))
    if not valid:return jsonify(error='target unavailable'),404
    execute('INSERT INTO reports(reporter_id,target_type,target_id,reason,details) VALUES(%s,%s,%s,%s,%s)',(session['user_id'],kind,tid,reason[:100],(request.form.get('details') or '')[:2000]))
    record_signal(session['user_id'],'CREATOR' if kind=='USER' else 'SOCIAL',tid,'REPORT')
    return jsonify(ok=True)

def _check_live_frame(frame):
    os.makedirs('uploads/live',exist_ok=True);path=os.path.join('uploads/live',f'{uuid.uuid4().hex}.jpg');frame.save(path)
    try:
        from PIL import Image
        Image.open(path).verify();sig,d=evaluate(session['user_id'],'IMAGE',path)
        if d.action!='ALLOW':
            import time
            now=time.time();last=float(session.get('last_live_safety_event',0) or 0)
            if now-last>=30:
                event_id=record(session['user_id'],'LIVE_FRAME',None,sig,d);execute("UPDATE moderation_events SET status='RESOLVED' WHERE event_id=%s",(event_id,));parent_notify(session['user_id'],'LIVE_SAFETY_'+d.action,'Live Safety detected content that was '+('blocked.' if d.action=='BLOCK' else 'flagged.'),'/parent/notifications/');session['last_live_safety_event']=now
        return {'decision':d.action,'reason':d.reason,'risk':d.risk,'adult_score':round(float(sig.get('adult_score',0))*100,1),'weapon_score':round(float(sig.get('weapon_score',0))*100,1),'violence_score':round(float(sig.get('violence_score',0))*100,1)}
    finally:
        try:os.remove(path)
        except OSError:pass

@child_bp.route('/live-safety/',methods=['GET','POST'])
@child_required
def live_safety():
    result=None
    if request.method=='POST':
        frame=request.files.get('frame')
        if frame:
            try:result=_check_live_frame(frame)
            except Exception:result={'decision':'BLOCK','reason':'Live safety check unavailable: fail closed','risk':100}
    return render_template('live_safety.html',result=result)

@child_bp.route('/api/live-safety/check/',methods=['POST'])
@child_required
@limiter.limit('45 per minute')
def live_safety_api():
    frame=request.files.get('frame')
    if not frame:return jsonify(error='frame required'),400
    try:return jsonify(_check_live_frame(frame))
    except Exception:return jsonify(decision='BLOCK',reason='Live safety check unavailable: fail closed',risk=100),503

@child_bp.route('/api/following/')
@child_required
def api_following():
    rows=fetch_all("SELECT u.user_id,u.full_name FROM followers f JOIN users u ON u.user_id=f.following_child_id WHERE f.child_id=%s AND f.approved=TRUE AND f.approval_stage='ACTIVE'",(session['user_id'],));return jsonify(rows)

@child_bp.route('/api/share-post/',methods=['POST'])
@child_required
def api_share_post():
    data=request.get_json(silent=True) or {}
    try:receiver=int(data.get('receiver_id'));post_id=int(data.get('post_id'))
    except:return jsonify(error='invalid request'),400
    from services.social import is_post_shareable_to
    from childMessage.service import conversation
    ok,reason=is_post_shareable_to(post_id,session['user_id'],receiver)
    if not ok:return jsonify(error=reason),403
    cid=conversation(session['user_id'],receiver);execute("INSERT INTO child_messages(conversation_id,sender_child_id,receiver_child_id,message_type,shared_post_id,moderation_status) VALUES(%s,%s,%s,'SHARED_POST',%s,'ALLOWED')",(cid,session['user_id'],receiver,post_id));record_signal(session['user_id'],'SOCIAL',post_id,'SHARE');return jsonify(ok=True)

@child_bp.route('/time-limit-reached/')
@child_required
def time_limit_reached():return render_template('time_limit_reached.html')

@child_bp.route('/child/edit-profile/',methods=['GET','POST'])
@child_required
def edit_profile():
    if request.method=='POST':
        from safety.pii_service import scan_pii
        if scan_pii(_public_profile_text(request.form))['detected']:
            return render_template('edit_profile.html',profile=get_child_profile(session['user_id']),error='Profile cannot contain phone numbers, addresses, or external contacts.'),400
        signals,d=evaluate(session['user_id'],'TEXT',_public_profile_text(request.form))
        if d.action!='ALLOW':return render_template('edit_profile.html',profile=get_child_profile(session['user_id']),error='Profile text could not be published under Kids Mode safety rules.'),400
        execute('UPDATE child_profiles SET full_name=%s,school_name=%s,location=%s,current_class=%s,bio=%s,updated_at=NOW() WHERE child_id=%s',(request.form.get('full_name'),request.form.get('school_name'),request.form.get('location'),request.form.get('current_class'),request.form.get('bio'),session['user_id']));return redirect('/child/profile/')
    return render_template('edit_profile.html',profile=get_child_profile(session['user_id']))

@child_bp.route('/followers/')
@child_required
def followers():return render_template('people_list.html',title='Friends',people=fetch_all("SELECT DISTINCT u.user_id,u.full_name,cp.profile_picture FROM followers f JOIN users u ON u.user_id=CASE WHEN f.child_id=%s THEN f.following_child_id ELSE f.child_id END LEFT JOIN child_profiles cp ON cp.child_id=u.user_id WHERE (f.child_id=%s OR f.following_child_id=%s) AND f.approved=TRUE AND f.approval_stage='ACTIVE'",(session['user_id'],session['user_id'],session['user_id'])))

@child_bp.route('/following/')
@child_required
def following():return render_template('people_list.html',title='Friends',people=fetch_all("SELECT DISTINCT u.user_id,u.full_name,cp.profile_picture FROM followers f JOIN users u ON u.user_id=CASE WHEN f.child_id=%s THEN f.following_child_id ELSE f.child_id END LEFT JOIN child_profiles cp ON cp.child_id=u.user_id WHERE (f.child_id=%s OR f.following_child_id=%s) AND f.approved=TRUE AND f.approval_stage='ACTIVE'",(session['user_id'],session['user_id'],session['user_id'])))

@child_bp.route('/unfollow/<int:child_id>/',methods=['POST'])
@child_required
def unfollow(child_id):unfollow_child(session['user_id'],child_id);return redirect('/following/')
