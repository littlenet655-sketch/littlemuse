import os,re,unicodedata
from .common import env_flag,normalize_signals,timed_call,timeout_seconds

# Exact/near-exact high-risk phrases. These deterministic rules are deliberately
# narrow: the ML sexual-explicit score handles broader context while these rules
# guarantee obvious sexual solicitation cannot pass if a model is unavailable.
ADULT_TERMS={
    'porn','pornography','nude','nudes','sex video','sex tape','xxx','send nudes',
    'sexual photo','sexual picture','explicit photo','explicit picture','onlyfans',
    'sexting','send me a nude','send nude','take your clothes off','remove your clothes',
    'show me your body','show your body','naked pic','naked picture','naked photo',
    'private parts','show me your private parts','send a sexy pic','send sexy pics',
    'send a hot pic','send hot pics','adult video','adult content','nsfw','18+ video',
    '18+ content','dirty picture','dirty pics','bedroom pic','without clothes'
}
ADULT_PATTERNS=(
    r"\bsend\s+(?:me\s+)?(?:a\s+)?(?:nude|nudes|naked|sexy|hot|explicit|private)\s*(?:pic|pics|picture|pictures|photo|photos|selfie|selfies)?\b",
    r"\bshow\s+(?:me\s+)?(?:your\s+)?(?:body|private parts|chest|breasts?|genitals?)\b",
    r"\b(?:take|remove|pull)\s+(?:off\s+)?(?:your\s+)?clothes\b",
    r"\b(?:naked|nude|explicit|sexual|sexy)\s+(?:pic|pics|picture|pictures|photo|photos|video|videos|selfie|selfies)\b",
    r"\b(?:watch|send|share)\s+(?:a\s+)?(?:porn|porno|xxx|adult|18\+)\s*(?:video|videos|clip|clips|content)?\b",
    r"\b(?:sext|sexting|cybersex)\b",
)
PROFANE={'fuck','bitch','asshole'}
BULLYING_TERMS={
    'kill yourself','nobody likes you','you are ugly','you are stupid','you are useless',
    'loser','idiot','worthless','go die','hate you','shut up','no one wants you','everyone hates you'
}
SEVERE_ABUSE_TERMS={
    'i will kill you','i am going to kill you','i will hurt you','i will beat you',
    'you deserve to die','go kill yourself','hurt yourself','cut yourself','hang yourself',
    'i will find you','i know where you live','i will come to your house'
}
SELF_HARM_TERMS={
    'i want to kill myself','i am going to kill myself','i will kill myself',
    'i want to die','i do not want to live','i dont want to live','end my life',
    'how do i kill myself','ways to kill myself','help me commit suicide',
}
DANGEROUS_CHALLENGE_TERMS={
    'choking game','blackout challenge','pass out challenge','fire challenge',
    'hold your breath until you pass out','make yourself pass out',
    'swallow detergent','eat a tide pod','set yourself on fire',
}
GROOMING_PATTERNS=(
    r"\bdon'?t tell (?:your )?(?:mom|mum|mother|dad|father|parents?)\b",
    r"\bkeep (?:this|it) (?:a )?secret\b",
    r"\bour little secret\b",
    r"\bmeet me (?:alone|privately|outside|after school)\b",
    r"\bcome alone\b",
    r"\bdelete (?:this|our) chat\b",
    r"\bsend (?:me )?(?:a )?(?:pic|photo|selfie) (?:in|without|of)\b",
    r"\bwhat are you wearing\b",
    r"\bwhere do you live\b",
    r"\bwhat(?:'s| is) your address\b",
    r"\bgive me your (?:phone|number|snap|instagram|telegram)\b",
    r"\badd me on (?:snap|snapchat|instagram|telegram|whatsapp)\b",
)

_DETOX=None;_DETOX_NAME=None;_HF_TEXT=None

# Confusable-skeleton fold: Cyrillic/Greek lookalikes that survive NFKC and
# evade the Latin term/pattern lists (proven: "send nudеs" with Cyrillic е
# scored clean). Applied inside _normalized_text -- i.e. only to the copy
# used for deterministic matching; the original text passed to ML/audit is
# untouched. Covers lowercase forms because _normalized_text lowercases first.
_CONFUSABLES=str.maketrans({
    # Cyrillic -> Latin
    'а':'a','с':'c','е':'e','ё':'e','і':'i','ј':'j','о':'o','р':'p',
    'х':'x','у':'y','к':'k','м':'m','н':'h','т':'t','в':'b','п':'n',
    'ш':'w','ѕ':'s','ґ':'g',
    # Greek -> Latin
    'α':'a','β':'b','ε':'e','ζ':'z','η':'n','ι':'i','κ':'k','μ':'u',
    'ν':'v','ο':'o','ρ':'p','ς':'s','σ':'o','τ':'t','υ':'u','χ':'x',
    'ω':'w','δ':'d',
})


def _normalized_text(text):
    """Canonicalize common evasion without changing the text sent to ML."""
    value=unicodedata.normalize('NFKC',text or '').lower()
    value=''.join(ch for ch in value if unicodedata.category(ch) not in {'Cf','Mn'})
    value=value.translate(_CONFUSABLES)
    value=value.translate(str.maketrans({'0':'o','1':'i','3':'e','4':'a','5':'s','7':'t','@':'a','$':'s'}))
    value=re.sub(r'(?<=\w)[._*~`|/\\-]+(?=\w)','',value)
    value=re.sub(r'(.)\1{2,}',r'\1\1',value)
    value=re.sub(r'[^\w\s+\']+',' ',value,flags=re.UNICODE)
    value=re.sub(r'\s+',' ',value).strip()
    # Collapse four-or-more deliberately spaced letters ("n u d e s") while
    # leaving ordinary short phrases such as "i am ok" unchanged.
    value=re.sub(
        r'(?<!\w)(?:[a-z]\s+){3,}[a-z](?!\w)',
        lambda match: re.sub(r'\s+','',match.group(0)),
        value,
    )
    return value


def check_text_deterministic(text: str):
    """Cheap, model-free high-risk text gate.

    This is not a replacement for ML moderation. It is used only to stop
    obvious hard-block content before a media worker/GPU is started.
    """
    text = (text or "").strip()
    low = _normalized_text(text)
    compact = low.replace(" ", "")

    adult = 1.0 if (
        any(t in low for t in ADULT_TERMS)
        or any(t.replace(" ", "") in compact for t in ADULT_TERMS if " " in t)
        or any(re.search(p, low) for p in ADULT_PATTERNS)
    ) else 0.0
    profanity = 1.0 if any(re.search(r"\b" + re.escape(t) + r"\b", low) for t in PROFANE) else 0.0
    bullying = .90 if any(t in low for t in BULLYING_TERMS) else 0.0
    severe = 1.0 if any(t in low for t in SEVERE_ABUSE_TERMS) else 0.0
    self_harm = 1.0 if any(t in low for t in SELF_HARM_TERMS) else 0.0
    dangerous_challenge = 1.0 if any(t in low for t in DANGEROUS_CHALLENGE_TERMS) else 0.0
    grooming = 1.0 if any(re.search(p, low) for p in GROOMING_PATTERNS) else 0.0

    if grooming:
        category = "GROOMING"
    elif self_harm:
        category = "SELF_HARM"
    elif dangerous_challenge:
        category = "DANGEROUS_CHALLENGE"
    elif severe:
        category = "SEVERE_ABUSE"
    elif adult:
        category = "SEXUAL_LANGUAGE"
    elif bullying:
        category = "CYBERBULLYING"
    else:
        category = "TEXT"

    toxicity = max(profanity, bullying, severe, self_harm, dangerous_challenge, grooming)
    return normalize_signals({
        "adult_score": adult,
        "sexual_score": adult,
        "violence_score": severe,
        "weapon_score": 0.0,
        "toxicity_score": toxicity,
        "general_score": max(adult, toxicity, severe),
        "category": category,
        "deterministic_grooming": bool(grooming),
        "deterministic_severe_abuse": bool(severe),
        "deterministic_self_harm": bool(self_harm),
        "deterministic_dangerous_challenge": bool(dangerous_challenge),
        "deterministic_sexual": bool(adult),
        "deterministic_only": True,
        "total_safety_failure": False,
        "partial_safety_failure": False,
        "errors": [],
    }, category="TEXT")


def _detox_scores(text):
    global _DETOX, _DETOX_NAME
    from detoxify import Detoxify
    # ``original`` does not expose sexual_explicit. LittleNet needs that head,
    # so production defaults to multilingual and falls back to unbiased only.
    model_name=os.getenv('LITTLENET_DETOXIFY_MODEL','multilingual').strip() or 'multilingual'
    if model_name not in {'multilingual','unbiased'}:
        model_name='multilingual'
    if _DETOX is None or _DETOX_NAME!=model_name:
        _orig_load = None
        try:
            import torch
            if hasattr(torch, 'load'):
                _orig_load = torch.load
                def _safe_load(*args, **kwargs):
                    if 'weights_only' not in kwargs:
                        kwargs['weights_only'] = False
                    return _orig_load(*args, **kwargs)
                torch.load = _safe_load
        except Exception:
            _orig_load = None

        try:
            try:
                _DETOX=Detoxify(model_name)
                _DETOX_NAME=model_name
            except Exception:
                _DETOX=Detoxify('unbiased')
                _DETOX_NAME='unbiased'
        finally:
            if _orig_load is not None:
                try:
                    import torch
                    torch.load = _orig_load
                except Exception:
                    pass
    scores=_DETOX.predict(text) if text else {}
    if text and 'sexual_explicit' not in scores:
        raise RuntimeError('detoxify_missing_sexual_explicit_head')
    return scores


def _optional_hf_scores(text):
    if not env_flag('LITTLENET_ENABLE_TEXT_CLASSIFIER'):return None
    model_id=os.getenv('LITTLENET_TEXT_SAFETY_MODEL','').strip()
    if not model_id:raise RuntimeError('text_classifier_model_missing')
    global _HF_TEXT
    if _HF_TEXT is None:
        from transformers import pipeline
        _HF_TEXT=pipeline('text-classification',model=model_id,top_k=None,device=-1)
    rows=_HF_TEXT(text[:4000])
    if rows and isinstance(rows[0],list):rows=rows[0]
    harmful=0.0;sexual=0.0;details={}
    for row in rows or []:
        label=str(row.get('label','')).lower();score=float(row.get('score',0) or 0);details[label]=score
        if any(k in label for k in ('toxic','hate','bully','harass','self-harm','self_harm','unsafe')):harmful=max(harmful,score)
        if any(k in label for k in ('sexual','explicit','porn','nsfw','adult')):sexual=max(sexual,score)
    return {'toxicity':harmful,'sexual':sexual,'labels':details}


def check_text(text:str):
    from .remote_client import enabled,moderate_text
    text=(text or '').strip();low=_normalized_text(text)

    compact=low.replace(' ','')
    adult=1.0 if (
        any(t in low for t in ADULT_TERMS)
        or any(t.replace(' ','') in compact for t in ADULT_TERMS if ' ' in t)
        or any(re.search(p,low) for p in ADULT_PATTERNS)
    ) else 0.0
    profanity=1.0 if any(re.search(r'\b'+re.escape(t)+r'\b',low) for t in PROFANE) else 0.0
    bullying=.90 if any(t in low for t in BULLYING_TERMS) else 0.0
    severe=1.0 if any(t in low for t in SEVERE_ABUSE_TERMS) else 0.0
    self_harm=1.0 if any(t in low for t in SELF_HARM_TERMS) else 0.0
    dangerous_challenge=1.0 if any(t in low for t in DANGEROUS_CHALLENGE_TERMS) else 0.0
    grooming=1.0 if any(re.search(p,low) for p in GROOMING_PATTERNS) else 0.0
    remote_failed=False

    # Production web requests prefer the scale-to-zero Modal CPU text tier.
    # The AI server sets LITTLENET_AI_SERVER=1, so calls inside that worker run
    # Detoxify locally and never recurse back into Modal.
    if text and os.getenv("LITTLENET_AI_SERVER") != "1":
        try:
            from services.modal_text_moderation import (
                allow_gpu_fallback as text_gpu_fallback_allowed,
                enabled as modal_text_cpu_enabled,
                moderate_text as moderate_text_cpu,
            )
            if modal_text_cpu_enabled():
                try:
                    cpu=normalize_signals(moderate_text_cpu(text),category='TEXT')
                    cpu['adult_score']=max(float(cpu.get('adult_score',0)),adult)
                    cpu['sexual_score']=max(float(cpu.get('sexual_score',0)),adult)
                    cpu['toxicity_score']=max(float(cpu.get('toxicity_score',0)),profanity,bullying,severe,self_harm,dangerous_challenge,grooming)
                    cpu['general_score']=max(float(cpu.get('general_score',0)),cpu['adult_score'],cpu['toxicity_score'])
                    if grooming:cpu['category']='GROOMING'
                    elif self_harm:cpu['category']='SELF_HARM'
                    elif dangerous_challenge:cpu['category']='DANGEROUS_CHALLENGE'
                    elif severe:cpu['category']='SEVERE_ABUSE'
                    elif adult:cpu['category']='SEXUAL_LANGUAGE'
                    elif bullying:cpu['category']='CYBERBULLYING'
                    cpu['deterministic_grooming']=bool(grooming)
                    cpu['deterministic_severe_abuse']=bool(severe)
                    cpu['deterministic_self_harm']=bool(self_harm)
                    cpu['deterministic_dangerous_challenge']=bool(dangerous_challenge)
                    cpu['deterministic_sexual']=bool(adult)
                    cpu['compute_tier']='modal_cpu'
                    return normalize_signals(cpu,category='TEXT')
                except Exception:
                    if not text_gpu_fallback_allowed():
                        deterministic=adult>0 or bullying>0 or profanity>0 or severe>0 or self_harm>0 or dangerous_challenge>0 or grooming>0
                        if grooming:category='GROOMING'
                        elif self_harm:category='SELF_HARM'
                        elif dangerous_challenge:category='DANGEROUS_CHALLENGE'
                        elif severe:category='SEVERE_ABUSE'
                        elif adult:category='SEXUAL_LANGUAGE'
                        elif bullying:category='CYBERBULLYING'
                        else:category='TEXT'
                        toxicity=max(profanity,bullying,severe,self_harm,dangerous_challenge,grooming)
                        return normalize_signals({
                            'adult_score':adult,'sexual_score':adult,'violence_score':severe,'weapon_score':0,
                            'toxicity_score':toxicity,'general_score':max(adult,toxicity,severe),'category':category,
                            'deterministic_grooming':bool(grooming),'deterministic_severe_abuse':bool(severe),
                            'deterministic_self_harm':bool(self_harm),
                            'deterministic_dangerous_challenge':bool(dangerous_challenge),
                            'deterministic_sexual':bool(adult),
                            'total_safety_failure':not deterministic,
                            'partial_safety_failure':bool(deterministic),
                            'errors':['modal_cpu_text_unavailable'],
                            'compute_tier':'modal_cpu_failed_closed',
                        },category='TEXT')
        except Exception:
            # Missing Modal client/config should not change local/test behavior.
            pass

    if enabled():
        try:
            remote=normalize_signals(moderate_text(text),category='TEXT')
            remote['adult_score']=max(float(remote.get('adult_score',0)),adult)
            remote['sexual_score']=max(float(remote.get('sexual_score',0)),adult)
            remote['toxicity_score']=max(float(remote.get('toxicity_score',0)),profanity,bullying,severe,self_harm,dangerous_challenge,grooming)
            remote['general_score']=max(float(remote.get('general_score',0)),remote['adult_score'],remote['toxicity_score'])
            if grooming:remote['category']='GROOMING'
            elif self_harm:remote['category']='SELF_HARM'
            elif dangerous_challenge:remote['category']='DANGEROUS_CHALLENGE'
            elif severe:remote['category']='SEVERE_ABUSE'
            elif adult:remote['category']='SEXUAL_LANGUAGE'
            elif bullying:remote['category']='CYBERBULLYING'
            remote['deterministic_grooming']=bool(grooming)
            remote['deterministic_severe_abuse']=bool(severe)
            remote['deterministic_self_harm']=bool(self_harm)
            remote['deterministic_dangerous_challenge']=bool(dangerous_challenge)
            remote['deterministic_sexual']=bool(adult)
            return normalize_signals(remote,category='TEXT')
        except Exception:
            remote_failed=True

    toxicity=max(profanity,bullying,severe,self_harm,dangerous_challenge,grooming);sexual=adult;ran=0
    errors=['remote_ai_unavailable'] if remote_failed else []
    extras={}
    if text:
        try:
            scores=timed_call('detoxify',lambda:_detox_scores(text),timeout_seconds('detoxify',90));ran+=1
            toxicity=max([toxicity]+[float(v) for k,v in scores.items() if k!='sexual_explicit'])
            sexual=max(float(scores.get('sexual_explicit',0) or 0),adult)
            extras['detoxify_model']=_DETOX_NAME
            extras['detoxify_scores']={k:float(v) for k,v in scores.items()}
        except Exception as exc:
            errors.append('detoxify_timeout' if 'timeout' in str(exc).lower() else ('detoxify_missing_sexual_head' if 'sexual_explicit' in str(exc) else 'detoxify'))
        if env_flag('LITTLENET_ENABLE_TEXT_CLASSIFIER'):
            try:
                h=timed_call('text_classifier',lambda:_optional_hf_scores(text),timeout_seconds('text_classifier',90));ran+=1
                if h:
                    toxicity=max(toxicity,float(h.get('toxicity',0)))
                    sexual=max(sexual,float(h.get('sexual',0)))
                    extras['text_classifier_scores']=h.get('labels',{})
            except Exception as exc:errors.append('text_classifier_timeout' if 'timeout' in str(exc).lower() else 'text_classifier')
        # LittleNet-trained 18+ text classifier (user-staged artifact). Runs
        # last in the local tier so its sexual/violence/toxicity evidence
        # merges by max over deterministic rules, Detoxify, and the optional
        # HF classifier above. Absent artifact (or load failure) degrades to
        # the existing stack, never a bypass.
        try:
            from . import littlenet_trained_text as _trained_text
            if _trained_text.available():
                try:
                    tts = timed_call('trained_text', lambda: _trained_text.predict(text), timeout_seconds('trained_text', 60))
                    sexual = max(sexual, float(tts.get('sexual_score', 0) or 0))
                    toxicity = max(toxicity, float(tts.get('toxicity_score', 0) or 0))
                    # Model violence_score is a probability, virtually never
                    # exactly 0 (e.g. 0.0003 for benign text). Folding it raw
                    # into the lexical `severe` flag would make every message
                    # truthy-severe and hard-block all chat. Threshold it:
                    # only a confident model signal joins the severe tier.
                    trained_violence = float(tts.get('violence_score', 0) or 0)
                    if trained_violence >= 0.60:
                        severe = max(severe, trained_violence)
                    if tts.get('partial_safety_failure'):
                        # The classifier returned scores no bucket could
                        # interpret (e.g. unknown labels): fail closed to
                        # parent review, never a silent ALLOW.
                        tts_errors = [str(e) for e in (tts.get('errors') or []) if e]
                        errors.extend(tts_errors or ['trained_text_partial_failure'])
                    extras['trained_text'] = (tts.get('model_signals') or {}).get('littlenet_trained_text', {})
                    extras['trained_text_model'] = True
                    ran += 1
                except Exception as exc:
                    errors.append('trained_text_timeout' if 'timeout' in str(exc).lower() else 'trained_text')
        except Exception:
            # Trained-text module unavailable: deterministic + Detoxify stack
            # above remains the fail-safe.
            pass

    if grooming:category='GROOMING'
    elif self_harm:category='SELF_HARM'
    elif dangerous_challenge:category='DANGEROUS_CHALLENGE'
    elif severe:category='SEVERE_ABUSE'
    elif sexual>=.4:category='SEXUAL_LANGUAGE'
    elif bullying>=.6:category='CYBERBULLYING'
    else:category='TEXT'

    deterministic=adult>0 or bullying>0 or profanity>0 or severe>0 or self_harm>0 or dangerous_challenge>0 or grooming>0
    result={
        'adult_score':sexual,'sexual_score':sexual,'violence_score':severe,'weapon_score':0,
        'toxicity_score':toxicity,'general_score':max(sexual,toxicity,severe),'category':category,
        'deterministic_grooming':bool(grooming),'deterministic_severe_abuse':bool(severe),
        'deterministic_self_harm':bool(self_harm),
        'deterministic_dangerous_challenge':bool(dangerous_challenge),
        'deterministic_sexual':bool(adult),
        'total_safety_failure':bool(text) and ran==0 and not deterministic,
        'partial_safety_failure':bool(text) and bool(errors) and (ran>0 or deterministic),
        'errors':errors,**extras
    }
    return normalize_signals(result,category='TEXT')
