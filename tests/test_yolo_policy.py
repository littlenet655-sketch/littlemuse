from safety.policy import decide
from safety.yolo_policy import classify_detections, classify_label, dangerous_label_coverage


def _signals(label, confidence):
    return {
        'adult_score': 0.0,
        'sexual_score': 0.0,
        'violence_score': 0.0,
        'weapon_score': 0.0,
        'toxicity_score': 0.0,
        'general_score': 0.0,
        'category': 'IMAGE',
        'model_signals': {
            'yolo': {
                'detections': [
                    {'label': label, 'confidence': confidence},
                ]
            }
        },
    }


def test_openimages_dangerous_label_variants_are_recognized():
    for label in ['Handgun', 'Kitchen knife', 'Axe', 'Rifle', 'Shotgun', 'Grenade', 'Crossbow']:
        assert classify_label(label), label


def test_medium_confidence_dangerous_object_requires_parent_review():
    result = classify_detections([{'label': 'Axe', 'confidence': 0.31}])
    assert result['review'] is True
    assert result['block'] is False
    d = decide(_signals('Axe', 0.31), 'STRICT')
    assert d.action == 'REVIEW'
    assert 'dangerous object' in d.reason.lower()


def test_high_confidence_dangerous_object_hard_blocks():
    result = classify_detections([{'label': 'Kitchen knife', 'confidence': 0.63}])
    assert result['block'] is True
    d = decide(_signals('Kitchen knife', 0.63), 'STRICT')
    assert d.action == 'BLOCK'
    assert 'knife' in d.reason.lower()


def test_safe_object_does_not_trigger_yolo_safety_action():
    result = classify_detections([{'label': 'Backpack', 'confidence': 0.95}])
    assert result['dangerous'] == []
    d = decide(_signals('Backpack', 0.95), 'STRICT')
    assert d.action == 'ALLOW'


def test_video_frame_detections_are_also_enforced():
    signals = {
        'adult_score': 0.0,
        'sexual_score': 0.0,
        'violence_score': 0.0,
        'weapon_score': 0.0,
        'toxicity_score': 0.0,
        'general_score': 0.0,
        'category': 'VIDEO',
        'model_signals': {
            'frames': [
                {'yolo': {'detections': [{'label': 'Handgun', 'confidence': 0.28}]}}
            ]
        },
    }
    assert decide(signals, 'STRICT').action == 'REVIEW'


def test_model_label_coverage_reports_dangerous_classes():
    names = {0: 'Person', 1: 'Handgun', 2: 'Kitchen knife', 3: 'Axe', 4: 'Tree'}
    assert dangerous_label_coverage(names) == ['axe', 'handgun', 'kitchen knife']
