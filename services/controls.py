import json
import os
from datetime import datetime, time
from zoneinfo import ZoneInfo
from database.connection import fetch_one, execute
from services.request_cache import memo as _req_memo

SAFE_CATEGORIES = [
    'Other','Science','Math','Art','Sports','Music','Technology','Education',
    'Nature','Books','Coding','General Knowledge',
    'Family & Community','Nature & Animals','Art & Creative Hobbies',
    'Science & Gardening','Culinary Arts & Food'
]
EDUCATIONAL_CATEGORIES = [
    'Science','Math','Technology','Education','Nature','Books','Coding','General Knowledge',
    'Nature & Animals','Art & Creative Hobbies','Science & Gardening','Culinary Arts & Food'
]
FEATURE_COLUMNS = {
    'reels':'allow_reels',
    'stories':'allow_stories',
    'messaging':'allow_messaging',
    'posting':'allow_posting',
    'discover':'allow_discover',
    'comments':'allow_comments',
}


def _clock(value, fallback):
    if isinstance(value, time):
        return value.strftime('%H:%M')
    if value is None:
        return fallback
    text=str(value).strip()
    return text[:5] if len(text)>=5 else fallback


def _defaults(child_id=None):
    return {
        'child_id':child_id,
        'allow_reels':True,
        'allow_stories':True,
        'allow_messaging':True,
        'allow_posting':True,
        'allow_discover':True,
        'allow_comments':True,
        'quiet_hours_enabled':False,
        'quiet_start':'21:00',
        'quiet_end':'07:00',
        'educational_only_feed':False,
        'allowed_categories':list(SAFE_CATEGORIES),
    }

import time as _time
_controls_cache = {}
_controls_cache_ttl = 15.0


def controls_for_child(child_id):
    now = _time.time()
    cached = _controls_cache.get(child_id)
    if cached and (now - cached['time'] < _controls_cache_ttl):
        return dict(cached['data'])
    row=fetch_one('SELECT * FROM parent_control_settings WHERE child_id=%s',(child_id,))
    if not row:
        out = _defaults(child_id)
    else:
        out=_defaults(child_id);out.update(dict(row))
        raw_cats=out.get('allowed_categories')
        cats=list(SAFE_CATEGORIES) if raw_cats is None else list(raw_cats)
        out['allowed_categories']=[c for c in cats if c in SAFE_CATEGORIES]
        out['quiet_start']=_clock(out.get('quiet_start'),'21:00')
        out['quiet_end']=_clock(out.get('quiet_end'),'07:00')
    _controls_cache[child_id] = {'data': out, 'time': now}
    return dict(out)


def feature_allowed(child_id,feature):
    # Checked per post for reels/stories gating; controls cannot change
    # mid-request, so memoize it on flask.g.
    return _req_memo(("feature_allowed", child_id, feature), lambda: _feature_allowed_uncached(child_id, feature))


def _feature_allowed_uncached(child_id,feature):
    col=FEATURE_COLUMNS.get(feature)
    if not col:return True
    return bool(controls_for_child(child_id).get(col,True))


CATEGORY_SYNONYMS = {
    'Nature': ['Nature & Animals'],
    'Art': ['Art & Creative Hobbies', 'Culinary Arts & Food'],
    'Science': ['Science & Gardening'],
    'Other': ['Family & Community'],
}


def effective_categories(child_id):
    # Evaluated once per feed item and per media authorization; parent controls
    # cannot change mid-request, so memoize it on flask.g.
    return _req_memo(("effective_categories", child_id), lambda: _effective_categories_uncached(child_id))


def _effective_categories_uncached(child_id):
    c=controls_for_child(child_id)
    allowed=[x for x in c['allowed_categories'] if x in SAFE_CATEGORIES]
    if c.get('educational_only_feed'):
        allowed=[x for x in allowed if x in EDUCATIONAL_CATEGORIES]
    # An explicitly empty parent selection is a deny-all policy. Never widen
    # it back to every safe category.
    if not allowed:
        return []
    base = allowed
    expanded = list(base)
    for cat in base:
        for syn in CATEGORY_SYNONYMS.get(cat, []):
            if syn not in expanded:
                expanded.append(syn)
    return expanded


def _parse_clock(value):
    try:
        parts=str(value).split(':')
        if len(parts)<2:raise ValueError
        hour,minute=int(parts[0]),int(parts[1])
        if not (0<=hour<=23 and 0<=minute<=59):raise ValueError
        return time(hour,minute)
    except (TypeError,ValueError):
        raise ValueError('invalid_quiet_hours')


def quiet_hours_state(child_id, at=None):
    controls=controls_for_child(child_id)
    if not controls.get('quiet_hours_enabled'):
        return {'active':False,'start':controls['quiet_start'],'end':controls['quiet_end']}
    if at is None:
        try:tz=ZoneInfo(os.getenv('APP_TIMEZONE','Asia/Kolkata'))
        except Exception:tz=ZoneInfo('UTC')
        at=datetime.now(tz)
    current=at.timetz().replace(tzinfo=None) if getattr(at,'tzinfo',None) else at.time()
    try:
        start=_parse_clock(controls['quiet_start']);end=_parse_clock(controls['quiet_end'])
    except ValueError:
        start=time(21,0);end=time(7,0)
    if start==end:
        active=True
    elif start<end:
        active=start<=current<end
    else:
        active=current>=start or current<end
    return {'active':active,'start':controls['quiet_start'],'end':controls['quiet_end']}


def quiet_hours_active(child_id, at=None):
    return bool(quiet_hours_state(child_id,at)['active'])


def save_controls(parent_id,child_id,form):
    allowed=[x for x in form.getlist('allowed_categories') if x in SAFE_CATEGORIES]
    qstart=_clock(form.get('quiet_start'),'21:00');qend=_clock(form.get('quiet_end'),'07:00')
    _parse_clock(qstart);_parse_clock(qend)
    values={
        'allow_reels':'allow_reels' in form,
        'allow_stories':'allow_stories' in form,
        'allow_messaging':'allow_messaging' in form,
        'allow_posting':'allow_posting' in form,
        'allow_discover':'allow_discover' in form,
        'allow_comments':'allow_comments' in form,
        'quiet_hours_enabled':'quiet_hours_enabled' in form,
        'educational_only_feed':'educational_only_feed' in form,
    }
    execute('''INSERT INTO parent_control_settings(
        child_id,parent_id,allow_reels,allow_stories,allow_messaging,allow_posting,allow_discover,allow_comments,
        quiet_hours_enabled,quiet_start,quiet_end,educational_only_feed,allowed_categories,updated_at
      ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::time,%s::time,%s,%s::jsonb,NOW())
      ON CONFLICT(child_id) DO UPDATE SET parent_id=EXCLUDED.parent_id,allow_reels=EXCLUDED.allow_reels,
      allow_stories=EXCLUDED.allow_stories,allow_messaging=EXCLUDED.allow_messaging,allow_posting=EXCLUDED.allow_posting,
      allow_discover=EXCLUDED.allow_discover,allow_comments=EXCLUDED.allow_comments,quiet_hours_enabled=EXCLUDED.quiet_hours_enabled,
      quiet_start=EXCLUDED.quiet_start,quiet_end=EXCLUDED.quiet_end,educational_only_feed=EXCLUDED.educational_only_feed,
      allowed_categories=EXCLUDED.allowed_categories,updated_at=NOW()''',(
        child_id,parent_id,values['allow_reels'],values['allow_stories'],values['allow_messaging'],values['allow_posting'],
        values['allow_discover'],values['allow_comments'],values['quiet_hours_enabled'],qstart,qend,values['educational_only_feed'],json.dumps(allowed)))
    _controls_cache.pop(child_id, None)
    return controls_for_child(child_id)
