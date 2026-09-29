from database.connection import fetch_one, fetch_all, execute


def children(parent_id):
    """Return children linked to a currently active parent through an approved mapping."""
    return fetch_all('''
        SELECT DISTINCT u.user_id, u.username, u.full_name, u.age,
               u.account_status, u.parent_paused, u.demo_unlimited, cp.profile_picture
        FROM parent_child_map m
        JOIN users u ON u.user_id = m.child_id AND u.role='CHILD'
        JOIN users p ON p.user_id=%s AND p.role='PARENT' AND p.account_status='ACTIVE'
        LEFT JOIN child_profiles cp ON cp.child_id = u.user_id
        WHERE m.approved=TRUE
          AND m.approval_status='APPROVED'
          AND (m.parent_id=%s OR m.verified_parent_id=%s)
    ''', (parent_id, parent_id, parent_id))


def owns(parent_id, child_id):
    """Canonical authorization check for Parent Mode child access."""
    return bool(fetch_one('''
        SELECT 1
        FROM parent_child_map m
        JOIN users u ON u.user_id=m.child_id AND u.role='CHILD'
        JOIN users p ON p.user_id=%s AND p.role='PARENT' AND p.account_status='ACTIVE'
        WHERE m.child_id=%s
          AND m.approved=TRUE
          AND m.approval_status='APPROVED'
          AND (m.parent_id=%s OR m.verified_parent_id=%s)
        LIMIT 1
    ''', (parent_id, child_id, parent_id, parent_id)))


def pending_follows(parent_id):
    """Return actionable/waiting two-parent friendship stages for this active parent."""
    return fetch_all('''
        WITH owned AS (
          SELECT m.child_id
          FROM parent_child_map m
          JOIN users p ON p.user_id=%s AND p.role='PARENT' AND p.account_status='ACTIVE'
          WHERE m.approved=TRUE
            AND m.approval_status='APPROVED'
            AND (m.parent_id=%s OR m.verified_parent_id=%s)
        )
        SELECT * FROM (
          SELECT f.child_id, f.following_child_id,
                 u1.full_name requester_name, u2.full_name target_name,
                 f.approval_stage,
                 TRUE AS actionable,
                 'OUTGOING' AS approval_direction,
                 'Your child sent this request. Approve it before the other family sees an approval request.' AS stage_help,
                 f.created_at
          FROM followers f
          JOIN users u1 ON u1.user_id=f.child_id
          JOIN users u2 ON u2.user_id=f.following_child_id
          WHERE f.approved=FALSE AND f.approval_stage='REQUESTED'
            AND f.child_id IN (SELECT child_id FROM owned)

          UNION ALL

          SELECT f.child_id, f.following_child_id,
                 u2.full_name requester_name, u1.full_name target_name,
                 f.approval_stage,
                 TRUE AS actionable,
                 'INCOMING' AS approval_direction,
                 'The other child’s parent already approved. Approve this incoming friendship for your child.' AS stage_help,
                 f.created_at
          FROM followers f
          JOIN users u1 ON u1.user_id=f.child_id
          JOIN users u2 ON u2.user_id=f.following_child_id
          WHERE f.approved=FALSE AND f.approval_stage='RECEIVER_PARENT_PENDING'
            AND f.child_id IN (SELECT child_id FROM owned)

          UNION ALL

          SELECT f.child_id, f.following_child_id,
                 u1.full_name requester_name, u2.full_name target_name,
                 f.approval_stage,
                 FALSE AS actionable,
                 'WAITING' AS approval_direction,
                 'You approved this request. It is waiting for the other child’s parent.' AS stage_help,
                 f.created_at
          FROM followers f
          JOIN users u1 ON u1.user_id=f.child_id
          JOIN users u2 ON u2.user_id=f.following_child_id
          WHERE f.approved=FALSE AND f.approval_stage='SENDER_PARENT_APPROVED'
            AND f.child_id IN (SELECT child_id FROM owned)
        ) q
        ORDER BY actionable DESC, created_at ASC
    ''', (parent_id,parent_id,parent_id))


def get_parent_weekly_digest(parent_id, child_id):
    """
    Retrieves or synthesizes the weekly AI intelligence digest for a parent.
    Aggregates usage, quiz achievements, and safety alerts without leaking private chat text.
    """
    if not owns(parent_id, child_id):
        return None

    existing = fetch_one('''
        SELECT * FROM parent_weekly_digests
        WHERE child_id = %s AND week_start_date >= CURRENT_DATE - INTERVAL '7 days'
        ORDER BY created_at DESC LIMIT 1
    ''', (child_id,))
    if existing:
        import json
        data = existing.get('digest_data')
        return json.loads(data) if isinstance(data, str) else data

    usage_row = fetch_one('''
        SELECT COALESCE(SUM(GREATEST(EXTRACT(EPOCH FROM (logout_time-login_time)),0)), 0) AS seconds
        FROM child_usage_logs
        WHERE child_id = %s AND usage_date >= CURRENT_DATE - INTERVAL '7 days'
    ''', (child_id,))
    screen_hours = round(float((usage_row or {}).get('seconds', 0) or 0) / 3600.0, 1)

    attempts = fetch_all('''
        SELECT is_correct FROM child_quiz_attempts
        WHERE child_id = %s AND attempted_at >= NOW() - INTERVAL '7 days'
    ''', (child_id,))
    total_q = len(attempts)
    correct_q = sum(1 for a in attempts if a.get('is_correct'))
    accuracy = round((correct_q / total_q * 100.0), 1) if total_q > 0 else 0.0

    safety_counts = fetch_one('''
        SELECT
            COUNT(*) FILTER (WHERE decision = 'BLOCK') as blocked,
            COUNT(*) FILTER (WHERE decision = 'REVIEW') as reviews
        FROM moderation_events
        WHERE child_id = %s AND created_at >= NOW() - INTERVAL '7 days'
    ''', (child_id,))

    from services.ai import get_ai_client
    try:
        from quiz.service import age_group
        digest_age_group = age_group(child_id)
    except Exception:
        digest_age_group = None
    raw_stats = {
        "age_group": digest_age_group or "unknown",
        "quizzes_completed": total_q,
        "accuracy_pct": accuracy,
        "screen_time_hours": screen_hours,
        "safety_blocks_count": int((safety_counts or {}).get('blocked', 0) or 0),
        "reviews_count": int((safety_counts or {}).get('reviews', 0) or 0),
        "top_subjects": [],
        "weak_subjects": []
    }

    digest_res = get_ai_client().synthesize_parent_digest(raw_stats)
    digest_dict = digest_res.model_dump()

    import json
    try:
        execute('''
            INSERT INTO parent_weekly_digests(child_id, parent_id, week_start_date, headline, digest_data)
            VALUES(%s, %s, CURRENT_DATE, %s, %s::jsonb)
        ''', (child_id, parent_id, digest_dict['headline'], json.dumps(digest_dict)))
    except Exception:
        pass

    return digest_dict


def get_parent_safety_summary(parent_id, child_id):
    """Aggregates week-to-date safety events into a clear, parent-friendly summary."""
    if not owns(parent_id, child_id):
        return None

    stats = fetch_one('''
        SELECT
            COUNT(*) FILTER (WHERE decision = 'BLOCK') as blocks,
            COUNT(*) FILTER (WHERE decision = 'BLOCK' AND signals->>'category' = 'TEXT') as message_blocks,
            COUNT(*) FILTER (WHERE decision = 'REVIEW') as reviews,
            COUNT(*) FILTER (WHERE signals->>'reason_codes' ILIKE '%%PHONE%%' OR signals->>'reason_codes' ILIKE '%%CONTACT%%') as contact_attempts
        FROM moderation_events
        WHERE child_id = %s AND created_at >= NOW() - INTERVAL '7 days'
    ''', (child_id,))

    blocks = int((stats or {}).get('blocks', 0) or 0)
    msg_blocks = int((stats or {}).get('message_blocks', 0) or 0)
    reviews = int((stats or {}).get('reviews', 0) or 0)
    contacts = int((stats or {}).get('contact_attempts', 0) or 0)

    summary_text = (
        f"This week: {blocks} items blocked for safety ({msg_blocks} messages, {contacts} contact-sharing attempts); "
        f"{reviews} flagged for your review."
    )
    return {
        "blocks": blocks,
        "message_blocks": msg_blocks,
        "reviews": reviews,
        "contact_sharing_attempts": contacts,
        "summary_text": summary_text
    }
