"""Historical release hardening: legacy web routes share v2 publication policy.

The browser upload route remains live for compatibility; it must never discard
OCR/PII or deterministic text safety evidence merely because v2 uploads use a
different entry point.
"""
from pathlib import Path

from safety.policy import decide
from uploadPost.routes import _merge


ROOT = Path(__file__).resolve().parents[1]


def test_legacy_web_image_upload_preserves_ocr_pii_hard_block():
    text = {"category": "TEXT", "adult_score": 0.0}
    image = {
        "category": "IMAGE",
        "adult_score": 0.0,
        "deterministic_ocr_pii": True,
        "ocr_category": "CONTACT_INFO",
        "total_safety_failure": False,
    }
    signals = _merge(text, image)
    assert signals["deterministic_ocr_pii"] is True
    assert decide(signals).action == "BLOCK"
    assert "OCR" in decide(signals).reason


def test_legacy_web_image_upload_does_not_dilute_caption_or_grooming():
    text = {
        "category": "GROOMING",
        "deterministic_grooming": True,
        "adult_score": 0.0,
        "general_score": 0.0,
    }
    clean_photo = {"category": "IMAGE", "adult_score": 0.0, "general_score": 0.0}
    signals = _merge(text, clean_photo)
    assert signals["deterministic_grooming"] is True
    assert decide(signals).action == "BLOCK"


def test_legacy_web_merger_keeps_visual_provenance_for_calibrated_nsfw_policy():
    signals = _merge(
        {"category": "TEXT", "adult_score": 0.0},
        {
            "category": "IMAGE",
            "adult_score": 0.35,
            "sexual_score": 0.20,
            "model_signals": {"clip": {"adult": 0.35}},
        },
    )
    assert signals["category"] == "IMAGE"
    assert signals["sexual_score"] == 0.20
    assert signals["media_adult_score"] == 0.35
    assert signals["model_signals"]["clip"]["adult"] == 0.35


def test_no_moderation_evidence_must_fail_closed():
    signals = _merge(None, None)
    assert signals["total_safety_failure"] is True
    assert decide(signals).action == "BLOCK"


def test_legacy_web_allowed_post_is_marked_fully_published():
    source = (ROOT / "uploadPost" / "routes.py").read_text(encoding="utf-8")
    create = source.split("def _create(", 1)[1].split("@upload_bp.route('/feed/')", 1)[0]
    assert "is_safe,moderation_status,processing_status,moderation_reason)" in create
    assert create.count("'ALLOWED' if d.action=='ALLOW' else 'REVIEW'") == 2


def test_every_legacy_public_post_surface_rechecks_processing_state():
    source = (ROOT / "services" / "social.py").read_text(encoding="utf-8")
    public_read_functions = [
        "visible_posts", "discoverable_posts", "active_stories", "story_visible_to",
        "post_visible_to", "visible_profile_posts",
    ]
    for name in public_read_functions:
        body = source.split(f"def {name}(", 1)[1].split("\ndef ", 1)[0]
        assert "p.processing_status='ALLOWED'" in body, name
    share = source.split("def is_post_shareable_to(", 1)[1]
    assert "p_sender.get('processing_status') != 'ALLOWED'" in share
    # Do not change the owner's private REVIEW view into a public surface.
    assert "OR (p.child_id=%s AND p.moderation_status='REVIEW')" in source


def test_secondary_verified_parent_receives_safety_notifications(monkeypatch):
    import services.social as social

    captured = []
    query_seen = []
    def fake_fetch(sql, params):
        query_seen.append((sql, params))
        return [
            {"parent_id": 12, "email": "parent1@example.invalid"},
            {"parent_id": 13, "email": "parent2@example.invalid"},
        ]
    monkeypatch.setattr(social, "fetch_all", fake_fetch)
    monkeypatch.setattr(social, "execute", lambda sql, params: captured.append(params))
    social.parent_notify(7, "PARENT_ALERT", "Review your child's post", "/parent/safety/")
    assert "pcm.verified_parent_id" in query_seen[0][0]
    assert query_seen[0][1] == (7,)
    assert [row[0] for row in captured] == [12, 13]
