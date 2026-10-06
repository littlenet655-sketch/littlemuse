"""Regression coverage for deterministic-vs-probabilistic text safety semantics."""


def test_trained_violence_probability_does_not_become_deterministic_abuse(monkeypatch):
    import safety.remote_client as remote_client
    import safety.text_service as text_service
    from safety import littlenet_trained_text

    monkeypatch.setenv("LITTLENET_AI_SERVER", "1")
    monkeypatch.delenv("LITTLENET_ENABLE_TEXT_CLASSIFIER", raising=False)
    monkeypatch.setattr(remote_client, "enabled", lambda: False)
    monkeypatch.setattr(text_service, "timed_call", lambda _name, fn, _timeout: fn())
    monkeypatch.setattr(
        text_service,
        "_detox_scores",
        lambda _text: {
            "toxicity": 0.0,
            "severe_toxicity": 0.0,
            "obscene": 0.0,
            "identity_attack": 0.0,
            "insult": 0.0,
            "threat": 0.0,
            "sexual_explicit": 0.0,
        },
    )
    monkeypatch.setattr(littlenet_trained_text, "available", lambda: True)
    monkeypatch.setattr(
        littlenet_trained_text,
        "predict",
        lambda _text: {
            "adult_score": 0.0,
            "sexual_score": 0.0,
            "violence_score": 0.80,
            "weapon_score": 0.0,
            "toxicity_score": 0.0,
            "general_score": 0.80,
            "category": "SEVERE_ABUSE",
            "total_safety_failure": False,
            "partial_safety_failure": False,
            "errors": [],
            "model_signals": {
                "littlenet_trained_text": {
                    "labels": {"violence": 0.80},
                    "buckets": {"sexual": 0.0, "violence": 0.80, "toxic": 0.0},
                }
            },
        },
    )

    result = text_service.check_text("A calm travel quote")

    assert result["violence_score"] == 0.80
    assert result["deterministic_severe_abuse"] is False
    assert result["category"] == "TEXT"


def test_true_lexical_severe_abuse_stays_deterministic(monkeypatch):
    import safety.remote_client as remote_client
    import safety.text_service as text_service

    monkeypatch.setenv("LITTLENET_AI_SERVER", "1")
    monkeypatch.setattr(remote_client, "enabled", lambda: False)
    monkeypatch.setattr(text_service, "timed_call", lambda _name, fn, _timeout: fn())
    monkeypatch.setattr(
        text_service,
        "_detox_scores",
        lambda _text: {
            "toxicity": 0.0,
            "severe_toxicity": 0.0,
            "obscene": 0.0,
            "identity_attack": 0.0,
            "insult": 0.0,
            "threat": 0.0,
            "sexual_explicit": 0.0,
        },
    )

    result = text_service.check_text("I will kill you")

    assert result["deterministic_severe_abuse"] is True
    assert result["category"] == "SEVERE_ABUSE"
