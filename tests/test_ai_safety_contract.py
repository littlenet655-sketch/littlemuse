import unittest
from safety.policy import decide, Decision

class TestAISafetyContract(unittest.TestCase):
    def test_adult_hard_block_overrides_everything(self):
        # Even with zero general risk, adult >= 0.40 MUST hard-block
        d = decide({'adult_score': 0.41, 'sexual_score': 0.1, 'weapon_score': 0.0, 'toxicity_score': 0.0})
        self.assertEqual(d.action, 'BLOCK')
        self.assertIn('18+', d.reason)

    def test_weapon_hard_block(self):
        d = decide({'adult_score': 0.0, 'weapon_score': 0.46})
        self.assertEqual(d.action, 'BLOCK')
        self.assertIn('weapon', d.reason.lower())

    def test_total_safety_failure_fails_closed(self):
        # Zero models ran -> total_safety_failure -> BLOCK
        d = decide({'total_safety_failure': True, 'errors': ['clip_timeout', 'yolo_timeout']})
        self.assertEqual(d.action, 'BLOCK')
        self.assertIn('fail closed', d.reason.lower())

    def test_partial_safety_failure_triggers_review(self):
        # Some models ran, some timed out -> partial_safety_failure -> REVIEW
        d = decide({'partial_safety_failure': True, 'general_score': 0.1, 'adult_score': 0.05, 'weapon_score': 0.0})
        self.assertEqual(d.action, 'REVIEW')
        self.assertIn('parent review', d.reason.lower())

    def test_clean_content_allows(self):
        d = decide({'adult_score': 0.02, 'weapon_score': 0.01, 'violence_score': 0.03, 'toxicity_score': 0.01})
        self.assertEqual(d.action, 'ALLOW')

    def test_safety_levels(self):
        # Standard vs Very Strict thresholds
        signals = {'violence_score': 0.40, 'toxicity_score': 0.40}
        # In STANDARD (review_t=0.58), 0.40 is ALLOW
        self.assertEqual(decide(signals, safety_level='STANDARD').action, 'ALLOW')
        # In VERY_STRICT (review_t=0.38), 0.40 is REVIEW
        self.assertEqual(decide(signals, safety_level='VERY_STRICT').action, 'REVIEW')

if __name__ == '__main__':
    unittest.main()
