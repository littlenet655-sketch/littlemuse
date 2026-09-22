from database.connection import fetch_all, fetch_one, execute
from services.controls import effective_categories, controls_for_child, feature_allowed, quiet_hours_state


def _age_group(viewer_id):
    row=fetch_one('SELECT age,date_of_birth FROM child_profiles WHERE child_id=%s',(viewer_id,)) or {}
    age=row.get('age')
    if not age and row.get('date_of_birth'):
        from datetime import date
        d=row['date_of_birth'];today=date.today();age=today.year-d.year-((today.month,today.day)<(d.month,d.day))
    if not age:
        u=fetch_one('SELECT age,dob FROM users WHERE user_id=%s',(viewer_id,)) or {};age=u.get('age')
    try: age=int(age)
    except (TypeError,ValueError): return None
    if age<=8:return '6-8'
    if age<=11:return '9-11'
    if age<=13:return '12-13'
    return '14-18'


def child_surface_open(viewer_id, feature=None):
    """Fail closed for child-facing HTTP/media surfaces.

    Quiet-hours, screen-time and mandatory-quiz state are request-time controls.
    Background policy/unit evaluation has no browser session to lock and continues
    to use the canonical content/friend/category SQL rules instead.
    """
    try:
        from flask import has_request_context
        if not has_request_context():
            return True
    except ImportError:
        return True

    user=fetch_one("SELECT account_status,role FROM users WHERE user_id=%s",(viewer_id,))
    if not user or user.get('role')!='CHILD' or user.get('account_status')!='ACTIVE':return False
    if feature and not feature_allowed(viewer_id,feature):return False
    try:
        if quiet_hours_state(viewer_id).get('active'):return False
        from services.usage import lock_state
        locked,_=lock_state(viewer_id)
        if locked:return False
        from quiz.service import needs_onboarding_quiz,quiz_due
        if needs_onboarding_quiz(viewer_id) or quiz_due(viewer_id):return False
    except Exception:
        return False
    return True


def can_interact(a,b):
    if a==b:return False
    try:
        from flask import has_request_context,request,session
        if has_request_context() and request.path.startswith('/uploads/') and session.get('role')=='CHILD':
            current=int(session.get('user_id') or 0)
            if current in {int(a),int(b)} and not child_surface_open(current,'messaging'):return False
    except Exception:return False
    blocked=fetch_one('SELECT 1 FROM blocked_users WHERE (blocker_id=%s AND blocked_id=%s) OR (blocker_id=%s AND blocked_id=%s)',(a,b,b,a))
    if blocked:return False
    return bool(fetch_one('''SELECT 1 FROM followers WHERE approved=TRUE AND approval_stage='ACTIVE'
      AND ((child_id=%s AND following_child_id=%s) OR (child_id=%s AND following_child_id=%s)) LIMIT 1''',(a,b,b,a)))


def visible_posts(viewer_id, reels=False, limit=20, offset=0):
    controls=controls_for_child(viewer_id)
    if reels and not controls.get('allow_reels',True):return []
    cats=effective_categories(viewer_id);age_group=_age_group(viewer_id)
    return fetch_all('''SELECT p.*,u.full_name,cp.profile_picture,
      (SELECT COUNT(*) FROM likes l WHERE l.post_id=p.post_id) likes,
      (SELECT COUNT(*) FROM comments c WHERE c.post_id=p.post_id AND c.moderation_status='ALLOWED') comments_count
      FROM posts p JOIN users u ON u.user_id=p.child_id LEFT JOIN child_profiles cp ON cp.child_id=p.child_id
      WHERE ((p.moderation_status='ALLOWED' AND p.is_safe=TRUE) OR (p.child_id=%s AND p.moderation_status='REVIEW')) AND p.is_story=FALSE AND p.is_reel=%s
        AND p.content_category = ANY(%s)
        AND (%s IS NULL OR p.audience_age_group='ALL' OR p.audience_age_group=%s)
        AND (p.child_id=%s OR p.child_id IN (SELECT following_child_id FROM followers WHERE child_id=%s AND approved=TRUE AND approval_stage='ACTIVE'))
        AND p.child_id NOT IN (
          SELECT blocked_id FROM blocked_users WHERE blocker_id=%s
          UNION SELECT blocker_id FROM blocked_users WHERE blocked_id=%s
          UNION SELECT muted_id FROM muted_users WHERE muter_id=%s)
      ORDER BY CASE WHEN p.content_category IN (
          SELECT skill_name FROM child_skills WHERE child_id=%s AND approved=TRUE
          UNION SELECT interest_name FROM child_interests WHERE child_id=%s AND approved=TRUE
          UNION SELECT ambition_name FROM child_ambitions WHERE child_id=%s AND approved=TRUE) THEN 0 ELSE 1 END, p.created_at DESC
      LIMIT %s OFFSET %s''',
      (viewer_id,reels,cats,age_group,age_group,viewer_id,viewer_id,viewer_id,viewer_id,viewer_id,viewer_id,viewer_id,viewer_id,limit,offset))


def discoverable_posts(viewer_id, reels=False, limit=30, offset=0):
    controls = controls_for_child(viewer_id)
    feature = 'allow_reels' if reels else 'allow_discover'
    if not controls.get(feature, True):
        return []
    from child.service import discoverable_child_ids
    allowed_child_ids = discoverable_child_ids(viewer_id)
    if not allowed_child_ids:
        return []
    cats = effective_categories(viewer_id)
    age_group = _age_group(viewer_id)
    return fetch_all('''SELECT p.*, u.full_name, u.username, cp.profile_picture,
      (SELECT COUNT(*) FROM likes l WHERE l.post_id=p.post_id) likes,
      (SELECT COUNT(*) FROM comments c WHERE c.post_id=p.post_id AND c.moderation_status='ALLOWED') comments_count
      FROM posts p JOIN users u ON u.user_id=p.child_id LEFT JOIN child_profiles cp ON cp.child_id=p.child_id
      WHERE p.moderation_status='ALLOWED' AND p.is_safe=TRUE AND p.is_story=FALSE AND p.is_reel=%s
        AND p.content_category = ANY(%s)
        AND (%s IS NULL OR p.audience_age_group='ALL' OR p.audience_age_group=%s)
         AND p.child_id = ANY(%s::int[])
        AND p.child_id NOT IN (
          SELECT blocked_id FROM blocked_users WHERE blocker_id=%s
          UNION SELECT blocker_id FROM blocked_users WHERE blocked_id=%s
          UNION SELECT muted_id FROM muted_users WHERE muter_id=%s)
      ORDER BY p.created_at DESC
      LIMIT %s OFFSET %s''',
       (reels, cats, age_group, age_group, allowed_child_ids, viewer_id, viewer_id, viewer_id, limit, offset))


def active_stories(viewer_id):
    controls=controls_for_child(viewer_id)
    if not controls.get('allow_stories',True):return []
    cats=effective_categories(viewer_id);age_group=_age_group(viewer_id)
    return fetch_all('''SELECT p.*,u.full_name,cp.profile_picture,
        EXISTS(SELECT 1 FROM story_views sv WHERE sv.post_id=p.post_id AND sv.child_id=%s) AS viewed
        FROM posts p JOIN users u ON u.user_id=p.child_id
        LEFT JOIN child_profiles cp ON cp.child_id=p.child_id
        WHERE p.is_story=TRUE AND p.is_safe=TRUE AND p.moderation_status='ALLOWED'
          AND p.created_at>NOW()-INTERVAL '24 hours'
          AND p.content_category = ANY(%s)
          AND (%s IS NULL OR p.audience_age_group='ALL' OR p.audience_age_group=%s)
          AND (p.child_id=%s OR p.child_id IN (
              SELECT following_child_id FROM followers WHERE child_id=%s AND approved=TRUE AND approval_stage='ACTIVE'
          ))
          AND p.child_id NOT IN (
              SELECT blocked_id FROM blocked_users WHERE blocker_id=%s
              UNION SELECT blocker_id FROM blocked_users WHERE blocked_id=%s
              UNION SELECT muted_id FROM muted_users WHERE muter_id=%s
          )
        ORDER BY CASE WHEN p.child_id=%s THEN 0 ELSE 1 END, p.child_id, p.created_at ASC''',
        (viewer_id,cats,age_group,age_group,viewer_id,viewer_id,viewer_id,viewer_id,viewer_id,viewer_id))


def story_visible_to(viewer_id,post_id):
    if not child_surface_open(viewer_id,'stories'):return None
    cats=effective_categories(viewer_id);age_group=_age_group(viewer_id)
    return fetch_one('''SELECT p.*,u.full_name,cp.profile_picture FROM posts p
        JOIN users u ON u.user_id=p.child_id LEFT JOIN child_profiles cp ON cp.child_id=p.child_id
        WHERE p.post_id=%s AND p.is_story=TRUE AND p.is_safe=TRUE AND p.moderation_status='ALLOWED'
          AND p.created_at>NOW()-INTERVAL '24 hours' AND p.content_category = ANY(%s)
          AND (%s IS NULL OR p.audience_age_group='ALL' OR p.audience_age_group=%s)
          AND (p.child_id=%s OR EXISTS(SELECT 1 FROM followers f WHERE f.child_id=%s AND f.following_child_id=p.child_id AND f.approved=TRUE AND f.approval_stage='ACTIVE'))
          AND NOT EXISTS(SELECT 1 FROM blocked_users b WHERE (b.blocker_id=%s AND b.blocked_id=p.child_id) OR (b.blocker_id=p.child_id AND b.blocked_id=%s))
          AND NOT EXISTS(SELECT 1 FROM muted_users m WHERE m.muter_id=%s AND m.muted_id=p.child_id)''',
        (post_id,cats,age_group,age_group,viewer_id,viewer_id,viewer_id,viewer_id,viewer_id))


def notify(user_id,kind,message,url=None,actor=None):
    if str(kind).upper()=='FOLLOW_REQUEST':return None
    execute('INSERT INTO notifications(user_id,actor_id,notification_type,message,target_url) VALUES(%s,%s,%s,%s,%s)',(user_id,actor,kind,message,url))


def parent_notify(child_id,kind,message,url=None):
    parents=fetch_all('''SELECT DISTINCT pcm.parent_id,u.email,u.full_name FROM parent_child_map pcm
        JOIN users u ON u.user_id=pcm.parent_id
        WHERE pcm.child_id=%s
          AND pcm.parent_id IS NOT NULL
          AND pcm.approved=TRUE
          AND pcm.approval_status='APPROVED'
          AND u.role='PARENT'
          AND u.account_status='ACTIVE' ''',(child_id,))
    for parent in parents:
        execute('''INSERT INTO parent_notifications(parent_id,child_id,notification_type,notification_message,target_url)
          VALUES(%s,%s,%s,%s,%s)''',(parent['parent_id'],child_id,kind,message,url))
    safety_kind=('BLOCK' in str(kind).upper()) or ('REVIEW' in str(kind).upper())
    if safety_kind and parents:
        try:
            from mailg.send_email import send_email
            from config import Config
            target=f"{Config.BASE_URL.rstrip('/')}{url or '/parent/notifications/'}"
            for parent in parents:send_email(parent['email'],'LittleNet safety alert',f"<h2>LittleNet safety alert</h2><p>{message}</p><p><a href='{target}'>Open Parent Mode</a></p>")
        except Exception:pass


def post_visible_to(viewer_id,post_id):
    if not child_surface_open(viewer_id):return None
    cats=effective_categories(viewer_id);age_group=_age_group(viewer_id)
    post=fetch_one("""SELECT p.* FROM posts p WHERE p.post_id=%s AND (p.moderation_status='ALLOWED' OR (p.child_id=%s AND p.moderation_status='REVIEW')) AND p.is_safe=TRUE
      AND p.content_category = ANY(%s) AND (%s IS NULL OR p.audience_age_group='ALL' OR p.audience_age_group=%s)
      AND (p.child_id=%s OR EXISTS(SELECT 1 FROM followers f WHERE f.child_id=%s AND f.following_child_id=p.child_id AND f.approved=TRUE AND f.approval_stage='ACTIVE'))
      AND p.child_id NOT IN (
        SELECT blocked_id FROM blocked_users WHERE blocker_id=%s
        UNION SELECT blocker_id FROM blocked_users WHERE blocked_id=%s
        UNION SELECT muted_id FROM muted_users WHERE muter_id=%s)""",(post_id,viewer_id,cats,age_group,age_group,viewer_id,viewer_id,viewer_id,viewer_id,viewer_id))
    if not post:return None
    if post.get('is_reel') and not feature_allowed(viewer_id,'reels'):return None
    if post.get('is_story') and not feature_allowed(viewer_id,'stories'):return None
    return post


def visible_profile_posts(viewer_id,target_id,limit=60):
    if viewer_id == target_id:
        return fetch_all("""SELECT p.* FROM posts p WHERE p.child_id=%s AND p.is_story=FALSE
          AND ((p.moderation_status='ALLOWED' AND p.is_safe=TRUE) OR p.moderation_status='REVIEW')
          ORDER BY p.created_at DESC LIMIT %s""",(target_id,limit))
    rows=fetch_all("""SELECT p.* FROM posts p WHERE p.child_id=%s AND p.is_story=FALSE
      AND p.moderation_status='ALLOWED' AND p.is_safe=TRUE ORDER BY p.created_at DESC LIMIT %s""",(target_id,limit))
    return [p for p in rows if post_visible_to(viewer_id,p['post_id'])]


def is_post_shareable_to(post_id, sender_id, receiver_id):
    if not can_interact(sender_id, receiver_id):return False, "Both parents must approve this friendship before sharing or messaging."
    p_sender = post_visible_to(sender_id, post_id)
    if not p_sender:return False, "Post unavailable"
    if p_sender.get('moderation_status') != 'ALLOWED' or not p_sender.get('is_safe'):return False, "Post not approved for sharing"
    cats = effective_categories(receiver_id)
    if p_sender.get('content_category') not in cats:return False, "Post category restricted by recipient's parent controls"
    recip_age = _age_group(receiver_id);post_age = p_sender.get('audience_age_group')
    if post_age and post_age != 'ALL' and recip_age and post_age != recip_age:return False, "Post not suitable for recipient's age group"
    return True, "OK"
