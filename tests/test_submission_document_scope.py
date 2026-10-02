"""Keep submission-facing documents aligned with the locked college build."""
from pathlib import Path


ROOT = Path(__file__).parents[1]
CURRENT_DOCS = [
    ROOT / "LITTLENET_FINAL_RELEASE_VERIFICATION.md",
    ROOT / "LITTLENET_COMPLETE_IMPLEMENTATION_REPORT.md",
    ROOT / "LITTLENET_RELEASE_CANDIDATE_REPORT.md",
    ROOT / "docs" / "VIVA_PRESENTATION_GUIDE.md",
]


def _all_current_docs() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in CURRENT_DOCS)


def test_submission_docs_do_not_claim_retired_speech_pipeline_is_active():
    text = _all_current_docs().lower()
    stale_active_claims = [
        "faster-whisper",
        "audio moderation pipeline verified",
        "speech transcription service: external whisper",
        "complete audio moderation pipeline",
        "voice & audio moderation",
        "ffmpeg audio extraction +",
        "whisper detects audio harassment",
    ]
    for claim in stale_active_claims:
        assert claim not in text, f"stale current-scope claim found: {claim}"


def test_submission_docs_state_locked_audio_scope_and_live_deploy_status():
    text = _all_current_docs().lower()
    assert "standalone audio/voice" in text
    assert "intentionally disabled" in text
    assert "video audio is stripped" in text
    assert "modal_token_id" in text
    assert "modal_token_secret" in text
    assert "331" in text
    assert "53/53" in text


def test_viva_guide_has_no_embedded_demo_password_or_aadhaar_claim():
    viva = (ROOT / "docs" / "VIVA_PRESENTATION_GUIDE.md").read_text(encoding="utf-8").lower()
    assert "studentait2026" not in viva
    assert "parentait2026" not in viva
    assert "12-digit mock aadhaar" not in viva
