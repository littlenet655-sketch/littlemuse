from werkzeug.middleware.proxy_fix import ProxyFix
from flask import Flask,send_from_directory,session,request,jsonify,redirect,render_template,g
from config import Config
from extensions import csrf,limiter
from auth.routes import auth_bp
from auth.api import api_bp
from child.search_routes import content_search_bp
from child.routes import child_bp
from uploadPost.routes import upload_bp
from childMessage.routes import child_message_bp
from parent.routes import parent_bp
from parent.api import parent_api_bp
from quiz.routes import quiz_bp
from admin.routes import admin_bp
from mailg.webhooks import resend_webhook_bp
from database.connection import fetch_one, execute
from services.usage import lock_state,heartbeat,start_session
from quiz.service import quiz_due, needs_onboarding_quiz
from services.controls import controls_for_child, feature_allowed, effective_categories, quiet_hours_state
from services.i18n import language_for_user, tr, LANGUAGES


def create_app():
    app=Flask(__name__);app.config.from_object(Config)
    app.wsgi_app=ProxyFix(app.wsgi_app,x_for=1,x_proto=1,x_host=1,x_port=1)

    def _dynamic_cookie_secure(flask_app):
        if not flask_app.config.get('SESSION_COOKIE_SECURE', False):
            return False
        from flask import has_request_context, request
        if has_request_context() and request:
            return request.is_secure
        return flask_app.config.get('SESSION_COOKIE_SECURE', False)

    app.session_interface.get_cookie_secure = _dynamic_cookie_secure
    if Config._PRODUCTION:
        if Config.SECRET_KEY=='change-me-before-demo' or len(Config.SECRET_KEY)<32:
            raise RuntimeError('Production SECRET_KEY must be a random value of at least 32 characters')
        if Config.AI_SERVICE_URL and not Config.AI_SHARED_SECRET:
            raise RuntimeError('AI_SHARED_SECRET is required when AI_SERVICE_URL is configured')

    csrf.init_app(app);limiter.init_app(app)
    try:
        from services.analytics import init_analytics
        init_analytics()
    except Exception:
        pass
    from flask_wtf.csrf import CSRFError

    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        if request.path.startswith(('/login', '/switch-mode', '/register', '/logout')):
            session.clear()
            return redirect('/login/?error=Your+session+was+refreshed.+Please+enter+your+credentials+to+continue.')
        return render_template('csrf_error.html', reason=e.description), 400

    for bp in [auth_bp,api_bp,content_search_bp,child_bp,upload_bp,child_message_bp,parent_bp,parent_api_bp,quiz_bp,admin_bp,resend_webhook_bp]:
        app.register_blueprint(bp)

    @app.before_request
    def capture_r2_delete_targets():
        """Remember private R2 objects that a successful child delete must purge.

        The cloud delete happens in the after-request path only after the route has
        successfully deleted the DB row. A failed request therefore never destroys
        media that the database still references.
        """
        if request.method!='POST' or session.get('role')!='CHILD' or not session.get('user_id'):
            return None
        path=request.path.rstrip('/')
        post_id=None;story_only=False
        try:
            if path.startswith('/delete-post/'):
                post_id=int(path.split('/')[-1])
            elif path.startswith('/api/delete-story/'):
                post_id=int(path.split('/')[-1]);story_only=True
        except (TypeError,ValueError):
            return None
        if not post_id:return None
        sql='SELECT media_path,poster_path,story_music_path FROM posts WHERE post_id=%s AND child_id=%s'
        params=(post_id,session['user_id'])
        if story_only:sql+=" AND is_story=TRUE"
        row=fetch_one(sql,params)
        if not row:return None
        refs=[]
        for ref in (row.get('media_path'),row.get('poster_path'),row.get('story_music_path')):
            if ref and str(ref).startswith('uploads/r2/'):
                refs.append(str(ref))
        if refs:g.r2_delete_refs=refs
        return None

    @app.before_request
    def signup_preflight():
        """Give deterministic, human-friendly duplicate errors before DB constraints fire."""
        if request.method != 'POST':
            return None
        path = request.path.rstrip('/')
        if path == '/register-parent':
            username=(request.form.get('username') or '').strip()
            email=(request.form.get('email') or '').strip().lower()
            row=fetch_one(
                'SELECT username,email FROM users WHERE LOWER(username)=LOWER(%s) OR LOWER(email)=LOWER(%s) LIMIT 1',
                (username,email)
            )
            if row:
                if (row.get('username') or '').casefold()==username.casefold():
                    error=f"The username '{username}' already exists. Please choose a different username."
                else:
                    error=f"The email '{email}' is already used by a LittleNet account. Please log in instead."
                import random
                n1=random.randint(14,28);n2=random.randint(13,29)
                return render_template('parent_register_direct.html',error=error,challenge_q=f'{n1} + {n2}',challenge_expected=str(n1+n2)),409
        if path == '/parent/create-child' and session.get('role')=='PARENT':
            username=(request.form.get('username') or '').strip()
            email=(request.form.get('email') or '').strip().lower()
            if username or email:
                row=fetch_one(
                    'SELECT username,email FROM users WHERE LOWER(username)=LOWER(%s) OR (%s<>\'\' AND LOWER(email)=LOWER(%s)) LIMIT 1',
                    (username,email,email)
                )
                if row:
                    if (row.get('username') or '').casefold()==username.casefold():
                        error=f"The username '{username}' already exists. Choose another username for your child."
                    else:
                        error=f"The email '{email}' is already used. Use a different child email or log in to the existing account."
                    return render_template('parent_create_child.html',error=error),409
        return None

    @app.before_request
    def enforce_kids_controls():
        if session.get('role')!='CHILD':
            return None
        path=request.path
        if path.startswith('/static/') or path.startswith('/uploads/') or path in {'/logout/','/switch-mode/','/language/','/api/usage/heartbeat/','/quiet-hours/'}:
            return None
        if path.startswith('/quiz/'):
            return None
        if needs_onboarding_quiz(session['user_id']):
            return redirect('/quiz/start/?onboarding=1')

        feature=None
        if path.startswith(('/reels/','/api/reels/')):feature='reels'
        elif path.startswith(('/stories/','/story/','/api/story-view/')):feature='stories'
        elif path.startswith(('/messages/','/chat/','/send-message/','/send-media/','/share-post/','/api/chat/','/api/share-post/')):feature='messaging'
        elif path.startswith(('/upload-story/','/api/delete-story/','/api/edit-story-caption/')):feature='stories'
        elif path.startswith('/child/upload-post/'):feature='posting'
        elif path.startswith(('/discover/','/api/discover/')):feature='discover'
        if feature and not feature_allowed(session['user_id'],feature):
            if path.startswith('/api/') or request.is_json:return jsonify(error='disabled_by_parent',feature=feature),403
            return render_template('feature_restricted.html',feature=feature),403
        if path=='/discover/' and request.method=='GET':
            target='/discover/search/'
            if request.query_string:
                target+='?'+request.query_string.decode('utf-8','ignore')
            return redirect(target)
        quiet=quiet_hours_state(session['user_id'])
        if quiet['active']:
            return render_template('quiet_hours.html',quiet=quiet),403
        key=session.get('usage_session_key')
        if not key or heartbeat(key) is None:
            started=start_session(session['user_id'])
            key=str(started['session_key'])
            session['usage_session_key']=key
            heartbeat(key)
        locked,_=lock_state(session['user_id'])
        if locked:return render_template('time_limit_reached.html'),403
        if quiz_due(session['user_id']):return redirect('/quiz/start/')
        return None

    @app.route('/sw.js')
    def service_worker():
        response = send_from_directory('static', 'sw.js', mimetype='application/javascript')
        response.headers['Service-Worker-Allowed'] = '/'
        return response

    @app.route('/uploads/<path:filename>')
    def uploaded_file(filename):
        import os
        uid=session.get('user_id');role=session.get('role')
        if not uid:return ('Unauthorized',401)
        stored='uploads/'+filename

        p=fetch_one('SELECT post_id,child_id,moderation_status,is_safe,is_story FROM posts WHERE media_path=%s OR story_music_path=%s',(stored,stored))
        if p:
            if role=='CHILD':
                if p['moderation_status']!='ALLOWED' and uid!=p['child_id']:return ('Unavailable',404)
                from services.social import post_visible_to, story_visible_to
                visible=story_visible_to(uid,p['post_id']) if p.get('is_story') else post_visible_to(uid,p['post_id'])
                if not visible:return ('Unavailable',404)
            elif role=='PARENT':
                from parent.service import owns
                if not owns(uid,p['child_id']):return ('Forbidden',403)
            elif role!='ADMIN':return ('Forbidden',403)

        m=fetch_one('SELECT sender_child_id,receiver_child_id,moderation_status FROM child_messages WHERE media_path=%s',(stored,))
        if m:
            if role=='CHILD':
                if uid not in {m['sender_child_id'],m['receiver_child_id']}:return ('Forbidden',403)
                from services.social import can_interact
                if not can_interact(m['sender_child_id'],m['receiver_child_id']):return ('Unavailable',404)
                if m['moderation_status']!='ALLOWED' and uid!=m['sender_child_id']:return ('Unavailable',404)
            elif role=='PARENT':
                from parent.service import owns
                if not owns(uid,m['sender_child_id']):return ('Forbidden',403)
                if m['moderation_status']!='REVIEW':return ('Unavailable',404)
            elif role!='ADMIN':return ('Forbidden',403)

        f=fetch_one('SELECT child_id FROM child_profiles WHERE profile_picture=%s',(stored,))
        if f:
            if role=='CHILD':
                from child.service import can_discover_child
                if not can_discover_child(uid,f['child_id']):return ('Unavailable',404)
            elif role=='PARENT':
                from parent.service import owns
                if not owns(uid,f['child_id']):return ('Forbidden',403)
            elif role!='ADMIN':return ('Forbidden',403)

        default_avatar=filename=='profile_pictures/download.webp'
        if not any([p,m,f]) and not default_avatar:return ('Unavailable',404)

        if stored.startswith('uploads/r2/'):
            try:
                from services.object_storage import signed_download_url
                response=redirect(signed_download_url(stored),302)
                response.headers['Cache-Control']='private, no-store, max-age=0'
                response.headers['Pragma']='no-cache'
                response.headers['Expires']='0'
                return response
            except Exception:
                app.logger.exception('Authorized R2 media could not be signed')
                return ('Media unavailable',503)

        target_dir='uploads'
        if not os.path.exists(os.path.join('uploads',filename)):
            demo_file=os.path.join('static','demo',filename)
            if os.path.exists(demo_file):
                target_dir=os.path.join('static','demo')
        return send_from_directory(target_dir,filename)

    @app.route('/healthz')
    def healthz():
        try:
            row=fetch_one('SELECT 1 ok')
            return jsonify(status='ok',database=bool(row and row['ok']==1))
        except Exception:
            return jsonify(status='degraded',database=False),503

    @app.route('/readyz')
    def readyz():
        import os
        db_ok=False; ai_ok=None; ai_detail='local'
        try:
            row=fetch_one('SELECT 1 ok'); db_ok=bool(row and row['ok']==1)
        except Exception:
            db_ok=False
        try:
            from safety.remote_client import enabled,health
            if enabled():
                ai=health();ai_ok=bool(ai.get('ok'));ai_detail='remote'
            else:
                ai_ok=True;ai_detail='local'
        except Exception:
            ai_ok=False;ai_detail='remote_unavailable'
        from mailg.send_email import get_mail_status
        mail_status = get_mail_status()
        mail_ok = bool(mail_status.get('ok'))
        mail_mode = mail_status.get('mail_mode', 'not_configured')
        strict_prod = os.getenv('STRICT_PRODUCTION_PREFLIGHT', '').strip().lower() in {'1', 'true', 'yes'}
        mail_ready = mail_status.get('is_production_ready') if strict_prod else mail_ok
        ok = db_ok and bool(ai_ok) and bool(mail_ready)
        return jsonify(status='ready' if ok else 'degraded',database=db_ok,ai=ai_ok,ai_mode=ai_detail,mail=mail_ok,mail_mode=mail_mode),(200 if ok else 503)

    @app.after_request
    def security_headers(response):
        refs=getattr(g,'r2_delete_refs',[]) if request.method=='POST' and response.status_code<400 else []
        if refs:
            try:
                from services.object_storage import delete_reference
                for ref in refs:delete_reference(ref)
            except Exception:
                app.logger.exception('R2 object cleanup failed after successful media deletion')

        if request.path.startswith('/static/'):
            response.headers['Cache-Control'] = 'public, max-age=604800, immutable'
        elif request.path.startswith('/uploads/'):
            response.headers['Cache-Control'] = 'private, no-store, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        response.headers.setdefault('X-Content-Type-Options','nosniff')
        response.headers.setdefault('X-Frame-Options','DENY')
        response.headers.setdefault('Referrer-Policy','same-origin')
        response.headers.setdefault('Permissions-Policy','camera=(self), microphone=(), geolocation=()')
        # Allow media delivery from Cloudflare R2 (*.r2.cloudflarestorage.com)
        try:
            from services.object_storage import normalize_r2_origin
            r2_origin = normalize_r2_origin()
        except Exception:
            r2_origin = ''
        img_src = "'self' data: blob:" + (f' {r2_origin}' if r2_origin else '')
        media_src = "'self' blob:" + (f' {r2_origin}' if r2_origin else '')
        response.headers.setdefault('Content-Security-Policy', f"default-src 'self'; img-src {img_src}; media-src {media_src}; font-src 'self' https://fonts.gstatic.com data:; script-src 'self'; object-src 'none'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        if request.is_secure:response.headers.setdefault('Strict-Transport-Security','max-age=31536000; includeSubDomains')
        return response

    @app.context_processor
    def ui_context():
        uid=session.get('user_id');lang=session.get('language') or (language_for_user(uid) if uid else 'EN')
        if uid:session['language']=lang
        ctrls = session.get('_ctrls') if session.get('role') == 'CHILD' else None
        if ctrls is None and uid and session.get('role') == 'CHILD':
            ctrls = controls_for_child(uid)
            session['_ctrls'] = ctrls
        avatar = session.get('_avatar') if session.get('role') == 'CHILD' else None
        if avatar is None and uid and session.get('role') == 'CHILD':
            prow = fetch_one('SELECT profile_picture FROM child_profiles WHERE child_id=%s', (uid,))
            avatar = (prow or {}).get('profile_picture') or 'uploads/profile_pictures/download.webp'
            session['_avatar'] = avatar
        activity_count = 0
        if uid and session.get('role') == 'CHILD':
            try:
                pending_reqs = fetch_one('SELECT COUNT(*) n FROM followers WHERE following_child_id=%s AND approved=FALSE', (uid,))
                unread_notifs = fetch_one('SELECT COUNT(*) n FROM notifications WHERE user_id=%s AND is_read=FALSE', (uid,))
                activity_count = int((pending_reqs or {}).get('n', 0)) + int((unread_notifs or {}).get('n', 0))
            except Exception:
                activity_count = 0
        return {'t':lambda key:tr(lang,key),'ui_language':lang,'ui_languages':LANGUAGES,'child_controls':ctrls,'child_effective_categories':effective_categories(uid) if uid and session.get('role')=='CHILD' else [],'nav_avatar':avatar,'unread_activity_count':activity_count}

    @app.errorhandler(413)
    def too_large(_):return jsonify(error='upload too large'),413

    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith('/api/') or 'application/json' in request.headers.get('Accept', ''):
            return jsonify(error='Not Found', path=request.path), 404
        return render_template('404.html'), 404

    @app.errorhandler(500)
    def internal_error(e):
        if request.path.startswith('/api/') or 'application/json' in request.headers.get('Accept', ''):
            return jsonify(error='Internal Server Error'), 500
        return render_template('500.html'), 500
    return app


app=create_app()
if __name__=='__main__':app.run(host='0.0.0.0',port=5000,debug=False)
