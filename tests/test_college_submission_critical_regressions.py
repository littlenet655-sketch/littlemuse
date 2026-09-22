"""Regression tests for the college-submission safety blockers found in the master audit."""
from pathlib import Path
import sys
import types

import pytest


def test_empty_moderation_envelope_fails_closed():
    from safety.common import normalize_signals
    from safety.policy import decide

    signals=normalize_signals(None,category='IMAGE')
    assert signals['total_safety_failure'] is True
    assert 'invalid_signal_envelope' in signals['errors']
    assert decide(signals).action=='BLOCK'


def test_malformed_score_never_becomes_plain_allow():
    from safety.common import normalize_signals
    from safety.policy import decide

    signals=normalize_signals({'category':'TEXT','toxicity_score':'not-a-number'})
    assert signals['partial_safety_failure'] is True
    assert decide(signals).action=='REVIEW'


def test_remote_empty_signals_are_rejected():
    from safety.remote_client import _moderation_signals

    class Response:
        def json(self):return {'ok':True,'signals':{}}

    with pytest.raises(ValueError,match='moderation_signals_missing'):
        _moderation_signals(Response())


def test_mixed_video_frame_failure_routes_to_review(monkeypatch):
    import safety.remote_client as remote
    import safety.video_service as video
    from safety.common import normalize_signals
    from safety.policy import decide

    safe=normalize_signals({
        'category':'IMAGE','adult_score':0.0,'sexual_score':0.0,'violence_score':0.0,
        'weapon_score':0.0,'toxicity_score':0.0,'general_score':0.0,
        'total_safety_failure':False,'partial_safety_failure':False,'errors':[],
    },category='IMAGE')
    failed=normalize_signals({
        'category':'IMAGE','total_safety_failure':True,'errors':['frame_failed'],
    },category='IMAGE')

    monkeypatch.setattr(remote,'enabled',lambda:False)
    monkeypatch.setattr(video,'_video_sample_count',lambda path,max_frames=None:2)
    monkeypatch.setattr(video,'timed_call',lambda name,fn,seconds:([safe,failed],[0],[1]))

    signals=video.check_video('synthetic.mp4')
    assert signals['total_safety_failure'] is False
    assert signals['partial_safety_failure'] is True
    assert decide(signals).action=='REVIEW'


def test_conversation_rechecks_relationship_before_existing_lookup(monkeypatch):
    import childMessage.service as service

    called={'fetch':False}
    monkeypatch.setattr(service,'can_interact',lambda a,b:False)
    def forbidden_fetch(*args,**kwargs):
        called['fetch']=True
        raise AssertionError('existing conversation must not be looked up after revocation')
    monkeypatch.setattr(service,'fetch_one',forbidden_fetch)

    assert service.conversation(10,20) is None
    assert called['fetch'] is False


def test_messages_recheck_current_relationship(monkeypatch):
    import childMessage.service as service

    monkeypatch.setattr(service,'fetch_one',lambda *a,**k:{'child1_id':10,'child2_id':20})
    monkeypatch.setattr(service,'can_interact',lambda a,b:False)
    monkeypatch.setattr(service,'fetch_all',lambda *a,**k:(_ for _ in ()).throw(AssertionError('message rows must not be read')))
    assert service.messages(99,10)==[]




def test_mobile_parent_liveness_route_removed():
    # Parent face/liveness verification was removed from the mobile Parent
    # flow; Android device authentication now gates Parent Mode locally.
    src=(Path(__file__).parents[1]/'mobile/api.py').read_text(encoding='utf-8')
    assert 'def mobile_parent_verify_liveness' not in src
    assert '/api/mobile/v1/auth/parent/verify-liveness' not in src
    assert 'verify_adult_face' not in src
    assert 'PARENT_LIVENESS_VERIFIED' not in src
    assert 'PARENT_LIVENESS_FAILED' not in src


def test_mobile_parent_email_otp_activates_parent_and_returns_login():
    # Email OTP is the final server-side parent activation step: it activates
    # the account and returns a signed-in login response (no pending_token
    # hop and no liveness step).
    src=(Path(__file__).parents[1]/'mobile/api.py').read_text(encoding='utf-8')
    block=src[src.index('def mobile_parent_verify_email'):src.index('def mobile_parent_resend_email')]
    assert "UPDATE users SET account_status='ACTIVE'" in block
    assert '_mobile_login_response(user, "PARENT_EMAIL_OTP")' in block
    assert '_issue_pending_parent' not in block
    assert 'verify-liveness' not in block
    assert 'verify_adult_face' not in block


def test_mobile_parent_no_face_enrollment_on_activation():
    # Parent activation must not enroll any face embedding/profile: the
    # mobile Parent flow performs no selfie capture at all.
    src=(Path(__file__).parents[1]/'mobile/api.py').read_text(encoding='utf-8')
    block=src[src.index('def mobile_parent_verify_email'):src.index('def mobile_parent_resend_email')]
    assert 'store_embedding' not in block
    assert 'face_profiles' not in block
    assert "'LocalBiometricV1'" not in block
    assert "'[]'::jsonb" not in block


def test_short_usage_segments_are_aggregated_before_rounding(monkeypatch):
    import services.usage as usage

    totals=iter(({'total':590},{'total':0}))
    monkeypatch.setattr(usage,'fetch_one',lambda *a,**k:next(totals))
    assert usage.minutes_today(7)==9


def test_contextual_chat_records_final_decision_and_runs_unavailable_fallback():
    src=(Path(__file__).parents[1]/'childMessage/routes.py').read_text(encoding='utf-8')
    assert 'if needs_contextual_eval:' in src
    assert 'if needs_contextual_eval and ai_client.is_k2_available()' not in src
    assert "record(session['user_id'],'MESSAGE',row['child_message_id'],sig,final_decision)" in src


def test_server_recreates_missing_usage_session_before_lock_check():
    src=(Path(__file__).parents[1]/'app.py').read_text(encoding='utf-8')
    assert "if not key or heartbeat(key) is None:" in src
    assert "started=start_session(session['user_id'])" in src
    assert src.index("started=start_session(session['user_id'])") < src.index("locked,_=lock_state(session['user_id'])")


def test_parent_media_uses_canonical_ownership_helper():
    src=(Path(__file__).parents[1]/'app.py').read_text(encoding='utf-8')
    assert "from parent.service import owns" in src
    assert "if not owns(uid,p['child_id'])" in src
    assert "if not owns(uid,m['sender_child_id'])" in src


def test_canonical_parent_ownership_requires_active_parent_and_approved_link():
    src=(Path(__file__).parents[1]/'parent/service.py').read_text(encoding='utf-8')
    assert "p.account_status='ACTIVE'" in src
    assert "m.approved=TRUE" in src
    assert "m.approval_status='APPROVED'" in src
    assert "m.verified_parent_id=%s" in src


def test_admin_moderation_state_and_audit_share_transaction():
    src=(Path(__file__).parents[1]/'admin/routes.py').read_text(encoding='utf-8')
    block=src[src.index('def block_review_event'):src.index('@admin_bp.route(\'/admin/post/')]
    assert '_admin_audit_cursor(cur' in block
    assert block.index('_admin_audit_cursor(cur') < block.index('conn.commit()')
