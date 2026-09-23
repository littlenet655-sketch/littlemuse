from datetime import date
from database.connection import fetch_one, fetch_all, execute, get_db_connection

# Product-locked doom-scroll intervention. Parent Mode may make it MORE
# frequent, but never less frequent than the LittleNet safety default.
FEED_QUIZ_INTERVAL = 4

# ─── Age helpers ──────────────────────────────────────────────────────────────

def _age_from_profile_or_user(cid):
    """Return the best available child age without silently inventing one."""
    r = fetch_one(
        '''SELECT cp.date_of_birth, cp.age AS profile_age, u.age AS user_age
           FROM users u
           LEFT JOIN child_profiles cp ON cp.child_id=u.user_id
           WHERE u.user_id=%s''',
        (cid,)
    )
    if not r:
        return None
    dob = r.get('date_of_birth')
    if dob:
        t = date.today()
        return t.year - dob.year - ((t.month, t.day) < (dob.month, dob.day))
    for key in ('profile_age', 'user_age'):
        try:
            value = int(r.get(key))
            if 4 <= value <= 18:
                return value
        except (TypeError, ValueError):
            pass
    return None


def age_group(cid):
    """Map a child to the quiz/feed age bands used by LittleNet."""
    a = _age_from_profile_or_user(cid)
    if a is None:
        return '9-11'
    if a <= 8:
        return '6-8'
    if a <= 11:
        return '9-11'
    if a <= 13:
        return '12-13'
    return '14-18'


def learning_age_group(cid):
    return age_group(cid) or '9-11'


def needs_onboarding_quiz(cid, required_questions=2):
    """Gate normal Kids Mode on the short age-matched onboarding quiz."""
    created = fetch_one(
        "SELECT 1 FROM activity_logs WHERE child_id=%s AND activity_type='ACCOUNT_CREATED_BY_PARENT' LIMIT 1",
        (cid,)
    )
    if not created:
        return False
    row = fetch_one('SELECT COUNT(DISTINCT quiz_id) AS n FROM child_quiz_attempts WHERE child_id=%s', (cid,)) or {'n': 0}
    return int(row.get('n') or 0) < int(required_questions)

# ─── Classic quiz bank (used by quiz page) ────────────────────────────────────

def quizzes(cid, limit=5):
    """Return randomized unseen age-matched questions; strictly guarantees non-repeating for kids by dynamically generating new questions with K2 AI."""
    g = age_group(cid)
    if not g:
        return []
    limit = max(1, int(limit))
    rows = fetch_all(
        '''SELECT * FROM quizzes
           WHERE age_group=%s
             AND quiz_id NOT IN (
                 SELECT quiz_id FROM child_quiz_attempts WHERE child_id=%s
             )
           ORDER BY RANDOM() LIMIT %s''',
        (g, cid, limit)
    )
    if len(rows) < limit:
        needed = limit - len(rows)
        try:
            from quiz.learning_service import generate_and_insert_fresh_quizzes
            fresh = generate_and_insert_fresh_quizzes(age_group=g, needed=needed, child_id=cid)
            existing_ids = {r['quiz_id'] for r in rows}
            for f in fresh:
                if f['quiz_id'] not in existing_ids:
                    rows.append(f)
                    existing_ids.add(f['quiz_id'])
                    if len(rows) >= limit:
                        break
        except Exception as exc:
            pass

    # Strict zero-repetition guarantee: never return a question already in child_quiz_attempts for this child
    attempted_rows = fetch_all('SELECT quiz_id FROM child_quiz_attempts WHERE child_id=%s', (cid,))
    attempted_ids = {r['quiz_id'] for r in attempted_rows}
    return [r for r in rows if r['quiz_id'] not in attempted_ids]

# ─── Feed quiz — single unseen question injected between reels ────────────────

def next_feed_quiz(cid):
    """Return ONE unseen question, preferring personalized/adaptive material, cycling least-recently attempted when bank is exhausted."""
    g = age_group(cid)
    if not g:
        return None

    try:
        p_row = fetch_one('''
            SELECT q.*, p.pool_id FROM child_personalized_quiz_pool p
            JOIN quizzes q ON q.quiz_id = p.quiz_id
            WHERE p.child_id = %s AND p.served = FALSE
              AND q.age_group=%s
              AND q.quiz_id NOT IN (SELECT quiz_id FROM child_quiz_attempts WHERE child_id=%s)
            ORDER BY p.created_at ASC LIMIT 1
        ''', (cid, g, cid))
        if p_row:
            execute('UPDATE child_personalized_quiz_pool SET served=TRUE WHERE pool_id=%s', (p_row['pool_id'],))
            return p_row
    except Exception:
        pass

    from quiz.learning_service import get_child_difficulty_level, trigger_background_refill_if_needed, populate_child_personalized_pool
    diff = get_child_difficulty_level(cid)

    row = fetch_one(
        '''SELECT * FROM quizzes
           WHERE age_group=%s AND difficulty_level=%s
             AND quiz_id NOT IN (
                 SELECT quiz_id FROM child_quiz_attempts WHERE child_id=%s
             )
           ORDER BY RANDOM() LIMIT 1''',
        (g, diff, cid)
    )
    if not row:
        row = fetch_one(
            '''SELECT * FROM quizzes
               WHERE age_group=%s
                 AND quiz_id NOT IN (
                     SELECT quiz_id FROM child_quiz_attempts WHERE child_id=%s
                 )
               ORDER BY RANDOM() LIMIT 1''',
            (g, cid)
        )
    if not row:
        # Bank exhausted for this child! Generate fresh questions using K2 AI on the fly
        try:
            from quiz.learning_service import generate_and_insert_fresh_quizzes
            fresh = generate_and_insert_fresh_quizzes(age_group=g, needed=3, child_id=cid)
            if fresh:
                row = fresh[0]
        except Exception as exc:
            pass

    # Strictly guarantee: NEVER return a question already in child_quiz_attempts for this child
    if row:
        has_attempted = fetch_one('SELECT 1 FROM child_quiz_attempts WHERE child_id=%s AND quiz_id=%s', (cid, row['quiz_id']))
        if has_attempted:
            try:
                from quiz.learning_service import generate_and_insert_fresh_quizzes
                fresh = generate_and_insert_fresh_quizzes(age_group=g, needed=1, child_id=cid)
                row = fresh[0] if fresh else None
            except Exception:
                row = None

    try:
        trigger_background_refill_if_needed(g, cid)
        populate_child_personalized_pool(cid, g)
    except Exception:
        pass
    return row


def _unseen_count(cid, g):
    r = fetch_one(
        '''SELECT COUNT(*) AS c FROM quizzes
           WHERE age_group=%s
             AND quiz_id NOT IN (
                 SELECT quiz_id FROM child_quiz_attempts WHERE child_id=%s
             )''',
        (g, cid)
    )
    return int((r or {}).get('c', 0))

# ─── Server-persistent compulsory feed/reel gate ──────────────────────────────

def setting(cid):
    return fetch_one('SELECT * FROM parent_quiz_settings WHERE child_id=%s', (cid,))


def feed_quiz_interval(cid):
    """Return the server-authoritative view threshold for the next brain break.

    LittleNet default is 4.
    Parent may configure a MORE frequent intervention: 1, 2, 3, or 4.
    Never allow > 4 for a child. Child cannot disable it.
    """
    threshold = FEED_QUIZ_INTERVAL
    s = setting(cid)
    if s:
        raw_freq = s.get('quiz_frequency')
        if raw_freq is not None:
            try:
                freq = int(raw_freq)
                threshold = min(FEED_QUIZ_INTERVAL, max(1, freq))
            except (TypeError, ValueError):
                threshold = FEED_QUIZ_INTERVAL
    return threshold


def feed_quiz_state(cid):
    row = fetch_one(
        '''SELECT posts_seen,quiz_required,required_quiz_id,required_at,viewed_post_ids
           FROM child_quiz_progress WHERE child_id=%s''',
        (cid,)
    ) or {}
    return {
        'posts_seen': int(row.get('posts_seen') or 0),
        'required': bool(row.get('quiz_required')),
        'quiz_id': int(row['required_quiz_id']) if row.get('required_quiz_id') else None,
        'required_at': row.get('required_at'),
        'viewed_post_ids': list(row.get('viewed_post_ids') or []),
        'interval': feed_quiz_interval(cid),
    }


def record_feed_view(cid, post_id, source_type="POST"):
    """Atomically count one unique visible post/reel/curated item in the current quiz cycle.

    The client reports the concrete item id when it becomes substantially visible.
    Both Feed posts and Reels increment the SAME server-side view counter.
    Curated LittleNet content and social child content both count.
    PostgreSQL owns de-duplication and the latch. Once ``quiz_required`` is true,
    additional views cannot clear or postpone it; only ``reset`` after an accepted
    answer starts a new cycle.
    """
    stype = str(source_type or "POST").upper()
    try:
        clean_id = int(str(post_id).replace("CURATED:", "").replace("POST:", ""))
    except (TypeError, ValueError):
        return {'accepted': False, **feed_quiz_state(cid)}

    if stype == "CURATED" or str(post_id).startswith("CURATED:"):
        stype = "CURATED"
        visible = fetch_one(
            """SELECT content_id AS id FROM curated_content
               WHERE content_id=%s""",
            (clean_id,)
        )
        if not visible and clean_id <= 0:
            return {'accepted': False, **feed_quiz_state(cid)}
    else:
        stype = "POST"
        visible = fetch_one(
            """SELECT post_id AS id FROM posts
               WHERE post_id=%s AND moderation_status='ALLOWED' AND is_safe=TRUE AND is_story=FALSE""",
            (clean_id,)
        )
        if not visible:
            return {'accepted': False, **feed_quiz_state(cid)}

    threshold = feed_quiz_interval(cid)
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                '''INSERT INTO child_quiz_progress(child_id,posts_seen,quiz_required,viewed_post_ids)
                   VALUES(%s,0,FALSE,'[]'::jsonb) ON CONFLICT(child_id) DO NOTHING''',
                (cid,)
            )
            cur.execute(
                '''SELECT posts_seen,quiz_required,required_quiz_id,required_at,viewed_post_ids
                   FROM child_quiz_progress WHERE child_id=%s FOR UPDATE''',
                (cid,)
            )
            row = cur.fetchone() or {}
            if row.get('quiz_required'):
                conn.commit()
                return {
                    'accepted': False,
                    'posts_seen': int(row.get('posts_seen') or 0),
                    'required': True,
                    'quiz_id': int(row['required_quiz_id']) if row.get('required_quiz_id') else None,
                    'interval': threshold,
                }
            seen = [x for x in (row.get('viewed_post_ids') or [])]
            item_token = f"{stype}:{clean_id}"
            accepted = (post_id not in seen and item_token not in seen and clean_id not in seen)
            count = int(row.get('posts_seen') or 0)
            if accepted:
                seen.append(item_token)
                seen.append(clean_id)
                seen.append(post_id)
                count += 1
            required = count >= threshold
            cur.execute(
                '''UPDATE child_quiz_progress
                   SET posts_seen=%s,viewed_post_ids=%s::jsonb,
                       quiz_required=%s,
                       required_at=CASE WHEN %s THEN COALESCE(required_at,NOW()) ELSE required_at END,
                       last_updated=NOW()
                   WHERE child_id=%s''',
                (count, __import__('json').dumps(seen), required, required, cid)
            )
        conn.commit()
        return {
            'accepted': accepted,
            'posts_seen': count,
            'required': required,
            'quiz_id': None,
            'interval': threshold,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def required_feed_quiz(cid):
    """Return the exact latched quiz, assigning it once if the gate is pending."""
    state = feed_quiz_state(cid)
    if not state['required']:
        return None
    if state['quiz_id']:
        q = fetch_one('SELECT * FROM quizzes WHERE quiz_id=%s AND age_group=%s', (state['quiz_id'], age_group(cid)))
        if q:
            return q
        # Deleted/invalid assignment: clear only the assignment, never the latch.
        execute('UPDATE child_quiz_progress SET required_quiz_id=NULL,last_updated=NOW() WHERE child_id=%s', (cid,))

    q = next_feed_quiz(cid)
    if not q:
        return None
    execute(
        '''UPDATE child_quiz_progress SET required_quiz_id=%s,last_updated=NOW()
           WHERE child_id=%s AND quiz_required=TRUE AND required_quiz_id IS NULL''',
        (q['quiz_id'], cid)
    )
    state = feed_quiz_state(cid)
    if state['quiz_id'] and state['quiz_id'] != int(q['quiz_id']):
        return fetch_one('SELECT * FROM quizzes WHERE quiz_id=%s', (state['quiz_id'],))
    return q


def complete_required_feed_quiz(cid, quiz_id):
    """Clear the latch only when the submitted quiz matches the stored assignment."""
    state = feed_quiz_state(cid)
    if not state['required'] or not state['quiz_id']:
        return False
    try:
        if int(quiz_id) != int(state['quiz_id']):
            return False
    except (TypeError, ValueError):
        return False
    reset(cid)
    return True

# ─── Feed quiz answer submission ──────────────────────────────────────────────

def record_feed_answer(cid, quiz_id, selected_answer):
    """Record an age-authorized feed answer and award XP."""
    q = fetch_one('SELECT * FROM quizzes WHERE quiz_id=%s', (quiz_id,))
    if not q or q.get('age_group') != age_group(cid):
        return False, '', 0, ''
    is_correct = (str(selected_answer).strip() == str(q['correct_answer']).strip())
    execute(
        'INSERT INTO child_quiz_attempts(child_id,quiz_id,selected_answer,is_correct) VALUES(%s,%s,%s,%s)',
        (cid, quiz_id, selected_answer, is_correct)
    )
    xp = 10 if is_correct else 0
    if xp:
        execute(
            '''INSERT INTO child_xp(child_id, xp) VALUES(%s,%s)
               ON CONFLICT(child_id) DO UPDATE SET xp=child_xp.xp+EXCLUDED.xp, updated_at=NOW()''',
            (cid, xp)
        )

    if q.get('vocabulary_word') and q.get('language'):
        try:
            from quiz.learning_service import record_vocabulary_attempt
            record_vocabulary_attempt(cid, q['vocabulary_word'], q['language'], is_correct)
        except Exception:
            pass

    explanation = q.get('explanation') or ''
    return is_correct, q['correct_answer'], xp, explanation

# ─── Post-counter helpers ──────────────────────────────────────────────────────

def quiz_due(cid):
    # The PostgreSQL latch always wins. This makes refresh/new-tab/session reset
    # unable to postpone an already-required intervention.
    state = feed_quiz_state(cid)
    if state['required']:
        return True
    interval = feed_quiz_interval(cid)
    if state['posts_seen'] >= interval:
        execute(
            '''INSERT INTO child_quiz_progress(child_id,posts_seen,quiz_required,required_at)
               VALUES(%s,%s,TRUE,NOW())
               ON CONFLICT(child_id) DO UPDATE SET quiz_required=TRUE,required_at=COALESCE(child_quiz_progress.required_at,NOW()),last_updated=NOW()''',
            (cid, state['posts_seen'])
        )
        return True
    return False


def bump(cid):
    """Legacy compatibility hook; viewport post/reel IDs are authoritative now."""
    # Intentionally do not increment here. Feed/Reels routes call this helper on
    # page load, and counting page loads would let refreshes distort the safety
    # interval. ``record_feed_view`` is the only function allowed to add views.
    return feed_quiz_state(cid)


def reset(cid):
    execute(
        '''INSERT INTO child_quiz_progress(child_id,posts_seen,quiz_required,required_quiz_id,required_at,viewed_post_ids)
           VALUES(%s,0,FALSE,NULL,NULL,'[]'::jsonb)
           ON CONFLICT(child_id) DO UPDATE
             SET posts_seen=0,quiz_required=FALSE,required_quiz_id=NULL,required_at=NULL,
                 viewed_post_ids='[]'::jsonb,last_updated=NOW()''',
        (cid,)
    )

# ─── Learning challenges ──────────────────────────────────────────────────────

def learning_challenges(cid):
    g = learning_age_group(cid)
    if not g:
        return []
    return fetch_all(
        '''SELECT c.*,a.completed,a.points_awarded,a.completed_at
           FROM learning_challenges c
           LEFT JOIN learning_challenge_attempts a
             ON a.challenge_id=c.challenge_id AND a.child_id=%s
           WHERE c.age_group=%s AND c.active=TRUE
           ORDER BY a.completed NULLS FIRST, c.challenge_id''',
        (cid, g)
    )


def learning_points(cid):
    row = fetch_one(
        'SELECT COALESCE(SUM(points_awarded),0) points FROM learning_challenge_attempts WHERE child_id=%s',
        (cid,)
    )
    return int((row or {}).get('points', 0) or 0)
