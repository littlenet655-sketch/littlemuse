"""Verified-parent child provisioning for the locked LittleNet onboarding flow.

Sequence: verified ACTIVE parent -> validated child age -> child account -> mandatory
face enrollment -> mandatory age-matched onboarding quiz. The latter two gates are
enforced by auth/api.py before the child can reach normal Kids Mode screens.
"""
import uuid

from auth.service import hash_password
from database.connection import fetch_one, get_db_connection
from safety.policy import decide
from safety.text_service import check_text
from services.identity import validate_name, validate_username

MIN_CHILD_AGE = 6
MAX_CHILD_AGE = 16


def create_child_for_verified_parent(parent_id, form):
    parent = fetch_one(
        "SELECT user_id,full_name,email FROM users WHERE user_id=%s AND role='PARENT' AND account_status='ACTIVE'",
        (parent_id,),
    )
    if not parent:
        raise ValueError('A fully verified active Parent account is required.')

    username = (form.get('username') or '').strip()
    if not validate_username(username):
        raise ValueError('Child username must be 3-30 safe characters.')

    child_email = f"{username.lower()}@kids.littlenet.internal"
    existing_user = fetch_one(
        "SELECT user_id, username, email FROM users WHERE LOWER(username)=%s OR LOWER(email)=%s",
        (username.lower(), child_email.lower()),
    )
    if existing_user:
        raise ValueError('This username is already taken. Please choose another.')

    full_name = (form.get('full_name') or '').strip() or username.capitalize()
    if not validate_name(full_name):
        raise ValueError('Please enter a valid child name.')

    try:
        age = int(form.get('age'))
    except (TypeError, ValueError):
        raise ValueError('Enter the child age.')
    if not MIN_CHILD_AGE <= age <= MAX_CHILD_AGE:
        raise ValueError(
            f'Child age must be between {MIN_CHILD_AGE} and {MAX_CHILD_AGE}.'
        )

    password = form.get('password') or ''
    if len(password) < 8:
        raise ValueError('Child password must be at least 8 characters.')

    public_text = ' '.join(
        str(form.get(k, '') or '')
        for k in ('full_name', 'school_name', 'location', 'current_class', 'bio')
    )
    profile_decision = decide(check_text(public_text), 'STRICT')
    if profile_decision.action != 'ALLOW':
        raise ValueError('Child profile text could not be accepted under LittleNet safety rules.')

    try:
        limit = int(form.get('daily_limit') or 60)
    except (TypeError, ValueError):
        limit = 60
    if not 1 <= limit <= 1440:
        raise ValueError('Daily screen-time limit must be between 1 and 1440 minutes.')

    safety = (form.get('safety_level') or 'STRICT').upper()
    if safety not in {'STANDARD', 'STRICT', 'VERY_STRICT'}:
        safety = 'STRICT'

    allow_reels = form.get('allow_reels', '1') in ('1', 'on', 'true', True)
    allow_stories = form.get('allow_stories', '1') in ('1', 'on', 'true', True)
    allow_messaging = form.get('allow_messaging', '1') in ('1', 'on', 'true', True)
    allow_posting = form.get('allow_posting', '1') in ('1', 'on', 'true', True)
    allow_discover = form.get('allow_discover', '1') in ('1', 'on', 'true', True)
    educational_only = form.get('educational_only_feed', '0') in ('1', 'on', 'true', True)

    token = str(uuid.uuid4())
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO users(username,full_name,email,password_hash,role,age,account_status)
               VALUES(%s,%s,%s,%s,'CHILD',%s,'ACTIVE') RETURNING user_id""",
            (username, full_name, child_email, hash_password(password), age),
        )
        child_id = cur.fetchone()['user_id']
        cur.execute(
            """INSERT INTO parent_child_map(
                   child_id,parent_id,verified_parent_id,parent_name,parent_email,
                   approval_token,verification_token,approved,approved_at,
                   approval_status,is_token_used
               ) VALUES(%s,%s,%s,%s,%s,%s,%s,TRUE,NOW(),'APPROVED',TRUE)""",
            (child_id, parent_id, parent_id, parent['full_name'], parent['email'], token, token),
        )
        cur.execute(
            """INSERT INTO child_profiles(
                   child_id,parent_id,full_name,date_of_birth,age,school_name,
                   location,current_class,bio
               ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                child_id, parent_id, full_name, form.get('date_of_birth') or None,
                age, form.get('school_name'), form.get('location'),
                form.get('current_class'), form.get('bio') or "Hey! I'm on LittleNet 🌟",
            ),
        )
        cur.execute(
            "INSERT INTO parent_safety_settings(child_id,parent_id,safety_level) VALUES(%s,%s,%s)",
            (child_id, parent_id, safety),
        )
        cur.execute(
            "INSERT INTO child_time_limits(child_id,daily_limit_minutes,strict_mode) VALUES(%s,%s,%s)",
            (child_id, limit, form.get('strict_mode') != 'off'),
        )
        cur.execute(
            """INSERT INTO parent_control_settings(
                   child_id,parent_id,allow_reels,allow_stories,allow_messaging,
                   allow_posting,allow_discover,educational_only_feed
               ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                child_id, parent_id, allow_reels, allow_stories, allow_messaging,
                allow_posting, allow_discover, educational_only,
            ),
        )
        # Default doom-scroll intervention: mandatory age quiz after four viewed items.
        cur.execute(
            """INSERT INTO parent_quiz_settings(parent_id,child_id,quiz_frequency,mandatory_quiz)
               VALUES(%s,%s,4,TRUE)
               ON CONFLICT(child_id) DO UPDATE SET parent_id=EXCLUDED.parent_id""",
            (parent_id, child_id),
        )
        cur.execute(
            """INSERT INTO activity_logs(child_id,activity_type,activity_data)
               VALUES(%s,'ACCOUNT_CREATED_BY_PARENT',%s::jsonb)""",
            (child_id, '{"verified_parent":true,"face_enrollment_required":true,"onboarding_quiz_required":true}'),
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        err_msg = str(exc).lower()
        if "unique constraint" in err_msg or "duplicate key" in err_msg or "uniqueviolation" in err_msg:
            raise ValueError('This username is already taken. Please choose another.') from exc
        raise
    finally:
        conn.close()
    return child_id
