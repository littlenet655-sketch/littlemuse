from functools import wraps
from flask import session, redirect, jsonify, request
from database.connection import fetch_one
from urllib.parse import urlencode


def _deny():
    if request.path.startswith('/api/'):
        return jsonify(error='unauthorized'), 401
    if request.path.startswith('/parent/'):
        return redirect('/login/?' + urlencode({'mode': 'parent', 'next': request.full_path.rstrip('?')}))
    return redirect('/login/')


def _inactive(role):
    session.clear()
    if request.path.startswith('/api/') or request.is_json:
        return jsonify(error='account_inactive'), 403
    mode='parent' if role=='PARENT' else ('kids' if role=='CHILD' else 'admin')
    return redirect(f'/login/?mode={mode}&error=This+account+is+inactive+or+suspended')


def login_required(fn):
    @wraps(fn)
    def inner(*a,**kw):
        uid=session.get('user_id')
        if not uid:return _deny()
        role=session.get('role')
        if role in {'CHILD','PARENT','ADMIN'}:
            user=fetch_one('SELECT account_status,role FROM users WHERE user_id=%s',(uid,))
            if not user or user.get('role')!=role or user.get('account_status')!='ACTIVE':
                return _inactive(role)
        return fn(*a,**kw)
    return inner


def role_required(role):
    def deco(fn):
        @wraps(fn)
        def inner(*a,**kw):
            uid=session.get('user_id')
            if not uid or session.get('role')!=role:return _deny()

            # The usage heartbeat is a technical close/restart signal and exposes
            # no child content. Keep it DB-status-exempt so it can close an old
            # usage segment even during onboarding/test contexts. Every normal
            # CHILD/PARENT/ADMIN surface below rechecks account_status live.
            technical_heartbeat=(role=='CHILD' and request.path=='/api/usage/heartbeat/')
            if not technical_heartbeat:
                user=fetch_one('SELECT account_status,role FROM users WHERE user_id=%s',(uid,))
                if not user or user.get('role')!=role or user.get('account_status')!='ACTIVE':
                    return _inactive(role)

            if role=='CHILD':
                # Browser routes use the same authoritative parent pause,
                # quiet-hour and screen-time rules as mobile routes. Previously
                # the older /chat, /send-message, /feed and /upload paths only
                # checked login status and could bypass the parent's lock.
                # Keep the informational locked-screen routes and technical
                # usage heartbeat available to an otherwise authenticated child.
                unlocked_info_paths = {
                    '/time-limit-reached/', '/quiet-hours/',
                    '/api/time-remaining/', '/api/usage/heartbeat/',
                }
                child_path = request.path
                if not technical_heartbeat and child_path not in unlocked_info_paths:
                    from services.social import child_surface_open
                    chat_paths = (
                        '/messages/', '/chat/', '/send-message/',
                        '/send-media/', '/share-post/', '/api/chat/',
                        '/api/share-post/',
                    )
                    chat_feature = 'messaging' if child_path.startswith(chat_paths) else None
                    if not child_surface_open(uid, chat_feature):
                        if request.path.startswith('/api/') or request.is_json or request.method != 'GET':
                            return jsonify(error='child_access_locked', gate='parent_controls'), 423
                        return redirect('/time-limit-reached/')

                discover_paths=(
                    '/discover/','/api/discover/','/api/search/suggestions/',
                    '/child/view-profile/','/follow/','/recommended/'
                )
                if request.path.startswith(discover_paths):
                    from services.controls import feature_allowed
                    if not feature_allowed(uid,'discover'):
                        if request.path.startswith('/api/') or request.is_json or request.method!='GET':
                            return jsonify(error='disabled_by_parent',feature='discover'),403
                        return redirect('/child/dashboard/')

                if request.method=='POST' and request.path.startswith('/api/edit-story-caption/'):
                    from safety.pii_service import scan_pii
                    data=request.get_json(silent=True) or {}
                    if scan_pii((data.get('caption') or '').strip()).get('detected'):
                        return jsonify(ok=False,error='Personal contact information cannot be shared in story captions.'),400

            if role=='PARENT':
                if request.path.rstrip('/')=='/parent/quick-approve-child':
                    return ('Legacy quick approval is disabled. Complete guardian verification.',410)
                if request.method=='GET' and request.path.startswith('/parent/confirm-child/'):
                    return ('Legacy email-only child activation is disabled. Use verified Parent Mode.',410)

            return fn(*a,**kw)
        return inner
    return deco


child_required=role_required('CHILD')
parent_required=role_required('PARENT')
admin_required=role_required('ADMIN')
