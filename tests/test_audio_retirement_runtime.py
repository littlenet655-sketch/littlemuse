import io

import pytest
from flask import Flask, session

from safety.moderation_service import evaluate
from safety.policy import Decision, decide
import uploadPost.routes as upload_routes


def _safe_signals(category='TEXT'):
    return {
        'adult_score':0.0,
        'sexual_score':0.0,
        'violence_score':0.0,
        'weapon_score':0.0,
        'toxicity_score':0.0,
        'general_score':0.0,
        'category':category,
        'partial_safety_failure':False,
        'total_safety_failure':False,
    }


def _failed_signals(category='IMAGE'):
    data=_safe_signals(category)
    data['total_safety_failure']=True
    data['errors']=['model_unavailable']
    return data


def _bare_view(fn):
    while hasattr(fn,'__wrapped__'):
        fn=fn.__wrapped__
    return fn


def test_retired_audio_evaluate_blocks_without_database_or_model_calls():
    signals,decision=evaluate(999,'AUDIO','unused-path')
    assert decision.action=='BLOCK'
    assert decision.risk==100.0
    assert signals['total_safety_failure'] is True
    assert 'standalone_audio_disabled' in signals.get('errors',[])


def test_media_total_failure_survives_safe_caption_merge():
    merged=upload_routes._merge(_safe_signals('TEXT'),_failed_signals('IMAGE'))
    assert merged['total_safety_failure'] is True
    assert decide(merged).action=='BLOCK'


def test_create_does_not_insert_when_required_media_moderation_totally_fails(monkeypatch):
    app=Flask(__name__)
    app.secret_key='test-only'
    original_evaluate=upload_routes.evaluate

    def fake_evaluate(child_id,content_type,payload,adult_threshold=.40):
        if content_type.upper()=='TEXT':
            return _safe_signals('TEXT'),Decision('ALLOW',0.0,'safe')
        return _failed_signals(content_type.upper()),Decision('BLOCK',100.0,'AI safety unavailable: fail closed')

    monkeypatch.setattr(upload_routes,'evaluate',fake_evaluate)
    monkeypatch.setattr(upload_routes,'safety_level',lambda _child_id:'STRICT')
    monkeypatch.setattr(upload_routes,'record',lambda *a,**k:1)
    monkeypatch.setattr(upload_routes,'parent_notify',lambda *a,**k:None)
    monkeypatch.setattr(upload_routes,'_unlink',lambda *a,**k:None)
    monkeypatch.setattr(upload_routes,'execute',lambda *a,**k:pytest.fail('blocked media must never be inserted'))
    monkeypatch.setattr('safety.pii_service.scan_pii',lambda _text:{'detected':False})

    with app.test_request_context('/'):
        session['user_id']=123
        post_id,decision=upload_routes._create('IMAGE','fake-image','safe caption','Other',path='fake-image')

    assert post_id is None
    assert decision.action=='BLOCK'
    monkeypatch.setattr(upload_routes,'evaluate',original_evaluate)


def test_story_music_is_rejected_before_file_persistence(monkeypatch):
    app=Flask(__name__)
    app.secret_key='test-only'
    monkeypatch.setattr(upload_routes,'controls_for_child',lambda _cid:{'allow_posting':True,'allow_stories':True,'allow_reels':True})
    monkeypatch.setattr(upload_routes,'effective_categories',lambda _cid:['Other'])
    monkeypatch.setattr(upload_routes,'_save',lambda *a,**k:pytest.fail('retired story audio must not be saved'))

    view=_bare_view(upload_routes.upload_post)
    with app.test_request_context(
        '/child/upload-post/',
        method='POST',
        data={
            'kind':'story',
            'content_category':'Other',
            'caption':'safe story',
            'music_file':(io.BytesIO(b'audio'),'music.mp3'),
        },
        content_type='multipart/form-data',
    ):
        session['user_id']=123
        response,status=view()

    assert status==400
    assert response.get_json()['error']=='Story music/audio uploads are disabled in LittleNet'


def test_standalone_audio_upload_is_rejected_before_file_persistence(monkeypatch):
    app=Flask(__name__)
    app.secret_key='test-only'
    monkeypatch.setattr(upload_routes,'controls_for_child',lambda _cid:{'allow_posting':True,'allow_stories':True,'allow_reels':True})
    monkeypatch.setattr(upload_routes,'effective_categories',lambda _cid:['Other'])
    monkeypatch.setattr(upload_routes,'_save',lambda *a,**k:pytest.fail('retired standalone audio must not be saved'))

    view=_bare_view(upload_routes.upload_post)
    with app.test_request_context(
        '/child/upload-post/',
        method='POST',
        data={
            'kind':'post',
            'content_category':'Other',
            'caption':'safe caption',
            'media':(io.BytesIO(b'audio'),'voice.mp3'),
        },
        content_type='multipart/form-data',
    ):
        session['user_id']=123
        response,status=view()

    assert status==400
    assert response.get_json()['error']=='Standalone audio and voice uploads are disabled in LittleNet'
