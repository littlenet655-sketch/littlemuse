"""Tag and hashtag validation and persistence service for LittleNet.

Enforces child-safe manual hashtags:
- Max 10 tags per post/reel
- Strip leading #
- 1-30 chars
- Alphanumeric + underscore only
- Rejects phone numbers / numeric sequences (>= 7 digits)
- Rejects PII via scan_pii
- Rejects duplicates
- Normalizes to lowercase
"""
from __future__ import annotations

import re
from typing import Tuple, List, Optional

from database.connection import execute, fetch_all
from safety.pii_service import scan_pii

TAG_REGEX = re.compile(r"^[a-zA-Z0-9_]{1,30}$")
PHONE_LIKE_REGEX = re.compile(r"\d{7,}")


def validate_and_normalize_tags(
    raw_tags: list[str] | None, child_id: int | None = None
) -> Tuple[List[Tuple[str, str]], Optional[str]]:
    """Validate a list of raw hashtag strings.

    Returns:
        (valid_tags_list, error_string)
        where each item in valid_tags_list is (display_tag, normalized_tag).
    """
    if not raw_tags:
        return [], None

    if len(raw_tags) > 10:
        return [], "max_10_hashtags_allowed"

    seen_normalized: set[str] = set()
    cleaned_tags: List[Tuple[str, str]] = []

    for item in raw_tags:
        if not isinstance(item, str):
            return [], "invalid_hashtag_format"

        display = item.strip().lstrip("#").strip()
        if not display:
            return [], "empty_hashtag"

        if len(display) > 30:
            return [], "hashtag_too_long"

        if not TAG_REGEX.match(display):
            return [], "invalid_hashtag_characters"

        # Disallow phone numbers / contact info hidden in tags
        if display.isdigit() or PHONE_LIKE_REGEX.search(display):
            return [], "hashtag_contains_phone_number"

        # Scan for PII
        pii_res = scan_pii(display)
        if pii_res.get("detected"):
            return [], "hashtag_pii_detected"

        normalized = display.lower()
        if normalized in seen_normalized:
            return [], f"duplicate_hashtag_{normalized}"

        seen_normalized.add(normalized)
        cleaned_tags.append((display, normalized))

    return cleaned_tags, None


def save_post_tags(post_id: int, validated_tags: List[Tuple[str, str]]) -> None:
    """Insert validated tags into post_tags table."""
    for display, normalized in validated_tags:
        execute(
            """INSERT INTO post_tags(post_id, tag, normalized_tag)
               VALUES(%s, %s, %s)
               ON CONFLICT(post_id, normalized_tag) DO NOTHING""",
            (post_id, display, normalized),
        )


def get_post_tags(post_id: int) -> List[str]:
    """Retrieve all display tags for a post."""
    rows = fetch_all("SELECT tag FROM post_tags WHERE post_id=%s ORDER BY tag_id ASC", (post_id,))
    return [r["tag"] for r in rows]
