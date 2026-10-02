import json
from database.connection import execute, fetch_one
from .common import normalize_signals
from .policy import decide, Decision, policy_metadata
from .text_service import check_text
from .visual_service import check_image
from .video_service import check_video


def safety_level(child_id):
    row=fetch_one('SELECT safety_level FROM parent_safety_settings WHERE child_id=%s',(child_id,))
    return (row or {}).get('safety_level','STRICT')


def evaluate(child_id,content_type,payload,adult_threshold=.40):
    t=content_type.upper()
    if t in {'AUDIO','VOICE'}:
        signals=normalize_signals({
            'category':t,
            'total_safety_failure':True,
            'errors':['standalone_audio_disabled'],
        },category=t)
        return signals,Decision('BLOCK',100.0,'Standalone audio and voice uploads are disabled in LittleNet')
    if t=='TEXT':
        signals=check_text(payload)
    elif t=='VIDEO':
        signals=check_video(payload)
    elif t=='IMAGE':
        signals=check_image(payload)
    else:
        # Fail closed on unsupported content types: an explicit BLOCK decision
        # (never ALLOW, never publish) so API callers map it to 4xx instead of
        # surfacing a 500 from a raised ValueError.
        signals=normalize_signals({
            'category':t,
            'total_safety_failure':True,
            'errors':['unsupported_content_type'],
        },category=t)
        return signals,Decision('BLOCK',100.0,f'Unsupported moderation content type: {t}')
    signals=normalize_signals(signals,category=t)
    d=decide(signals,safety_level(child_id),adult_threshold)
    return signals,d


def record(child_id,content_type,content_id,signals,decision):
    signals=normalize_signals(signals,category=content_type)
    # Persist policy provenance with the evidence so later review and incident
    # analysis can reproduce which rules made the decision.
    for key,value in policy_metadata().items():
        signals.setdefault(key,value)
    status='OPEN' if decision.action=='REVIEW' else 'RESOLVED'
    return execute('''INSERT INTO moderation_events(child_id,content_type,content_id,risk_score,adult_score,violence_score,weapon_score,toxicity_score,decision,reason,signals,status) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s) RETURNING event_id''',(
        child_id,content_type,content_id,decision.risk,float(signals.get('adult_score',0))*100,float(signals.get('violence_score',0))*100,float(signals.get('weapon_score',0))*100,float(signals.get('toxicity_score',0))*100,decision.action,decision.reason,json.dumps(signals),status),returning=True)['event_id']
