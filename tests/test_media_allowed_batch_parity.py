"""Parity: _media_allowed_many must decide exactly like _media_allowed per ref.

The batch authorizer exists to kill the feed/reels N+1 (~10 sequential DB
round trips per media item). Policy logic must be identical; only data
fetching is batched. fetch_one/fetch_all are mocked at the mobile.api level
and routed by query text; policy helpers are stubbed identically for both.
"""
from contextlib import contextmanager
from unittest.mock import patch

from mobile.api import _media_allowed, _media_allowed_many


CURATED_ROW = {
    "delivery_object_key": "r2:curated/vid1.mp4",
    "original_object_key": None,
    "poster_object_key": "r2:curated/poster1.jpg",
    "thumbnail_object_key": None,
    "content_id": 11,
    "min_age": 6,
    "max_age": 16,
    "publish_status": "PUBLISHED",
    "display_name": "Art & Creative Hobbies",
    "active": True,
    "moderation_status": "ALLOWED",
    "is_safe": True,
}
SOCIAL_ROW = {
    "post_id": 501,
    "child_id": 202,
    "moderation_status": "ALLOWED",
    "is_safe": True,
    "source_media_path": "r2:quarantine/202/pic_src.jpg",
    "media_path": "r2:social/pic.jpg",
    "poster_path": None,
}
REVIEW_ROW = dict(
    SOCIAL_ROW,
    post_id=502,
    moderation_status="REVIEW",
    media_path="r2:quarantine/202/pic.jpg",
    source_media_path="r2:quarantine/202/pic.jpg",
)
BLOCKED_ROW = dict(SOCIAL_ROW, post_id=503, moderation_status="BLOCKED", media_path="r2:social/blocked.jpg")
MSG_ROW = {
    "sender_child_id": 202,
    "receiver_child_id": 303,
    "moderation_status": "ALLOWED",
    "media_path": "r2:messages/m1.jpg",
}
PROF_ROW = {"child_id": 404, "profile_picture": "r2:avatars/a1.jpg"}


def _single_fetch_one(query, params=None):
    q = str(query)
    if "curated_media_assets" in q:
        ref = params[0]
        if ref in ("r2:curated/vid1.mp4", "r2:curated/poster1.jpg"):
            return dict(CURATED_ROW)
        return None
    if "FROM posts" in q:
        ref = params[0]
        for row in (SOCIAL_ROW, REVIEW_ROW, BLOCKED_ROW):
            if ref in (row["media_path"], row["source_media_path"], row["poster_path"]):
                return dict(row)
        return None
    if "FROM child_messages" in q:
        return dict(MSG_ROW) if params[0] == MSG_ROW["media_path"] else None
    if "FROM child_profiles" in q:
        return dict(PROF_ROW) if params[0] == PROF_ROW["profile_picture"] else None
    return None


def _batch_fetch_all(query, params=None):
    q = str(query)
    refs = set(params[0]) if params else set()
    if "curated_media_assets" in q:
        out = []
        if refs & {"r2:curated/vid1.mp4", "r2:curated/poster1.jpg"}:
            out.append(dict(CURATED_ROW))
        return out
    if "FROM posts" in q and "p.post_id = ANY" not in q:
        out = []
        for row in (SOCIAL_ROW, REVIEW_ROW, BLOCKED_ROW):
            paths = {row["media_path"], row["source_media_path"], row["poster_path"]}
            if refs & paths:
                out.append(dict(row))
        return out
    if "FROM child_messages" in q:
        return [dict(MSG_ROW)] if MSG_ROW["media_path"] in refs else []
    if "FROM child_profiles" in q:
        return [dict(PROF_ROW)] if PROF_ROW["profile_picture"] in refs else []
    if "p.post_id = ANY" in q:
        # batched post_visible_to equivalent: only 501 is visible
        return [
            {"post_id": pid, "is_reel": False, "is_story": False}
            for pid in params[0]
            if pid == 501
        ]
    return []


@contextmanager
def _policy_stubs():
    with patch("mobile.api.fetch_one", side_effect=_single_fetch_one), \
         patch("mobile.api.fetch_all", side_effect=_batch_fetch_all), \
         patch("mobile.api.effective_categories", return_value=["Art & Creative Hobbies"]), \
         patch("services.controls.effective_categories", return_value=["Art & Creative Hobbies"]), \
         patch("mobile.api.feature_allowed", return_value=True), \
         patch("mobile.api.can_interact", return_value=True), \
         patch("mobile.api.can_discover_child", return_value=True), \
         patch("mobile.api.owns", side_effect=lambda u, c: (u, c) == (101, 202)), \
         patch("mobile.api.post_visible_to", side_effect=lambda u, pid: {"post_id": pid} if pid == 501 else None), \
         patch("services.social.child_surface_open", return_value=True), \
         patch("services.curated_feed._child_real_age", return_value=10), \
         patch("services.social._age_group", return_value="9-11"):
        yield


def _check_parity(uid, role, refs):
    with _policy_stubs():
        expected = {r: _media_allowed(uid, role, r) for r in refs}
        got = _media_allowed_many(uid, role, refs)
    assert set(got) == set(expected), f"ref set mismatch for role={role}"
    for r in refs:
        assert got[r] == expected[r], f"parity break role={role} ref={r}: single={expected[r]} batch={got[r]}"


def test_batch_parity_child_mixed_refs():
    refs = [
        "r2:curated/vid1.mp4",      # curated allowed
        "r2:curated/poster1.jpg",   # curated allowed (poster column)
        "r2:social/pic.jpg",        # social visible
        "r2:quarantine/202/pic.jpg",  # REVIEW quarantine -> child denied
        "r2:messages/m1.jpg",       # message media, viewer is receiver
        "r2:avatars/a1.jpg",        # profile picture, discoverable
        "r2:unknown/nope.jpg",      # unknown -> denied
        "uploads/profile_pictures/download.webp",  # default avatar -> allowed
    ]
    _check_parity(303, "CHILD", refs)


def test_batch_parity_blocked_post_denied_for_all_roles():
    for role, uid in (("CHILD", 303), ("PARENT", 101), ("ADMIN", 999)):
        _check_parity(uid, role, ["r2:social/blocked.jpg"])


def test_batch_parity_parent_review_preview():
    # REVIEW quarantine: parent owner allowed, non-owner denied, child denied
    _check_parity(101, "PARENT", ["r2:quarantine/202/pic.jpg"])
    _check_parity(102, "PARENT", ["r2:quarantine/202/pic.jpg"])
    _check_parity(303, "CHILD", ["r2:quarantine/202/pic.jpg"])


def test_batch_parity_admin_and_empty():
    _check_parity(999, "ADMIN", ["r2:curated/vid1.mp4", "r2:social/pic.jpg", "r2:unknown/nope.jpg"])
    with _policy_stubs():
        assert _media_allowed_many(303, "CHILD", []) == {}
        assert _media_allowed_many(303, "CHILD", ["r2:social/pic.jpg", "r2:social/pic.jpg"]) == {
            "r2:social/pic.jpg": True
        }


def test_batch_parity_curated_age_gate():
    # Same curated asset, child age outside the asset range -> denied in both.
    refs = ["r2:curated/vid1.mp4"]
    with _policy_stubs(), patch("services.curated_feed._child_real_age", return_value=4):
        expected = {r: _media_allowed(303, "CHILD", r) for r in refs}
        got = _media_allowed_many(303, "CHILD", refs)
    assert got == expected == {"r2:curated/vid1.mp4": False}
