import unittest
from safety.policy import decide
from services.identity import validate_name,validate_username

class PolicyRuntime(unittest.TestCase):
    def test_adult_always_blocks_even_with_partial_failure(self):
        d=decide({'adult_score':.41,'partial_safety_failure':True,'general_score':.1},'STANDARD')
        self.assertEqual(d.action,'BLOCK');self.assertIn('18+',d.reason)
    def test_weapon_always_blocks(self):
        self.assertEqual(decide({'weapon_score':.8},'STANDARD').action,'BLOCK')
    def test_total_model_failure_fails_closed(self):
        self.assertEqual(decide({'total_safety_failure':True},'STANDARD').action,'BLOCK')
    def test_partial_model_failure_needs_review_if_no_hard_evidence(self):
        self.assertEqual(decide({'partial_safety_failure':True,'general_score':.05},'STRICT').action,'REVIEW')
    def test_safety_levels_only_change_ambiguous_threshold(self):
        s={'violence_score':.5,'general_score':.5}
        self.assertEqual(decide(s,'STANDARD').action,'ALLOW')
        self.assertEqual(decide(s,'STRICT').action,'REVIEW')
        self.assertEqual(decide(s,'VERY_STRICT').action,'REVIEW')
    def test_safe_content_allows(self):
        self.assertEqual(decide({'general_score':.05},'STRICT').action,'ALLOW')
    def test_identity_validation(self):
        self.assertTrue(validate_username('safe.student_1'));self.assertFalse(validate_username('bad space'))
        self.assertTrue(validate_name('Asha Kumar'));self.assertFalse(validate_name('xxx'))

if __name__=='__main__':unittest.main()

class HarmfulTextFallbackTests(unittest.TestCase):
    def test_cyberbullying_lexical_signal_is_high_even_without_model(self):
        import safety.text_service as t
        result=t.check_text('You are useless, nobody likes you')
        self.assertEqual(result['category'],'CYBERBULLYING')
        self.assertGreaterEqual(result['toxicity_score'],0.8)
