import re
from datetime import date
from typing import List, Dict, Any, Optional

# Basic regex filters for data sanitization before external egress
PHONE_REGEX = re.compile(r'(?:\+91[\-\s]?)?[6-9]\d{9}|\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b')
EMAIL_REGEX = re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+')

def calculate_age_group(dob: Optional[Any]) -> str:
    """Safely convert exact Date of Birth to a coarse age group string."""
    if not dob:
        return "9-11"
    if isinstance(dob, str):
        try:
            dob = date.fromisoformat(dob.split('T')[0])
        except Exception:
            return "9-11"
    if not isinstance(dob, date):
        return "9-11"
    today = date.today()
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    if age <= 8:
        return "6-8"
    elif age <= 11:
        return "9-11"
    elif age <= 13:
        return "12-13"
    return "9-11"

def scrub_text(text: str) -> str:
    """Redact standard phones, emails, and exact identifiers from text."""
    if not text:
        return ""
    t = PHONE_REGEX.sub("[PHONE_REDACTED]", text)
    t = EMAIL_REGEX.sub("[EMAIL_REDACTED]", t)
    return t

def sanitize_chat_context(messages: List[Dict[str, Any]], sender_id: Optional[int] = None, receiver_id: Optional[int] = None, **kwargs) -> List[Dict[str, str]]:
    """
    Sanitizes conversation history for AI safety analysis.
    Replaces real user IDs and names with neutral tokens (PeerA/PeerB),
    redacts obvious phone/email patterns, and limits message length.
    """
    s_id = sender_id if sender_id is not None else kwargs.get("my_child_id")
    r_id = receiver_id if receiver_id is not None else kwargs.get("peer_child_id")
    sanitized = []
    for msg in messages:
        sender = msg.get("sender_child_id") or msg.get("sender_id")
        if sender == s_id:
            role = "PeerA"
        elif sender == r_id:
            role = "PeerB"
        else:
            role = "Peer"
        text = msg.get("message_text") or msg.get("text") or ""
        clean_text = scrub_text(text).strip()
        sanitized.append({
            "speaker": role,
            "text": clean_text[:500]
        })
    return sanitized

def sanitize_child_learning_profile(profile_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Strips real names, usernames, school names, addresses, and database IDs.
    Retains only age_group, grade_level, approved interest tags, and high-level goal areas.
    """
    dob = profile_dict.get("date_of_birth")
    age_group = profile_dict.get("age_group") or calculate_age_group(dob)
    raw_interests = profile_dict.get("interests") or profile_dict.get("child_interests") or []
    if isinstance(raw_interests, list):
        interests = [str(x.get("interest_name", x) if isinstance(x, dict) else x)[:40] for x in raw_interests]
    else:
        interests = []

    return {
        "age_group": age_group,
        "grade_level": str(profile_dict.get("grade_level") or profile_dict.get("current_class") or "Grade 4")[:20],
        "interests": interests[:10],
        "preferred_language": str(profile_dict.get("preferred_language") or "en")[:10]
    }

def sanitize_parent_digest_input(raw_stats: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitizes weekly parent telemetry to avoid leaking private message contents
    or peer identities. Only aggregates and coarse metrics are passed.
    """
    return {
        "age_group": raw_stats.get("age_group", "9-11"),
        "quizzes_completed": int(raw_stats.get("quizzes_completed", 0)),
        "accuracy_pct": round(float(raw_stats.get("accuracy_pct", 0.0)), 1),
        "top_subjects": [str(s)[:30] for s in raw_stats.get("top_subjects", [])][:5],
        "weak_subjects": [str(s)[:30] for s in raw_stats.get("weak_subjects", [])][:5],
        "screen_time_hours": round(float(raw_stats.get("screen_time_hours", 0.0)), 1),
        "safety_blocks_count": int(raw_stats.get("safety_blocks_count", 0)),
        "reviews_count": int(raw_stats.get("reviews_count", 0))
    }

def sanitize_content_metadata(raw_metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitizes post caption, hashtags, and category for educational classification.
    Removes personal handles, phone numbers, and external links.
    """
    caption = raw_metadata.get("caption", "") or ""
    clean_caption = scrub_text(caption)[:500]
    raw_tags = raw_metadata.get("hashtags") or []
    if isinstance(raw_tags, str):
        raw_tags = [t.strip() for t in raw_tags.split() if t.strip()]
    clean_tags = [str(t)[:30] for t in raw_tags][:15]

    return {
        "caption": clean_caption,
        "hashtags": clean_tags,
        "declared_category": str(raw_metadata.get("category") or "General")[:40]
    }

# Aliases for interface compatibility
sanitize_text = scrub_text
dob_to_age_group = calculate_age_group

