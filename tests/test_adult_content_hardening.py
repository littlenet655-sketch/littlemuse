import sys
import types

import pytest

from safety.policy import decide
from safety.nsfw_policy import classify_signals
from safety import text_service, visual_service


def _visual(model_signals, category='IMAGE'):
    return {
        'adult_score': 0.0,
        'sexual_score': 0.0,
        'violence_score': 0.0,
        'weapon_score': 0.0,
        'toxicity_score': 0.0,
        'general_score': 0.0,
        'category': category,
        'model_signals': model_signals,
    }


def test_obvious_sexual_solicitation_hard_blocks_even_without_ml():
    signals=text_service.check_text('Please send me nude pics and keep it secret')
    assert signals['deterministic_sexual'] is True
    assert signals['adult_score'] == 1.0
    assert decide(signals, 'STRICT').action == 'BLOCK'


def test_nudenet_medium_score_routes_to_parent_review():
    signals=_visual({'nudenet':0.30})
    result=classify_signals(signals)
    assert result['review'] is True and result['block'] is False
    assert decide(signals, 'STRICT').action == 'REVIEW'


def test_nudenet_high_score_hard_blocks():
    signals=_visual({'nudenet':0.60})
    assert classify_signals(signals)['block'] is True
    assert decide(signals, 'STRICT').action == 'BLOCK'


def test_falconsai_uses_its_own_review_and_block_thresholds():
    assert decide(_visual({'falconsai':0.50}), 'STRICT').action == 'REVIEW'
    assert decide(_visual({'falconsai':0.80}), 'STRICT').action == 'BLOCK'


def test_clip_uses_its_own_visual_thresholds():
    assert decide(_visual({'clip':{'adult':0.50,'sexual':0.50}}), 'STRICT').action == 'REVIEW'
    assert decide(_visual({'clip':{'adult':0.75,'sexual':0.75}}), 'STRICT').action == 'BLOCK'


def test_video_single_frame_nsfw_evidence_is_enforced():
    signals=_visual({
        'sampled_frames':1,
        'frames':[
            {'falconsai':0.76},
        ],
    }, category='VIDEO')
    assert decide(signals, 'STRICT').action == 'BLOCK'


def test_clean_visual_evidence_does_not_false_block():
    signals=_visual({'nudenet':0.05,'falconsai':0.08,'clip':{'adult':0.05,'sexual':0.05}})
    assert decide(signals, 'STRICT').action == 'ALLOW'


def test_detoxify_requires_sexual_explicit_head(monkeypatch):
    class FakeDetoxify:
        def __init__(self, _name):pass
        def predict(self, _text):return {'toxicity':0.01}
    monkeypatch.setitem(sys.modules,'detoxify',types.SimpleNamespace(Detoxify=FakeDetoxify))
    monkeypatch.setattr(text_service,'_DETOX',None)
    monkeypatch.setattr(text_service,'_DETOX_NAME',None)
    monkeypatch.setenv('LITTLENET_DETOXIFY_MODEL','multilingual')
    with pytest.raises(RuntimeError,match='sexual_explicit'):
        text_service._detox_scores('normal sentence')


def test_detoxify_multilingual_sexual_head_is_consumed(monkeypatch):
    class FakeDetoxify:
        def __init__(self, name):self.name=name
        def predict(self, _text):return {'toxicity':0.02,'sexual_explicit':0.83}
    monkeypatch.setitem(sys.modules,'detoxify',types.SimpleNamespace(Detoxify=FakeDetoxify))
    monkeypatch.setattr(text_service,'_DETOX',None)
    monkeypatch.setattr(text_service,'_DETOX_NAME',None)
    monkeypatch.setenv('LITTLENET_DETOXIFY_MODEL','multilingual')
    scores=text_service._detox_scores('contextual explicit text')
    assert scores['sexual_explicit'] == 0.83
    assert text_service._DETOX_NAME == 'multilingual'


def test_three_minute_reel_requests_single_frame(monkeypatch):
    monkeypatch.setattr(visual_service,'video_duration_seconds',lambda _path:180.0)
    monkeypatch.setenv('LITTLENET_VIDEO_SAMPLE_INTERVAL_SECONDS','3')
    monkeypatch.setenv('LITTLENET_VIDEO_MAX_FRAMES','60')
    assert visual_service._video_sample_count('fake.mp4') == 1


def test_short_video_samples_single_frame(monkeypatch):
    monkeypatch.setattr(visual_service,'video_duration_seconds',lambda _path:9.0)
    monkeypatch.setenv('LITTLENET_VIDEO_SAMPLE_INTERVAL_SECONDS','3')
    monkeypatch.setenv('LITTLENET_VIDEO_MAX_FRAMES','60')
    assert visual_service._video_sample_count('fake.mp4') == 1
