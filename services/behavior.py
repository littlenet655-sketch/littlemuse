from database.connection import fetch_one, fetch_all


def _count(sql, params):
    row = fetch_one(sql, params) or {'n': 0}
    return int(row.get('n') or 0)


def _window_metrics(child_id, start_days, end_days=0):
    # Window is [now-start_days, now-end_days). For current 7 days: 7,0.
    params = (child_id, start_days, end_days)
    ev = fetch_one('''
        SELECT
          COUNT(*) FILTER (WHERE decision='BLOCK') AS blocked,
          COUNT(*) FILTER (WHERE decision='REVIEW') AS reviewed,
          COUNT(*) FILTER (WHERE decision='BLOCK' AND adult_score>=40) AS adult_blocks,
          COUNT(*) FILTER (WHERE decision='BLOCK' AND weapon_score>=45) AS weapon_blocks,
          COUNT(*) FILTER (WHERE content_type IN ('MESSAGE','COMMENT','TEXT') AND decision='BLOCK') AS harmful_text_blocks
        FROM moderation_events
        WHERE child_id=%s
          AND created_at >= NOW()-(%s * INTERVAL '1 day')
          AND created_at <  NOW()-(%s * INTERVAL '1 day')
    ''', params) or {}
    reports = _count('''SELECT COUNT(*) n FROM reports WHERE target_type='USER' AND target_id=%s
        AND created_at >= NOW()-(%s * INTERVAL '1 day')
        AND created_at < NOW()-(%s * INTERVAL '1 day')''', params)
    screen_hits = _count('''SELECT COUNT(*) n FROM activity_logs WHERE child_id=%s AND activity_type='SCREEN_TIME_LIMIT_REACHED'
        AND created_at >= NOW()-(%s * INTERVAL '1 day')
        AND created_at < NOW()-(%s * INTERVAL '1 day')''', params)
    blocked_users = _count('''SELECT COUNT(*) n FROM activity_logs WHERE child_id=%s AND activity_type='USER_BLOCKED'
        AND created_at >= NOW()-(%s * INTERVAL '1 day')
        AND created_at < NOW()-(%s * INTERVAL '1 day')''', params)
    return {
        'blocked': int(ev.get('blocked') or 0),
        'reviewed': int(ev.get('reviewed') or 0),
        'adult_blocks': int(ev.get('adult_blocks') or 0),
        'weapon_blocks': int(ev.get('weapon_blocks') or 0),
        'harmful_text_blocks': int(ev.get('harmful_text_blocks') or 0),
        'reports': reports,
        'screen_hits': screen_hits,
        'blocked_users': blocked_users,
    }


def _score(m):
    # Explainable safety/activity indicator for a college project. It is deliberately
    # rule based; this is not a psychological or clinical assessment.
    raw = (
        m['adult_blocks'] * 18
        + m['weapon_blocks'] * 16
        + m['harmful_text_blocks'] * 10
        + max(0, m['blocked'] - m['adult_blocks'] - m['weapon_blocks'] - m['harmful_text_blocks']) * 8
        + m['reviewed'] * 4
        + m['reports'] * 12
        + m['screen_hits'] * 3
        + m['blocked_users'] * 2
    )
    return min(100, int(raw))


def behavior_summary(child_id):
    current = _window_metrics(child_id, 7, 0)
    previous = _window_metrics(child_id, 14, 7)
    score = _score(current)
    previous_score = _score(previous)
    level = 'HIGH' if score >= 60 else 'MEDIUM' if score >= 30 else 'LOW'
    delta = score - previous_score
    trend = 'UP' if delta >= 8 else 'DOWN' if delta <= -8 else 'STABLE'

    reasons = []
    if current['adult_blocks']:
        reasons.append(f"{current['adult_blocks']} adult/18+ attempt(s) blocked")
    if current['weapon_blocks']:
        reasons.append(f"{current['weapon_blocks']} weapon/danger event(s) blocked")
    if current['harmful_text_blocks']:
        reasons.append(f"{current['harmful_text_blocks']} harmful text/message event(s) blocked")
    if current['reports']:
        reasons.append(f"{current['reports']} report(s) received")
    if current['reviewed']:
        reasons.append(f"{current['reviewed']} item(s) required parent review")
    if current['screen_hits']:
        reasons.append(f"{current['screen_hits']} screen-time limit event(s)")
    if not reasons:
        reasons.append('No significant safety events in the last 7 days')

    daily = fetch_all('''
        SELECT DATE(created_at) AS "day",
               COUNT(*) FILTER (WHERE decision='BLOCK') blocked,
               COUNT(*) FILTER (WHERE decision='REVIEW') reviewed
        FROM moderation_events
        WHERE child_id=%s AND created_at>=CURRENT_DATE-INTERVAL '6 days'
        GROUP BY DATE(created_at) ORDER BY "day"
    ''', (child_id,))
    return {
        'score': score,
        'previous_score': previous_score,
        'level': level,
        'trend': trend,
        'delta': delta,
        'metrics': current,
        'previous': previous,
        'reasons': reasons,
        'daily': daily,
    }
