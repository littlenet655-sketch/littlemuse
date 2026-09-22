"""Regression tests: trained-text violence merge threshold + deterministic tiers.

Covers ``safety/text_service.py::check_text()``:

Class 1 -- the >= 0.60 trained-violence merge (commit 5f1c367). The trained
text model's ``violence_score`` is a probability that is virtually never
exactly 0; folding it raw into the lexical ``severe`` flag would make every
message truthy-severe and hard-block all kids' chat. The merge block only
folds it in when ``trained_violence >= 0.60``. These tests pin that boundary.

Class 2 -- defense in depth. Deterministic grooming / contact-request rules
must fire even when the trained model returns all-zero scores.

What is mocked (and what is not):
- ``safety.littlenet_trained_text.available`` / ``.predict`` are
  monkeypatched so the merge block under test runs with controlled scores.
  The merge logic inside ``text_service`` itself is NEVER touched -- it is
  what is exercised.
- ``_detox_scores`` and ``remote_client`` are deliberately NOT mocked.
  ``detoxify`` is not installed in this environment, so ``_detox_scores``
  raises ImportError immediately (fast, deterministic -- no model download);
  ``check_text`` records a 'detoxify' error and continues to the
  trained-text tier. ``remote_client.enabled()`` and
  ``modal_text_moderation.enabled()`` are False without env config, so those
  tiers are skipped by the real code. Nothing here is flaky or network
  dependent.
"""

import pytest

from safety import littlenet_trained_text
from safety import text_service
from safety import policy
from safety import pii_service

#: Benign text used for the threshold tests -- triggers no deterministic
#: rule (verified: no SEVERE_ABUSE_TERMS / grooming / adult substring).
BENIGN_TEXT = "Great science project today!"

#: Exact grooming trigger copied from
#: tests/test_real_app_acceptance_e2e.py::test_04_chat_safety_grooming_blocked.
GROOMING_TEXT = "keep this a secret and send me a private photo alone"

#: Exact PII trigger copied from
#: tests/test_real_app_acceptance_e2e.py::test_03_chat_safety_pii_blocked_and_parent_notified.
PII_TEXT = "Call me at 9876543210 or email test@gmail.com"

#: Deterministic contact-request trigger: matches the
#: r"\\badd me on (?:snap|snapchat|instagram|telegram|whatsapp)\\b"
#: rule in GROOMING_PATTERNS (safety/text_service.py).
CONTACT_REQUEST_TEXT = "add me on snapchat"


def _envelope(violence=0.0, sexual=0.0, toxicity=0.0):
    """Well-formed trained-text signal envelope with controlled scores."""
    return {
        "sexual_score": sexual,
        "violence_score": violence,
        "toxicity_score": toxicity,
        "partial_safety_failure": False,
        "errors": [],
        "model_signals": {},
        "trained_text_model": True,
    }


@pytest.fixture
def trained_model(monkeypatch):
    """Serve a controlled trained-text envelope; the caller sets scores."""
    scores = {"violence": 0.0, "sexual": 0.0, "toxicity": 0.0}
    monkeypatch.setattr(littlenet_trained_text, "available", lambda: True)
    monkeypatch.setattr(
        littlenet_trained_text,
        "predict",
        lambda text: _envelope(
            violence=scores["violence"],
            sexual=scores["sexual"],
            toxicity=scores["toxicity"],
        ),
    )
    return scores


class TestTrainedViolenceThreshold:
    """The trained violence_score merges into the lexical severe flag ONLY
    at trained_violence >= 0.60."""

    def test_059_does_not_merge(self, trained_model):
        trained_model["violence"] = 0.59
        result = text_service.check_text(BENIGN_TEXT)
        assert not result["violence_score"], (
            f"trained violence 0.59 must not merge, got "
            f"violence_score={result['violence_score']}"
        )
        assert result["deterministic_severe_abuse"] is False
        assert result["category"] != "SEVERE_ABUSE"

    def test_060_merges(self, trained_model):
        trained_model["violence"] = 0.60
        result = text_service.check_text(BENIGN_TEXT)
        assert result["violence_score"] == pytest.approx(0.60)
        assert result["deterministic_severe_abuse"] is True
        assert result["category"] == "SEVERE_ABUSE"

    def test_05999_does_not_merge_boundary(self, trained_model):
        # Documents the exact boundary: 0.5999 is still below the threshold.
        trained_model["violence"] = 0.5999
        result = text_service.check_text(BENIGN_TEXT)
        assert not result["violence_score"], (
            f"trained violence 0.5999 must not merge, got "
            f"violence_score={result['violence_score']}"
        )
        assert result["deterministic_severe_abuse"] is False
        assert result["category"] != "SEVERE_ABUSE"


class TestDeterministicRulesSurviveWeakModel:
    """Deterministic rules fire even when the trained model says 'clean'."""

    @pytest.fixture
    def zeroed_model(self, trained_model):
        """All-zero envelope: the model claims the text is perfectly clean."""
        trained_model["violence"] = 0.0
        trained_model["sexual"] = 0.0
        trained_model["toxicity"] = 0.0
        return trained_model

    def test_grooming_rule_fires_with_zeroed_model(self, zeroed_model):
        result = text_service.check_text(GROOMING_TEXT)
        assert result["deterministic_grooming"] is True
        assert result["category"] == "GROOMING"
        # check_text carries no allow/blocked key of its own; the policy
        # layer turns a GROOMING category into a hard block. Assert the
        # message would NOT be allowed via the real policy decision.
        decision = policy.decide(result)
        assert decision.action == "BLOCK", (
            f"grooming text must be blocked by policy, got {decision!r}"
        )

    def test_contact_request_rule_fires_with_zeroed_model(self, zeroed_model):
        # The deterministic contact-request rule lives in GROOMING_PATTERNS
        # ("add me on snapchat" -> r"\\badd me on (?:snap|...)\\b"), so the
        # deterministic flag it raises is deterministic_grooming.
        result = text_service.check_text(CONTACT_REQUEST_TEXT)
        assert result["deterministic_grooming"] is True
        assert result["category"] == "GROOMING"
        assert policy.decide(result).action == "BLOCK"

    def test_pii_blocking_lives_in_api_layer_not_check_text(self, zeroed_model):
        """check_text exposes NO PII-specific deterministic key (honest negative).

        Code evidence (read, not assumed):
        - safety/text_service.py::check_text returns deterministic flags only
          for grooming / severe_abuse / self_harm / dangerous_challenge /
          sexual. No 'pii' key exists in any result branch (local tier,
          modal_cpu tier, remote tier, or the fail-closed branch).
        - Typed-PII blocking happens one layer up: childMessage/routes.py
          calls safety.pii_service.scan_pii(text) and blocks when
          ``detected and policy_action == 'BLOCK'``.
        This test pins the check_text side of that contract: with a zeroed
        model the PII message must NOT gain an invented key, and scan_pii
        itself must still detect and BLOCK it.
        """
        result = text_service.check_text(PII_TEXT)
        assert not any("pii" in str(key).lower() for key in result), (
            "check_text must not invent a pii key; PII blocking belongs to "
            f"the API layer via pii_service.scan_pii. Keys: {sorted(result)}"
        )
        pii = pii_service.scan_pii(PII_TEXT)
        assert pii["detected"] is True
        assert pii["policy_action"] == "BLOCK"
