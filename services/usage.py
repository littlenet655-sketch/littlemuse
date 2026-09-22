from datetime import datetime,time
import json
from database.connection import fetch_one,fetch_all,execute


def _log_session(row,end_at):
    mins=max(0,int((end_at-row['started_at']).total_seconds()/60))
    execute('INSERT INTO child_usage_logs(child_id,usage_date,login_time,logout_time,duration_minutes) VALUES(%s,%s,%s,%s,%s)',(row['child_id'],row['started_at'].date(),row['started_at'],end_at,mins))


def _finalize_open(child_id):
    rows=fetch_all('SELECT * FROM child_usage_sessions WHERE child_id=%s AND ended_at IS NULL',(child_id,))
    for row in rows:
        end_at=row['last_seen_at'] or row['started_at'];execute('UPDATE child_usage_sessions SET ended_at=%s WHERE usage_session_id=%s',(end_at,row['usage_session_id'],));_log_session(row,end_at)


def start_session(child_id):
    _finalize_open(child_id);return execute('INSERT INTO child_usage_sessions(child_id) VALUES(%s) RETURNING usage_session_id,session_key,started_at',(child_id,),returning=True)


def heartbeat(session_key):
    row=fetch_one('SELECT * FROM child_usage_sessions WHERE session_key=%s AND ended_at IS NULL',(session_key,))
    if not row:return None
    now=datetime.now()
    if row['started_at'].date()<now.date():
        midnight=datetime.combine(now.date(),time.min);_log_session(row,midnight);execute('UPDATE child_usage_sessions SET started_at=%s,last_seen_at=%s WHERE usage_session_id=%s',(midnight,now,row['usage_session_id']))
    else:execute('UPDATE child_usage_sessions SET last_seen_at=%s WHERE usage_session_id=%s',(now,row['usage_session_id']))
    return True


def close_session(session_key):
    heartbeat(session_key);row=fetch_one('SELECT * FROM child_usage_sessions WHERE session_key=%s AND ended_at IS NULL',(session_key,))
    if not row:return
    end_at=row['last_seen_at'];execute('UPDATE child_usage_sessions SET ended_at=%s WHERE usage_session_id=%s',(end_at,row['usage_session_id'],));_log_session(row,end_at)


def seconds_today(child_id):
    """Return aggregate elapsed seconds before rounding to display minutes.

    Summing timestamps instead of per-session integer minutes prevents repeated
    short sessions (for example 59 seconds each) from disappearing completely.
    """
    logged=fetch_one('''SELECT COALESCE(SUM(GREATEST(EXTRACT(EPOCH FROM (logout_time-login_time)),0)),0) total
        FROM child_usage_logs WHERE child_id=%s AND usage_date=CURRENT_DATE''',(child_id,))['total']
    active=fetch_one("""SELECT COALESCE(SUM(GREATEST(EXTRACT(EPOCH FROM (last_seen_at-started_at)),0)),0) total
        FROM child_usage_sessions WHERE child_id=%s AND ended_at IS NULL AND started_at::date=CURRENT_DATE""",(child_id,))['total']
    return max(0.0,float(logged or 0)+float(active or 0))


def minutes_today(child_id):
    return int(seconds_today(child_id)/60.0)


def _notice_once(child_id, activity_type, parent_type, message, remaining):
    seen=fetch_one('SELECT 1 FROM activity_logs WHERE child_id=%s AND activity_type=%s AND created_at::date=CURRENT_DATE LIMIT 1',(child_id,activity_type))
    if seen:return
    execute('INSERT INTO activity_logs(child_id,activity_type,activity_data) VALUES(%s,%s,%s::jsonb)',(child_id,activity_type,json.dumps({'remaining_minutes':remaining})))
    execute('''INSERT INTO parent_notifications(parent_id,child_id,notification_type,notification_message,target_url)
               SELECT pcm.parent_id,%s,%s,%s,'/parent/time-limit/?child_id='||%s
               FROM parent_child_map pcm
               JOIN users p ON p.user_id=pcm.parent_id
               WHERE pcm.child_id=%s
                 AND pcm.parent_id IS NOT NULL
                 AND pcm.approved=TRUE
                 AND pcm.approval_status='APPROVED'
                 AND p.role='PARENT'
                 AND p.account_status='ACTIVE' ''',(child_id,parent_type,message,child_id,child_id))


def lock_state(child_id):
    lim=fetch_one('SELECT * FROM child_time_limits WHERE child_id=%s',(child_id,))
    if not lim:return False,None
    used=minutes_today(child_id);remaining=max(0,int(lim['daily_limit_minutes'])-used);locked=bool(lim['strict_mode'] and remaining<=0)
    if lim['strict_mode']:
        warning_at=min(10,max(1,int(lim['daily_limit_minutes'])//5))
        if locked:
            _notice_once(child_id,'SCREEN_TIME_LIMIT_REACHED','SCREEN_TIME_LIMIT','Daily LittleNet screen-time limit was reached.',0)
        elif remaining<=warning_at:
            _notice_once(child_id,'SCREEN_TIME_WARNING','SCREEN_TIME_WARNING',f'{remaining} minute(s) of LittleNet time remaining today.',remaining)
    return locked,remaining


def online_state(child_id, stale_seconds=90):
    row=fetch_one("""SELECT last_seen_at,ended_at,
        (ended_at IS NULL AND last_seen_at>=NOW()-(%s * INTERVAL '1 second')) AS online
        FROM child_usage_sessions WHERE child_id=%s
        ORDER BY last_seen_at DESC NULLS LAST,started_at DESC LIMIT 1""",(stale_seconds,child_id))
    return {'online':bool((row or {}).get('online')),'last_seen_at':(row or {}).get('last_seen_at') if row else None}
