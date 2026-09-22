from unittest.mock import patch

from safety.chat_context import contextual_chat_risk
from safety.policy import decide, policy_metadata
from safety.text_service import _normalized_text, check_text


def test_spaced_letter_sexual_evasion_is_normalized_and_blocked(monkeypatch):
    monkeypatch.setattr("safety.text_service._detox_scores", lambda _text: {"sexual_explicit": 0.0})
    assert "sendnudes" in _normalized_text("s e n d  n u d e s")
    signals = check_text("s e n d  n u d e s")
    assert decide(signals).action == "BLOCK"


def test_self_harm_and_dangerous_challenge_phrases_are_hard_blocked(monkeypatch):
    monkeypatch.setattr("safety.text_service._detox_scores", lambda _text: {"sexual_explicit": 0.0})
    for text, category in (
        ("I want to end my life", "SELF_HARM"),
        ("Try the blackout challenge", "DANGEROUS_CHALLENGE"),
    ):
        signals = check_text(text)
        assert signals["category"] == category
        assert decide(signals).action == "BLOCK"


def test_multi_turn_grooming_requires_distinct_cue_families():
    history = [
        {"sender_child_id": 1, "message_text": "Keep this a secret"},
        {"sender_child_id": 2, "message_text": "Okay"},
    ]
    result = contextual_chat_risk(history, "Send me a selfie")
    assert result["suspicious"] is True
    assert result["cue_families"] == ["photo_request", "secrecy"]

    benign = contextual_chat_risk(
        [{"sender_child_id": 1, "message_text": "My science project is secret until Friday"}],
        "That sounds fun",
    )
    assert benign["suspicious"] is False


def test_policy_provenance_is_versioned():
    assert policy_metadata() == {
        "policy_name": "littlenet-college-child-safety",
        "policy_version": 1,
    }


def test_r2_worker_misconfiguration_is_retryable_not_missing_media():
    from services.media_processor import process_media_job

    post = {
        "post_id": 99,
        "child_id": 7,
        "media_type": "VIDEO",
        "caption": "",
        "content_category": "Science",
        "audience_age_group": "ALL",
        "is_story": False,
        "is_reel": True,
        "processing_status": "UPLOADED",
        "moderation_status": "PENDING",
        "processing_lease_token": None,
        "processing_lease_expires_at": None,
    }
    claimed = {**post, "processing_status": "PROCESSING", "processing_lease_token": "worker"}
    with patch("services.media_processor.fetch_one", return_value=post), \
         patch("services.media_processor.execute", side_effect=[claimed, None]) as execute, \
         patch("services.media_processor.object_storage.enabled", return_value=False), \
         patch("services.media_processor.Path.is_file", return_value=False):
        result = process_media_job(99, 7, "uploads/r2/quarantine/7/u/source.mp4", "reel")

    assert result == {"ok": False, "error": "r2_storage_unavailable", "retryable": True}
    assert "processing_status='UPLOADED'" in execute.call_args_list[1].args[0]
