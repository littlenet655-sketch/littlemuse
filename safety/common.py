"""Shared safety helpers.

All adapters remain optional/lazy. A feature flag that is disabled is not a
failure; a feature flag that is enabled but cannot run becomes a partial safety
failure so policy.py can fail closed to REVIEW/BLOCK.
"""
from __future__ import annotations
import math
import os
import queue
import threading
from typing import Any, Callable

BASE_SIGNAL_KEYS=(
    'adult_score','sexual_score','violence_score','weapon_score','toxicity_score',
    'general_score','category','total_safety_failure','partial_safety_failure','errors'
)

class ModelTimeout(RuntimeError):
    pass

def env_flag(name:str, default:bool=False)->bool:
    raw=os.getenv(name,'1' if default else '0').strip().lower()
    return raw in {'1','true','yes','on','enabled'}

def timeout_seconds(name:str, default:float)->float:
    specific=os.getenv(f'LITTLENET_{name.upper()}_TIMEOUT_SECONDS','').strip()
    general=os.getenv('LITTLENET_MODEL_TIMEOUT_SECONDS','').strip()
    raw=specific or general or str(default)
    try:return max(1.0,float(raw))
    except ValueError:return default

def timed_call(name:str, fn:Callable[[],Any], seconds:float|None=None)->Any:
    """Best-effort request timeout using a daemon worker.

    The caller can return fail-closed immediately if an inference call stalls.
    Modal/Gunicorn request timeouts remain the outer hard-stop for the process.
    """
    q:queue.Queue=queue.Queue(maxsize=1)
    def run():
        try:q.put((True,fn()))
        except BaseException as exc:q.put((False,exc))
    t=threading.Thread(target=run,name=f'littlenet-{name}',daemon=True);t.start()
    try:ok,value=q.get(timeout=seconds or timeout_seconds(name,90))
    except queue.Empty as exc:raise ModelTimeout(f'{name}_timeout') from exc
    if ok:return value
    raise value

def normalize_signals(signals:dict|None, *, category:str='UNKNOWN')->dict:
    """Normalize moderation evidence without turning malformed evidence into SAFE.

    A missing/empty envelope is a complete safety failure. Individual malformed
    scores become a partial failure so policy.py routes the item to REVIEW rather
    than silently treating bad evidence as a zero-risk signal.
    """
    if not isinstance(signals,dict) or not signals:
        return {
            'adult_score':0.0,
            'sexual_score':0.0,
            'violence_score':0.0,
            'weapon_score':0.0,
            'toxicity_score':0.0,
            'general_score':0.0,
            'category':str(category or 'UNKNOWN').upper(),
            'total_safety_failure':True,
            'partial_safety_failure':False,
            'errors':['invalid_signal_envelope'],
        }

    raw=dict(signals)
    errors=raw.get('errors') or []
    if isinstance(errors,str):errors=[errors]
    elif not isinstance(errors,(list,tuple,set)):errors=['invalid_errors_field']
    errors=[str(x) for x in errors if x]
    validation_errors=[]

    def score(name, fallback=0.0):
        value=raw.get(name,fallback)
        if value is None or value=='':value=fallback
        if isinstance(value,bool):
            validation_errors.append(f'invalid_{name}')
            return 0.0
        try:value=float(value)
        except (TypeError,ValueError):
            validation_errors.append(f'invalid_{name}')
            return 0.0
        if not math.isfinite(value) or value<0.0 or value>1.0:
            validation_errors.append(f'invalid_{name}')
            return 0.0
        return value

    for flag in ('total_safety_failure','partial_safety_failure'):
        if flag in raw and not isinstance(raw[flag],bool):validation_errors.append(f'invalid_{flag}')

    adult=score('adult_score',0.0)
    sexual=score('sexual_score',adult)
    violence=score('violence_score',0.0)
    weapon=score('weapon_score',0.0)
    toxicity=score('toxicity_score',0.0)
    general=score('general_score',0.0)
    total_failure=raw.get('total_safety_failure') is True
    partial_failure=raw.get('partial_safety_failure') is True
    if validation_errors and not total_failure:partial_failure=True

    out={
        'adult_score':max(adult,sexual),
        'sexual_score':sexual,
        'violence_score':violence,
        'weapon_score':weapon,
        'toxicity_score':toxicity,
        'general_score':general,
        'category':str(raw.get('category') or category).upper(),
        'total_safety_failure':total_failure,
        'partial_safety_failure':partial_failure,
        'errors':list(dict.fromkeys(errors+validation_errors)),
    }
    # Preserve non-contract diagnostic keys such as transcript/model scores.
    for k,v in raw.items():
        if k not in out:out[k]=v
    out['general_score']=max(out['general_score'],out['adult_score'],out['violence_score'],out['weapon_score'],out['toxicity_score'])
    return out
