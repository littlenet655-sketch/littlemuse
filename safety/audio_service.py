"""Retired LittleNet audio compatibility shim.

Standalone audio, voice upload and story music are not product features. No
Whisper or audio model is loaded. The active moderation service rejects AUDIO
and VOICE before this module can be reached. The helper below remains only for
legacy imports/tests and historic rows during migration.
"""


def check_audio(_path):
    return {
        'adult_score': 0.0,
        'sexual_score': 0.0,
        'violence_score': 0.0,
        'weapon_score': 0.0,
        'toxicity_score': 0.0,
        'general_score': 1.0,
        'category': 'AUDIO_RETIRED',
        'total_safety_failure': True,
        'partial_safety_failure': False,
        'errors': ['standalone_audio_disabled', 'remote_ai_unavailable'],
    }


def moderate_audio_safely(child_id: int, audio_path: str, duration_sec: float = 0.0, simulated_transcript: str = ""):
    """Compatibility-only evaluation; active routes never call this function."""
    from .policy import decide, Decision

    transcript=(simulated_transcript or '').strip()
    if not transcript:
        signals={
            'adult_score':0.0,'sexual_score':0.0,'violence_score':0.0,'weapon_score':0.0,
            'toxicity_score':0.0,'general_score':0.20,'category':'AUDIO_RETIRED',
            'total_safety_failure':False,'partial_safety_failure':True,
            'requires_human_review':True,'errors':['standalone_audio_disabled'],
        }
        return signals,Decision('REVIEW',50.0,'Retired audio content requires human review')

    from safety.pii_service import scan_pii
    pii=scan_pii(transcript)
    if pii.get('detected') and pii.get('policy_action')=='BLOCK':
        signals={
            'adult_score':0.0,'sexual_score':0.0,'violence_score':0.0,'weapon_score':0.0,
            'toxicity_score':0.0,'general_score':1.0,'category':'AUDIO_PII',
            'total_safety_failure':False,'partial_safety_failure':False,
            'transcript':transcript,'errors':[],
        }
        return signals,Decision('BLOCK',100.0,'Personal contact or phone number sharing in legacy audio transcript')

    from .text_service import check_text
    signals=dict(check_text(transcript))
    signals['category']='AUDIO_RETIRED'
    signals['transcript']=transcript
    signals['partial_safety_failure']=False
    return signals,decide(signals)
