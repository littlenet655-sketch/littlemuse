import os,uuid
from flask import Blueprint,render_template,request,session,jsonify,redirect
from decorators import child_required
from config import Config
from database.connection import execute,fetch_one,fetch_all
from services.social import visible_posts,active_stories,notify,parent_notify,post_visible_to,can_interact
from safety.moderation_service import evaluate,record,safety_level
from safety.policy import decide
from safety.visual_service import video_duration_seconds
from quiz.service import bump
from services.audit import log
from services.controls import SAFE_CATEGORIES, controls_for_child, effective_categories
from extensions import limiter
from services.recommendation_signals import record_signal

upload_bp=Blueprint('upload',__name__,template_folder='templates')
IMG={'jpg','jpeg','png','webp'};VID={'mp4','mov','avi','mkv','webm'};AUD={'mp3','wav','m4a','ogg','webm'}
def _save(file,folder,ext):
    os.makedirs(folder,exist_ok=True);p=os.path.join(folder,f'{uuid.uuid4().hex}.{ext}');file.save(p);return p
def _unlink(path):
    if path and not str(path).startswith('uploads/r2/'):
        try:os.remove(path)
        except OSError:pass

def _media_type(file):
    name=file.filename or '';ext=name.rsplit('.',1)[-1].lower() if '.' in name else '';mime=(file.mimetype or '').lower()
    if ext in IMG:return 'IMAGE',ext
    if ext in AUD and (mime.startswith('audio/') or ext!='webm'):return 'AUDIO',ext
    if ext in VID:return 'VIDEO',ext
    return None,ext

def _merge(*signals):
    out={'adult_score':0.0,'violence_score':0.0,'weapon_score':0.0,'toxicity_score':0.0,'general_score':0.0,'partial_safety_failure':False,'total_safety_failure':False,'sources':[]}
    valid=[s for s in signals if s]
    if not valid:out['total_safety_failure']=True;return out
    for s in valid:
        for k in ['adult_score','violence_score','weapon_score','toxicity_score','general_score']:out[k]=max(float(out.get(k,0)),float(s.get(k,0) or 0))
        out['partial_safety_failure']=out['partial_safety_failure'] or bool(s.get('partial_safety_failure'))
        out['sources'].append(s.get('category','UNKNOWN'))
    out['total_safety_failure']=any(bool(s.get('total_safety_failure')) for s in valid)
    out['category']='ADULT' if out['adult_score']>=Config.ADULT_HARD_BLOCK_THRESHOLD else ('WEAPON' if out['weapon_score']>=.45 else 'CONTENT')
    return out

def _create(content_type,payload,caption,category,is_story=False,is_reel=False,path=None,music_path=None,music_signals=None,audience_age_group='ALL'):
    from safety.pii_service import scan_pii
    if caption and scan_pii(caption)['detected']:
        from safety.policy import Decision
        _unlink(path);_unlink(music_path)
        d=Decision('BLOCK',100.0,'Personal contact or phone number sharing in caption is prohibited')
        parent_notify(session['user_id'],'CONTENT_BLOCKED',d.reason,'/parent/safety/')
        return None,d
    cs,_=evaluate(session['user_id'],'TEXT',caption or '')
    ms,_=evaluate(session['user_id'],content_type,payload) if content_type!='TEXT' else (cs,None)
    merged=_merge(cs,ms,music_signals)
    d=decide(merged,safety_level(session['user_id']),Config.ADULT_HARD_BLOCK_THRESHOLD)
    if d.action=='BLOCK':
        record(session['user_id'],content_type,None,merged,d);parent_notify(session['user_id'],'CONTENT_BLOCKED',d.reason,'/parent/safety/');_unlink(path);_unlink(music_path);return None,d

    if path and content_type == 'IMAGE':
        from services.media_sanitizer import sanitize_image_in_place
        sanitize_image_in_place(path)

    stored_path=path;stored_music=music_path;persisted=[]
    try:
        from services.media_persistence import persist_before_db,rollback_reference
        namespace='stories' if is_story else ('reels' if is_reel else 'posts')
        if path:
            stored_path=persist_before_db(path,namespace,session['user_id']);persisted.append(stored_path)
        if music_path:
            stored_music=persist_before_db(music_path,'story-music',session['user_id']);persisted.append(stored_music)
        row=execute('''INSERT INTO posts(child_id,media_type,media_path,story_music_path,caption,content_category,audience_age_group,is_story,is_reel,safety_score,adult_score,violence_score,weapon_score,toxicity_score,is_safe,moderation_status,moderation_reason) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING post_id''',(
            session['user_id'],content_type,stored_path,stored_music,caption,category,audience_age_group,is_story,is_reel,d.risk,merged['adult_score']*100,merged['violence_score']*100,merged['weapon_score']*100,merged['toxicity_score']*100,d.action=='ALLOW','ALLOWED' if d.action=='ALLOW' else 'REVIEW',d.reason),returning=True)
    except Exception:
        try:
            for ref in persisted:rollback_reference(ref)
        except Exception:pass
        _unlink(path);_unlink(music_path)
        raise
    event=record(session['user_id'],content_type,row['post_id'],merged,d)
    if d.action=='REVIEW':parent_notify(session['user_id'],'REVIEW_REQUIRED','Content is waiting for your review',f'/parent/safety/?event={event}')
    elif d.action=='ALLOW':
        from services.publication_lifecycle import refresh_publication_visibility
        refresh_publication_visibility(row['post_id'], session['user_id'], is_reel=is_reel)
    log(session['user_id'],'POST_CREATED',{'post_id':row['post_id'],'status':d.action,'type':content_type})
    try:
        from services.analytics import capture as analytics_capture
        analytics_capture(session['user_id'], 'post_created', {
            'post_id': row['post_id'], 'status': d.action,
            'kind': 'story' if is_story else ('reel' if is_reel else 'post'),
        })
    except Exception:
        pass
    return row['post_id'],d

@upload_bp.route('/feed/')
@child_required
def feed():
    bump(session['user_id']);return render_template('feed.html',posts=visible_posts(session['user_id'],False,30,0),stories=active_stories(session['user_id']))
@upload_bp.route('/reels/')
@child_required
def reels():
    bump(session['user_id']);return render_template('reels.html',reels=visible_posts(session['user_id'],True,10,0))
@upload_bp.route('/api/reels/')
@child_required
def api_reels():
    try:page=max(1,int(request.args.get('page',1)))
    except:page=1
    return jsonify(visible_posts(session['user_id'],True,10,(page-1)*10))

@upload_bp.route('/child/upload-post/',methods=['GET','POST'])
@limiter.limit('30 per hour')
@child_required
def upload_post(force_kind=None):
    if request.method=='GET' and force_kind is None:return render_template('upload_post.html')
    caption=(request.form.get('caption') or '').strip();category=request.form.get('content_category','Other');category=category if category in SAFE_CATEGORIES else 'Other';kind=force_kind or request.form.get('kind','post');is_reel=kind=='reel';is_story=kind=='story';audience=request.form.get('audience_age_group','ALL');audience=audience if audience in {'ALL','6-8','9-11','12-13','14-18'} else 'ALL';controls=controls_for_child(session['user_id']);file=request.files.get('media')
    if len(caption)>Config.MAX_USER_TEXT_CHARS:return jsonify(error='caption too long'),400
    if is_reel and not controls.get('allow_reels',True):return jsonify(error='Reels are disabled by Parent Mode'),403
    if is_story and not controls.get('allow_stories',True):return jsonify(error='Stories are disabled by Parent Mode'),403
    if not controls.get('allow_posting',True):return jsonify(error='Posting is disabled by Parent Mode'),403
    if category not in effective_categories(session['user_id']):return jsonify(error='This content category is disabled by Parent Mode'),403
    music_path=None;music_signals=None
    music=request.files.get('music_file') if is_story else None
    if music and music.filename:return jsonify(error='Story music/audio uploads are disabled in LittleNet'),400
    if not file or not file.filename:
        if caption:
            _,d=_create('TEXT',caption,caption,category,is_story,is_reel,None,music_path,music_signals,audience);return jsonify(success=d.action!='BLOCK',status=d.action,reason=d.reason,risk=d.risk),200 if d.action!='BLOCK' else 400
        return jsonify(error='Select media or enter text'),400
    mt,ext=_media_type(file)
    if not mt:return jsonify(error='Unsupported file'),400
    if mt=='AUDIO':return jsonify(error='Standalone audio and voice uploads are disabled in LittleNet'),400
    max_mb=15 if mt=='IMAGE' else 80
    if request.content_length and request.content_length>max_mb*1024*1024+10*1024*1024:return jsonify(error='File too large'),413
    folder='uploads/images' if mt=='IMAGE' else 'uploads/videos';path=_save(file,folder,ext)
    if mt=='IMAGE':
        try:
            from PIL import Image;Image.open(path).verify()
        except Exception:_unlink(path);return jsonify(error='Invalid image'),400
    if mt=='VIDEO':
        dur=video_duration_seconds(path);limit=Config.REEL_MAX_SECONDS if is_reel else Config.STORY_MAX_SECONDS if is_story else Config.VIDEO_MAX_SECONDS
        if dur<=0 or dur>limit:_unlink(path);return jsonify(error=f'Video must be under {limit} seconds'),400
    try:
        _,d=_create(mt,path,caption,category,is_story,is_reel,path,None,None,audience)
    except Exception:
        return jsonify(error='Secure media persistence failed; content was not published'),503
    return jsonify(success=d.action!='BLOCK',status=d.action,reason=d.reason,risk=d.risk),200 if d.action!='BLOCK' else 400

@upload_bp.route('/like/<int:post_id>/',methods=['POST'])
@child_required
def like(post_id):
    p=post_visible_to(session['user_id'],post_id)
    if not p:return jsonify(error='not found'),404
    if p['child_id']!=session['user_id'] and not can_interact(session['user_id'],p['child_id']):return jsonify(error='approved connection required'),403
    exists=fetch_one('SELECT 1 FROM likes WHERE post_id=%s AND child_id=%s',(post_id,session['user_id']))
    if exists:execute('DELETE FROM likes WHERE post_id=%s AND child_id=%s',(post_id,session['user_id']));liked=False
    else:
        execute('INSERT INTO likes(post_id,child_id) VALUES(%s,%s)',(post_id,session['user_id']));liked=True
        record_signal(session['user_id'],'SOCIAL',post_id,'LIKE')
        if p['child_id']!=session['user_id']:notify(p['child_id'],'LIKE',f'{session.get("full_name","Someone")} liked your post',f'/post/{post_id}/',session['user_id'])
    return jsonify(liked=liked)

@upload_bp.route('/comment/<int:post_id>/',methods=['POST'])
@child_required
def comment(post_id):
    p=post_visible_to(session['user_id'],post_id);text=((request.get_json(silent=True) or {}).get('text','') if request.is_json else (request.form.get('comment') or '')).strip()
    if not p:return jsonify(error='not found'),404
    if p['child_id']!=session['user_id'] and not can_interact(session['user_id'],p['child_id']):return jsonify(error='approved connection required'),403
    if not text:return jsonify(error='empty comment'),400
    if len(text)>Config.MAX_USER_TEXT_CHARS:return jsonify(error='comment too long'),400
    from safety.pii_service import scan_pii
    pii_res = scan_pii(text)
    if pii_res['detected'] and pii_res['policy_action'] == 'BLOCK':
        parent_notify(session['user_id'],'COMMENT_BLOCKED','Attempted contact/PII sharing in comment','/parent/safety/')
        return jsonify(blocked=True,error="Personal contact info cannot be shared in comments."),400
    sig,d=evaluate(session['user_id'],'TEXT',text)
    if d.action=='BLOCK':record(session['user_id'],'COMMENT',None,sig,d);parent_notify(session['user_id'],'COMMENT_BLOCKED',d.reason,'/parent/safety/');return jsonify(blocked=True),400
    row=execute("INSERT INTO comments(post_id,child_id,comment_text,moderation_status) VALUES(%s,%s,%s,%s) RETURNING comment_id",(post_id,session['user_id'],text,'ALLOWED' if d.action=='ALLOW' else 'REVIEW'),returning=True)
    if d.action=='ALLOW':record_signal(session['user_id'],'SOCIAL',post_id,'COMMENT')
    record(session['user_id'],'COMMENT',row['comment_id'],sig,d)
    if d.action=='REVIEW':parent_notify(session['user_id'],'REVIEW_REQUIRED','A comment needs review','/parent/safety/')
    elif p['child_id']!=session['user_id']:notify(p['child_id'],'COMMENT',f'{session.get("full_name","Someone")} commented on your post',f'/post/{post_id}/',session['user_id'])
    return jsonify(status=d.action) if request.is_json else redirect(f'/post/{post_id}/')

@upload_bp.route('/post/<int:post_id>/')
@child_required
def post_detail(post_id):
    p=post_visible_to(session['user_id'],post_id)
    if p:
        extra=fetch_one('SELECT u.full_name,cp.profile_picture FROM users u LEFT JOIN child_profiles cp ON cp.child_id=u.user_id WHERE u.user_id=%s',(p['child_id'],));p.update(extra or {})
    if not p:return ('Not found',404)
    return render_template('post_detail.html',post=p,comments=fetch_all("""SELECT c.*,u.full_name FROM comments c JOIN users u ON u.user_id=c.child_id
        WHERE c.post_id=%s AND c.moderation_status='ALLOWED' AND (c.child_id=%s OR EXISTS(
          SELECT 1 FROM followers f WHERE f.approved=TRUE AND ((f.child_id=c.child_id AND f.following_child_id=%s) OR (f.following_child_id=c.child_id AND f.child_id=%s))))
        ORDER BY c.created_at""",(post_id,p['child_id'],p['child_id'],p['child_id'])))

@upload_bp.route('/delete-post/<int:post_id>/',methods=['POST'])
@child_required
def delete_post(post_id):
    p=fetch_one('SELECT * FROM posts WHERE post_id=%s AND child_id=%s',(post_id,session['user_id']))
    if not p:return jsonify(error='not found'),404
    execute('INSERT INTO deleted_posts(original_post_id,child_id,media_type,media_path,caption,content_category) VALUES(%s,%s,%s,%s,%s,%s)',(p['post_id'],p['child_id'],p['media_type'],p.get('media_path'),p.get('caption'),p.get('content_category')))
    execute('DELETE FROM posts WHERE post_id=%s',(post_id,));_unlink(p.get('media_path'));_unlink(p.get('story_music_path'));return jsonify(ok=True)

@upload_bp.route('/save/<int:post_id>/',methods=['POST'])
@child_required
def save_post(post_id):
    p=post_visible_to(session['user_id'],post_id)
    if not p:return jsonify(error='not found'),404
    exists=fetch_one('SELECT 1 FROM saved_posts WHERE child_id=%s AND post_id=%s',(session['user_id'],post_id))
    if exists:
        execute('DELETE FROM saved_posts WHERE child_id=%s AND post_id=%s',(session['user_id'],post_id));saved=False
    else:
        execute('INSERT INTO saved_posts(child_id,post_id) VALUES(%s,%s) ON CONFLICT DO NOTHING',(session['user_id'],post_id));saved=True
        record_signal(session['user_id'],'SOCIAL',post_id,'SAVE')
    return jsonify(saved=saved)

@upload_bp.route('/saved/')
@child_required
def saved_posts_page():
    rows=fetch_all('''SELECT p.*,u.full_name,cp.profile_picture,
      (SELECT COUNT(*) FROM likes l WHERE l.post_id=p.post_id) likes,
      (SELECT COUNT(*) FROM comments c WHERE c.post_id=p.post_id AND c.moderation_status='ALLOWED') comments_count
      FROM saved_posts s JOIN posts p ON p.post_id=s.post_id JOIN users u ON u.user_id=p.child_id
      LEFT JOIN child_profiles cp ON cp.child_id=p.child_id
      WHERE s.child_id=%s AND p.moderation_status='ALLOWED' AND p.is_safe=TRUE
      ORDER BY s.created_at DESC''',(session['user_id'],))
    visible=[p for p in rows if post_visible_to(session['user_id'],p['post_id'])]
    return render_template('saved_posts.html',posts=visible)

@upload_bp.route('/my-posts/')
@child_required
def my_posts():return render_template('my_posts.html',posts=fetch_all("SELECT * FROM posts WHERE child_id=%s AND is_story=FALSE ORDER BY created_at DESC",(session['user_id'],)))

@upload_bp.route('/api/like/<int:post_id>/',methods=['POST'])
@limiter.limit('60 per minute')
@child_required
def api_like(post_id):return like(post_id)
@upload_bp.route('/api/comment/<int:post_id>/',methods=['POST'])
@limiter.limit('30 per minute')
@child_required
def api_comment(post_id):return comment(post_id)
@upload_bp.route('/api/comments/<int:post_id>/')
@child_required
def api_comments(post_id):
    if not post_visible_to(session['user_id'],post_id):return jsonify([]),404
    p=post_visible_to(session['user_id'],post_id)
    if not p:return jsonify([]),404
    return jsonify(fetch_all("""SELECT c.comment_text,u.full_name FROM comments c JOIN users u ON u.user_id=c.child_id
      WHERE c.post_id=%s AND c.moderation_status='ALLOWED' AND (c.child_id=%s OR EXISTS(SELECT 1 FROM followers f WHERE f.approved=TRUE AND ((f.child_id=c.child_id AND f.following_child_id=%s) OR (f.following_child_id=c.child_id AND f.child_id=%s)))) ORDER BY c.created_at""",(post_id,p['child_id'],p['child_id'],p['child_id'])))
@upload_bp.route('/api/post-detail/<int:post_id>/')
@child_required
def api_post_detail(post_id):
    p=post_visible_to(session['user_id'],post_id)
    return jsonify(p) if p else (jsonify(error='not found'),404)
@upload_bp.route('/api/random-posts/')
@child_required
def api_random_posts():return jsonify(visible_posts(session['user_id'],False,6,0))

@upload_bp.route('/upload-story/',methods=['POST'])
@limiter.limit('30 per hour')
@child_required
def upload_story_alias():
    files=[f for f in request.files.getlist('media') if f and f.filename]
    caption=(request.form.get('caption') or '').strip();category=request.form.get('content_category','Other');category=category if category in SAFE_CATEGORIES else 'Other';audience=request.form.get('audience_age_group','ALL');audience=audience if audience in {'ALL','6-8','9-11','12-13','14-18'} else 'ALL';controls=controls_for_child(session['user_id'])
    if len(caption)>Config.MAX_USER_TEXT_CHARS:return jsonify(error='caption too long'),400
    if not controls.get('allow_posting',True) or not controls.get('allow_stories',True):return jsonify(error='Stories are disabled by Parent Mode'),403
    if category not in effective_categories(session['user_id']):return jsonify(error='This content category is disabled by Parent Mode'),403
    music=request.files.get('music_file')
    if music and music.filename:return jsonify(error='Story music/audio uploads are disabled in LittleNet'),400
    if not files:
        if not caption:return jsonify(error='No Story content'),400
        _,d=_create('TEXT',caption,caption,category,True,False,None,None,None,audience);return jsonify(success=d.action!='BLOCK',count=1 if d.action!='BLOCK' else 0,status=d.action,reason=d.reason,risk=d.risk),200 if d.action!='BLOCK' else 400
    results=[]
    for file in files[:10]:
        mt,ext=_media_type(file)
        if mt=='AUDIO':results.append({'name':file.filename,'status':'AUDIO_DISABLED'});continue
        if mt not in {'IMAGE','VIDEO'}:results.append({'name':file.filename,'status':'UNSUPPORTED'});continue
        folder='uploads/images' if mt=='IMAGE' else 'uploads/videos';path=_save(file,folder,ext)
        try:
            if mt=='IMAGE':
                from PIL import Image;Image.open(path).verify()
            if mt=='VIDEO':
                dur=video_duration_seconds(path)
                if dur<=0 or dur>Config.STORY_MAX_SECONDS:raise ValueError('story_video_duration')
            pid,d=_create(mt,path,caption,category,True,False,path,None,None,audience);results.append({'name':file.filename,'post_id':pid,'status':d.action})
        except Exception:
            _unlink(path);results.append({'name':file.filename,'status':'ERROR'})
    accepted=[r for r in results if r.get('status') in {'ALLOW','REVIEW'}]
    return jsonify(success=bool(accepted),count=len(accepted),results=results),200 if accepted else 400
@upload_bp.route('/api/delete-story/<int:post_id>/',methods=['POST'])
@child_required
def delete_story(post_id):
    p=fetch_one("SELECT * FROM posts WHERE post_id=%s AND child_id=%s AND is_story=TRUE",(post_id,session['user_id']))
    if not p:return jsonify(ok=False),404
    execute('DELETE FROM posts WHERE post_id=%s',(post_id,));_unlink(p.get('media_path'));_unlink(p.get('story_music_path'));return jsonify(ok=True)
@upload_bp.route('/api/edit-story-caption/<int:post_id>/',methods=['POST'])
@child_required
def edit_story_caption(post_id):
    data=request.get_json(silent=True) or {};caption=(data.get('caption') or '').strip()
    if len(caption)>Config.MAX_USER_TEXT_CHARS:return jsonify(ok=False,error='caption too long'),400
    from safety.pii_service import scan_pii
    pii=scan_pii(caption)
    if pii.get('detected') and pii.get('policy_action')=='BLOCK':return jsonify(ok=False,status='BLOCK',reason='CONTACT_SHARING_BLOCKED'),400
    sig,d=evaluate(session['user_id'],'TEXT',caption)
    if d.action!='ALLOW':return jsonify(ok=False,status=d.action),400
    execute("UPDATE posts SET caption=%s WHERE post_id=%s AND child_id=%s AND is_story=TRUE AND moderation_status='ALLOWED'",(caption,post_id,session['user_id']));return jsonify(ok=True)
