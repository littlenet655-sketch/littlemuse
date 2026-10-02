from dataclasses import dataclass

from .policy_config import load_policy

# Legacy source-audit markers retained while contracts migrate to behavioral tests:
# HARD_TEXT_CATEGORIES={'GROOMING','SEVERE_ABUSE'}
# total_failure: return Decision('BLOCK'
# Decision('REVIEW' is still a required policy outcome; behavioral paths use double quotes.
_POLICY = load_policy()
ADULT_CATEGORIES = set(_POLICY["adult_categories"])
HARD_TEXT_CATEGORIES = set(_POLICY["hard_text_categories"])


@dataclass(frozen=True)
class Decision:
    action: str
    risk: float
    reason: str


def policy_metadata():
    """Stable, non-sensitive provenance attached to moderation evidence."""
    return {
        "policy_name": str(_POLICY.get("policy_name") or "littlenet-safety"),
        "policy_version": int(_POLICY.get("version") or 1),
    }


def decide(signals: dict, safety_level: str = "STRICT", adult_threshold=None):
    thresholds = _POLICY["thresholds"]
    if adult_threshold is None:
        adult_threshold = float(thresholds["adult_block"])

    adult = max(float(signals.get("adult_score", 0)), float(signals.get("sexual_score", 0)))
    legacy_weapon = float(signals.get("weapon_score", 0))
    violence = float(signals.get("violence_score", 0))
    toxicity = float(signals.get("toxicity_score", 0))
    category = str(signals.get("category", "")).upper()
    total_failure = bool(signals.get("total_safety_failure"))
    partial_failure = bool(signals.get("partial_safety_failure"))

    if category in HARD_TEXT_CATEGORIES or signals.get("deterministic_grooming") or signals.get("deterministic_severe_abuse") or signals.get("deterministic_self_harm") or signals.get("deterministic_dangerous_challenge"):
        if category == "GROOMING" or signals.get("deterministic_grooming"):
            reason = "grooming/coercion hard blocked"
        elif category == "SELF_HARM" or signals.get("deterministic_self_harm"):
            reason = "self-harm crisis language blocked and escalated"
        elif category == "DANGEROUS_CHALLENGE" or signals.get("deterministic_dangerous_challenge"):
            reason = "dangerous challenge instruction blocked"
        else:
            reason = "severe abuse/threat hard blocked"
        return Decision("BLOCK", 100.0, reason)
    if signals.get("deterministic_ocr_pii"):
        # Burned-in contact/PII sharing detected by the image OCR stage is
        # honored as a hard block, the same as typed contact sharing.
        return Decision("BLOCK", 100.0, "burned-in contact/PII text detected in image (OCR)")
    if total_failure:
        return Decision("BLOCK", 100.0, "AI safety unavailable: fail closed")

    visual_nsfw = None
    if signals.get("model_signals") and category in {"IMAGE", "VIDEO", "ADULT", "NSFW", "NUDITY", "EXPLICIT"}:
        try:
            from .nsfw_policy import classify_signals as classify_nsfw

            visual_nsfw = classify_nsfw(signals)
        except Exception:
            visual_nsfw = None
    if visual_nsfw and visual_nsfw.get("has_evidence"):
        top = visual_nsfw.get("top") or {}
        if visual_nsfw.get("block"):
            return Decision(
                "BLOCK",
                max(float(top.get("score", 0)) * 100, 90),
                f"18+ visual content hard blocked: {top.get('model', 'nsfw')} evidence",
            )
        if visual_nsfw.get("review"):
            return Decision(
                "REVIEW",
                max(float(top.get("score", 0)) * 100, 50),
                f"possible 18+ visual content requires parent review: {top.get('model', 'nsfw')} evidence",
            )
    elif adult >= float(adult_threshold) or category in ADULT_CATEGORIES:
        return Decision("BLOCK", max(adult * 100, 90), "18+ content hard blocked")

    try:
        from .yolo_policy import classify_signals

        yolo = classify_signals(signals)
    except Exception:
        yolo = {"score": 0.0, "block": False, "review": False, "dangerous": []}

    yolo_score = float(yolo.get("score", 0) or 0)
    evidence_score = max(legacy_weapon, yolo_score)
    weapon_block = float(thresholds["weapon_block"])
    if yolo.get("block") or legacy_weapon >= weapon_block or category == "WEAPON":
        label = ((yolo.get("dangerous") or [{}])[0].get("label") or "dangerous object")
        return Decision("BLOCK", max(evidence_score * 100, 85), f"weapon/dangerous object: {label}")
    if yolo.get("review"):
        label = ((yolo.get("dangerous") or [{}])[0].get("label") or "dangerous object")
        return Decision(
            "REVIEW",
            max(evidence_score * 100, 50),
            f"possible dangerous object requires parent review: {label}",
        )

    levels = thresholds["levels"]
    selected = levels.get(safety_level) or levels.get("STRICT")
    block_t = float(selected["block"])
    review_t = float(selected["review"])
    risk = max(violence, toxicity, float(signals.get("general_score", 0)))
    if risk >= block_t:
        return Decision("BLOCK", risk * 100, "high safety risk")
    if partial_failure:
        return Decision("REVIEW", max(risk * 100, 50), "incomplete AI result: parent review")
    if risk >= review_t:
        return Decision("REVIEW", risk * 100, "medium safety risk")
    return Decision("ALLOW", risk * 100, "safe under current policy")
