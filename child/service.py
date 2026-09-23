from datetime import date
from database.connection import fetch_one,fetch_all,execute
from services.request_cache import memo as _req_memo

def profile_exists(cid):return bool(fetch_one('SELECT 1 FROM child_profiles WHERE child_id=%s',(cid,)))
def get_child_profile(cid):return fetch_one('SELECT * FROM child_profiles WHERE child_id=%s',(cid,))
def create_child_profile(cid,form):
    """Create/update child-editable public profile fields.

    School/class/location/DOB are parent-managed identity context because they
    influence child discovery. Child profile edits must never be able to forge
    that relationship context. Parent provisioning writes those fields directly.
    """
    m=fetch_one("""SELECT parent_id FROM parent_child_map
                   WHERE child_id=%s AND approved=TRUE AND approval_status='APPROVED'
                   ORDER BY map_id LIMIT 1""",(cid,))
    execute(
        """INSERT INTO child_profiles(child_id,parent_id,full_name,bio)
           VALUES(%s,%s,%s,%s)
           ON CONFLICT(child_id) DO UPDATE SET
             full_name=EXCLUDED.full_name,
             bio=EXCLUDED.bio,
             updated_at=NOW()""",
        (cid,(m or {}).get('parent_id'),form.get('full_name','').strip(),form.get('bio')),
    )

def is_following(a,b):
    """Friendship is symmetric and active only after both parent approvals."""
    return bool(fetch_one('''SELECT 1 FROM followers WHERE approved=TRUE AND approval_stage='ACTIVE'
        AND ((child_id=%s AND following_child_id=%s) OR (child_id=%s AND following_child_id=%s)) LIMIT 1''',(a,b,b,a)))

def is_follow_pending(a,b):
    return bool(fetch_one('''SELECT 1 FROM followers WHERE approved=FALSE
        AND ((child_id=%s AND following_child_id=%s) OR (child_id=%s AND following_child_id=%s)) LIMIT 1''',(a,b,b,a)))

def follow_child(a,b):
    execute("""INSERT INTO followers(child_id,following_child_id,approved,approval_stage)
        VALUES(%s,%s,FALSE,'REQUESTED') ON CONFLICT(child_id,following_child_id) DO NOTHING""",(a,b))

def unfollow_child(a,b):
    execute('DELETE FROM followers WHERE (child_id=%s AND following_child_id=%s) OR (child_id=%s AND following_child_id=%s)',(a,b,b,a))


def discoverable_child_ids(cid):
    """Return minors the viewer may discover, fresh on every HTTP request.

    Discovery stays limited to legitimate relationship context:
    - same verified parent/family mapping;
    - same school AND same class;
    - an already ACTIVE friendship;
    - a pending parent-mediated friendship request; or
    - a friend-of-an-ACTIVE-friend.

    The expensive relationship query is memoized only inside the current
    request. Cross-request TTL caching is intentionally forbidden because a
    block, unfriend, parent-approval change, or profile-context change must
    affect a child on the very next request.
    """
    try:
        viewer_id = int(cid)
    except (TypeError, ValueError):
        return []
    ids = _req_memo(
        ("discoverable_child_ids", viewer_id),
        lambda: tuple(_discoverable_child_ids_uncached(viewer_id)),
    )
    return list(ids)


def _discoverable_child_ids_uncached(cid):
    rows=fetch_all('''WITH viewer AS (
          SELECT cp.school_name,cp.current_class,pcm.parent_id
          FROM child_profiles cp
          LEFT JOIN parent_child_map pcm ON pcm.child_id=cp.child_id
            AND pcm.approved=TRUE AND pcm.approval_status='APPROVED'
          WHERE cp.child_id=%s LIMIT 1
        ), approved_friends AS (
          SELECT following_child_id friend_id FROM followers
            WHERE child_id=%s AND approved=TRUE AND approval_stage='ACTIVE'
          UNION
          SELECT child_id FROM followers
            WHERE following_child_id=%s AND approved=TRUE AND approval_stage='ACTIVE'
        ), pending_peers AS (
          SELECT following_child_id peer_id FROM followers
            WHERE child_id=%s AND approved=FALSE
              AND approval_stage IN ('REQUESTED','SENDER_PARENT_APPROVED','RECEIVER_PARENT_PENDING')
          UNION
          SELECT child_id FROM followers
            WHERE following_child_id=%s AND approved=FALSE
              AND approval_stage IN ('REQUESTED','SENDER_PARENT_APPROVED','RECEIVER_PARENT_PENDING')
        ), network AS (
          SELECT DISTINCT CASE WHEN f.child_id=af.friend_id THEN f.following_child_id ELSE f.child_id END candidate_id
          FROM approved_friends af
          JOIN followers f ON f.approved=TRUE AND f.approval_stage='ACTIVE'
             AND (f.child_id=af.friend_id OR f.following_child_id=af.friend_id)
        )
        SELECT DISTINCT u.user_id
        FROM users u
        JOIN child_profiles cp ON cp.child_id=u.user_id
        LEFT JOIN parent_child_map pcm ON pcm.child_id=u.user_id
          AND pcm.approved=TRUE AND pcm.approval_status='APPROVED'
        WHERE u.role='CHILD' AND u.account_status='ACTIVE' AND u.user_id<>%s
          AND u.user_id NOT IN (
             SELECT blocked_id FROM blocked_users WHERE blocker_id=%s
             UNION SELECT blocker_id FROM blocked_users WHERE blocked_id=%s
             UNION SELECT muted_id FROM muted_users WHERE muter_id=%s
          )
          AND (
             (pcm.parent_id=(SELECT parent_id FROM viewer LIMIT 1) AND pcm.parent_id IS NOT NULL)
             OR (
                COALESCE(TRIM(cp.school_name),'')<>''
                AND COALESCE(TRIM(cp.current_class),'')<>''
                AND TRIM(LOWER(cp.school_name))=TRIM(LOWER(COALESCE((SELECT school_name FROM viewer LIMIT 1),'')))
                AND TRIM(LOWER(cp.current_class))=TRIM(LOWER(COALESCE((SELECT current_class FROM viewer LIMIT 1),'')))
             )
             OR u.user_id IN (SELECT friend_id FROM approved_friends)
             OR u.user_id IN (SELECT peer_id FROM pending_peers)
             OR u.user_id IN (SELECT candidate_id FROM network WHERE candidate_id<>%s)
          )''',(cid,cid,cid,cid,cid,cid,cid,cid,cid,cid))
    return [int(r['user_id']) for r in rows]


def can_discover_child(viewer_id,target_id):
    if viewer_id==target_id:return True
    try:target_id=int(target_id)
    except (TypeError,ValueError):return False
    return target_id in set(discoverable_child_ids(viewer_id))


def discoverable_children(cid,search_term=None,limit=30):
    ids=discoverable_child_ids(cid)
    if not ids:return []
    try:limit=max(1,min(int(limit),50))
    except (TypeError,ValueError):limit=30
    term=(search_term or '').strip();pattern=f"%{term}%"
    return fetch_all('''WITH viewer AS (
          SELECT cp.school_name,cp.current_class,pcm.parent_id
          FROM child_profiles cp LEFT JOIN parent_child_map pcm ON pcm.child_id=cp.child_id
            AND pcm.approved=TRUE AND pcm.approval_status='APPROVED'
          WHERE cp.child_id=%s LIMIT 1
        )
        SELECT u.user_id,u.full_name,u.username,cp.profile_picture,
          CASE
            WHEN pcm.parent_id=(SELECT parent_id FROM viewer LIMIT 1) AND pcm.parent_id IS NOT NULL THEN 'Family'
            WHEN EXISTS(SELECT 1 FROM followers f WHERE f.approved=TRUE AND f.approval_stage='ACTIVE'
                        AND ((f.child_id=%s AND f.following_child_id=u.user_id) OR (f.child_id=u.user_id AND f.following_child_id=%s))) THEN 'Friend'
            WHEN EXISTS(SELECT 1 FROM followers f WHERE f.approved=FALSE
                        AND ((f.child_id=%s AND f.following_child_id=u.user_id) OR (f.child_id=u.user_id AND f.following_child_id=%s))) THEN 'Pending parent approval'
            WHEN COALESCE(TRIM(cp.school_name),'')<>'' AND COALESCE(TRIM(cp.current_class),'')<>''
                 AND TRIM(LOWER(cp.school_name))=TRIM(LOWER(COALESCE((SELECT school_name FROM viewer LIMIT 1),'')))
                 AND TRIM(LOWER(cp.current_class))=TRIM(LOWER(COALESCE((SELECT current_class FROM viewer LIMIT 1),''))) THEN 'Same class'
            ELSE 'Approved friend network'
          END AS recommendation_reason
        FROM users u
        JOIN child_profiles cp ON cp.child_id=u.user_id
        LEFT JOIN parent_child_map pcm ON pcm.child_id=u.user_id
          AND pcm.approved=TRUE AND pcm.approval_status='APPROVED'
        WHERE u.user_id=ANY(%s)
          AND (%s='' OR u.full_name ILIKE %s OR u.username ILIKE %s)
        ORDER BY CASE
            WHEN pcm.parent_id=(SELECT parent_id FROM viewer LIMIT 1) AND pcm.parent_id IS NOT NULL THEN 0
            WHEN EXISTS(SELECT 1 FROM followers f WHERE f.approved=TRUE AND f.approval_stage='ACTIVE'
                        AND ((f.child_id=%s AND f.following_child_id=u.user_id) OR (f.child_id=u.user_id AND f.following_child_id=%s))) THEN 1
            WHEN COALESCE(TRIM(cp.school_name),'')<>'' AND COALESCE(TRIM(cp.current_class),'')<>''
                 AND TRIM(LOWER(cp.school_name))=TRIM(LOWER(COALESCE((SELECT school_name FROM viewer LIMIT 1),'')))
                 AND TRIM(LOWER(cp.current_class))=TRIM(LOWER(COALESCE((SELECT current_class FROM viewer LIMIT 1),''))) THEN 2
            ELSE 3 END,
            u.full_name,u.user_id
        LIMIT %s''',(cid,cid,cid,cid,cid,ids,term,pattern,pattern,cid,cid,limit))


def get_random_children(cid):return discoverable_children(cid,None,30)

def counts(cid):
    friends=(fetch_one("""SELECT COUNT(DISTINCT CASE WHEN child_id=%s THEN following_child_id ELSE child_id END) n
        FROM followers WHERE approved=TRUE AND approval_stage='ACTIVE' AND (child_id=%s OR following_child_id=%s)""",(cid,cid,cid)) or {'n':0})['n']
    return {'posts':fetch_one("SELECT COUNT(*) n FROM posts WHERE child_id=%s AND is_story=FALSE AND moderation_status='ALLOWED' AND is_safe=TRUE",(cid,))['n'],'followers':friends,'following':friends}

def replace_profile_tags(cid,skills,interests,ambitions):
    # Keep SQL identifiers static. Values remain parameterized below.
    execute('DELETE FROM child_skills WHERE child_id=%s',(cid,))
    execute('DELETE FROM child_interests WHERE child_id=%s',(cid,))
    execute('DELETE FROM child_ambitions WHERE child_id=%s',(cid,))
    for value in [x.strip() for x in skills if x.strip()]:execute('INSERT INTO child_skills(child_id,skill_name,approved) VALUES(%s,%s,FALSE)',(cid,value))
    for value in [x.strip() for x in interests if x.strip()]:execute('INSERT INTO child_interests(child_id,interest_name,approved) VALUES(%s,%s,FALSE)',(cid,value))
    for value in [x.strip() for x in ambitions if x.strip()]:execute('INSERT INTO child_ambitions(child_id,ambition_name,approved) VALUES(%s,%s,FALSE)',(cid,value))

def recommended_posts(cid,limit=30,offset=0):
    from services.recommendation import personalized_posts
    return personalized_posts(cid,limit,offset)
