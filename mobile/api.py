from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from functools import wraps
from urllib.parse import quote

from flask import g, jsonify, redirect, request, send_from_directory
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.datastructures import MultiDict

from auth.child_provisioning import create_child_for_verified_parent
from auth.parent_email_otp import (
    begin_parent_registration,
    resend_parent_email_otp,
    verify_parent_email_otp,
)
from auth.password_reset import (
    UNIFORM_RESET_MESSAGE,
    parent_reset_child_password,
    request_password_reset,
    verify_and_reset_password,
)
from auth.service import login_user
from child.service import (
    can_discover_child,
    counts,
    create_child_profile,
    discoverable_child_ids,
    discoverable_children,
    follow_child,
    get_child_profile,
    get_random_children,
    is_follow_pending,
    is_following,
    profile_exists,
    replace_profile_tags,
    unfollow_child,
)
from childMessage.service import conversation, conversations_page, is_peer_typing, messages, set_typing
from config import Config
from database.connection import execute, execute_count, fetch_all, fetch_one, get_db_connection
from extensions import csrf, limiter
from parent.service import children, owns, pending_follows
from parent.api import child_viewing_insights
from quiz.service import (
    age_group,
    complete_required_feed_quiz,
    feed_quiz_state,
    learning_challenges,
    learning_points,
    needs_onboarding_quiz,
    quizzes,
    record_feed_answer,
    record_feed_view,
    required_feed_quiz,
)
from safety.moderation_service import evaluate, record, safety_level
from safety.pii_service import scan_pii
from safety.policy import Decision, decide
from services.behavior import behavior_summary
from services.recommendation_signals import record_signal
from services.controls import (
    SAFE_CATEGORIES,
    controls_for_child,
    effective_categories,
    feature_allowed,
    quiet_hours_state,
    save_controls,
)
from services.curated_feed import (
    _child_real_age,
    authorize_curated_media,
    get_feed_page,
    record_feed_impression,
    search_curated_content,
)
from services.social import (
    active_stories,
    can_interact,
    discoverable_posts,
    notify,
    parent_notify,
    post_visible_to,
    visible_posts,
    visible_profile_posts,
)
from child.search_routes import search_visible_posts, visible_hashtags
from services.audit import log
from services.usage import close_session, heartbeat, lock_state, minutes_today, online_state, start_session

_AUTH_SALT = "littlenet-native-auth-v1"
_PENDING_PARENT_SALT = "littlenet-native-parent-pending-v1"
_TOKEN_TTL = int(os.getenv("LITTLENET_MOBILE_TOKEN_TTL_SECONDS", "86400"))
_PENDING_TTL = 30 * 60

class _InvalidJsonBody(Exception):
    """Raised when a JSON request body is present but is not an object."""

def _json_dict():
    """Return the request JSON body as a dict.

    Missing/empty bodies yield {}. A present-but-non-object JSON body
    (array, string, number, …) raises _InvalidJsonBody, which the mobile
    blueprint turns into a 400 — handlers never operate on a shape they
    did not expect.
    """
    data = request.get_json(silent=True)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise _InvalidJsonBody()
    return data

def _serializer(salt: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(Config.SECRET_KEY, salt=salt)

def _clean(value):
    if isinstance(value, dict):
        blocked = {"password_hash", "approval_token", "verification_token"}
        return {k: _clean(v) for k, v in value.items() if k not in blocked}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    return value

def _issue_token(user: dict, usage_session_key=None) -> str:
    claims = {
        "uid": int(user["user_id"]),
        "role": user["role"],
        "name": user.get("full_name") or user.get("username") or "LittleNet User",
        "sver": int(user.get("session_version") or 1),
    }
    if usage_session_key:
        claims["usage_session_key"] = str(usage_session_key)
    return _serializer(_AUTH_SALT).dumps(claims)

def _revoke_all_user_sessions(user_id: int) -> None:
    """Invalidate all active bearer sessions across devices for this user."""
    execute(
        "UPDATE users SET session_version = COALESCE(session_version, 1) + 1 WHERE user_id=%s",
        (int(user_id),),
    )

def _issue_pending_parent(user_id: int, email: str) -> str:
    return _serializer(_PENDING_PARENT_SALT).dumps({"uid": int(user_id), "email": email})

def _load_pending_parent(token: str):
    try:
        return _serializer(_PENDING_PARENT_SALT).loads(token, max_age=_PENDING_TTL)
    except (BadSignature, SignatureExpired):
        return None

def _bearer_token() -> str:
    header = request.headers.get("Authorization", "")
    if not header.lower().startswith("bearer "):
        return ""
    return header.split(" ", 1)[1].strip()

def _load_claims():
    token = _bearer_token()
    if not token:
        return None
    try:
        return _serializer(_AUTH_SALT).loads(token, max_age=_TOKEN_TTL)
    except (BadSignature, SignatureExpired):
        return None

def _mobile_token_revoked(token: str) -> bool:
    """Check the dedicated revocation store independently of route data lookups.

    Fail-closed: a revocation-store outage must deny the request (True =
    treated as revoked → 401), never silently admit a possibly-revoked token.
    """
    if not token:
        return False
    from database.connection import fetch_one as db_fetch_one

    thash = hashlib.sha256(token.encode()).hexdigest()
    try:
        return bool(
            db_fetch_one(
                "SELECT 1 FROM mobile_token_revocations WHERE token_hash=%s",
                (thash,),
            )
        )
    except Exception as exc:
        logging.getLogger(__name__).exception("revocation-store lookup failed: %s", exc)
        return True

def _require_mobile(*roles):
    allowed = {r.upper() for r in roles}

    def decorator(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            claims = _load_claims()
            if not claims:
                return jsonify(error="mobile_auth_required"), 401
            token = _bearer_token()
            if _mobile_token_revoked(token):
                return jsonify(error="token_revoked"), 401
            user = fetch_one(
                "SELECT user_id,username,full_name,email,role,age,account_status,session_version FROM users WHERE user_id=%s",
                (int(claims.get("uid") or 0),),
            )
            if not user or user.get("account_status") != "ACTIVE":
                return jsonify(error="account_inactive"), 401
            if claims.get("sver") is None or int(claims.get("sver")) != int(user.get("session_version") or 1):
                return jsonify(error="session_revoked"), 401
            if allowed and str(user.get("role") or "").upper() not in allowed:
                return jsonify(error="role_forbidden"), 403
            if str(user.get("role")) != str(claims.get("role")):
                return jsonify(error="token_role_mismatch"), 401
            g.mobile_claims = claims
            g.mobile_user = user
            return fn(*args, **kwargs)

        return wrapped

    return decorator

def _onboarding_state(uid: int) -> dict:
    """Authoritative gate state: only the onboarding quiz gates Kids Mode."""
    quiz_required = bool(feed_quiz_state(uid).get("required") or needs_onboarding_quiz(uid))
    return {"quiz_required": quiz_required}

def _kid_self_resets_today(child_id: int) -> int:
    row = fetch_one(
        "SELECT COUNT(*) as cnt FROM activity_logs WHERE child_id=%s AND activity_type='KID_SCREEN_TIME_SELF_RESET' AND created_at::date=CURRENT_DATE",
        (child_id,),
    )
    return int(row["cnt"]) if row else 0

def _child_gate(feature: str | None = None):
    uid = int(g.mobile_user["user_id"])
    if needs_onboarding_quiz(uid):

        return jsonify(error="onboarding_quiz_required", gate="quiz"), 428
    if feature and not feature_allowed(uid, feature):
        return jsonify(error="disabled_by_parent", feature=feature), 403
    quiet = quiet_hours_state(uid)
    if quiet.get("active"):
        return jsonify(error="quiet_hours", gate="quiet_hours", quiet=_clean(quiet)), 423
    locked, remaining = lock_state(uid)
    if locked:
        used_resets = _kid_self_resets_today(uid)
        return jsonify(
            error="screen_time_limit",
            gate="screen_time",
            remaining=remaining,
            self_resets_used=used_resets,
            self_resets_remaining=max(0, 2 - used_resets),
        ), 423
    if feed_quiz_state(uid).get("required"):
        return jsonify(error="quiz_required", gate="quiz"), 428
    key = (g.mobile_claims or {}).get("usage_session_key")
    if key:
        try:
            heartbeat(key)
        except Exception:
            pass
    return None

def _asset_url(reference, viewer_id=None, viewer_role=None):
    if not reference:
        return None
    from services.media_delivery import resolve_media_delivery

    v_id = viewer_id
    v_role = viewer_role
    if v_id is None and hasattr(g, "mobile_user") and g.mobile_user:
        v_id = g.mobile_user.get("user_id")
        v_role = g.mobile_user.get("role")
    res = resolve_media_delivery(reference, viewer_id=v_id, viewer_role=v_role)
    return res.get("url")

def _profile_json(row):
    if not row:
        return None
    out = dict(row)
    out["avatar_url"] = _asset_url(out.get("profile_picture"))
    out.pop("profile_picture", None)
    return _clean(out)

def _post_json(row, viewer_id=None):
    if not row:
        return None
    out = dict(row)
    v_id = viewer_id
    v_role = None
    if v_id is None and hasattr(g, "mobile_user") and g.mobile_user:
        v_id = g.mobile_user.get("user_id")
        v_role = g.mobile_user.get("role")
    elif v_id and hasattr(g, "mobile_user") and g.mobile_user:
        v_role = g.mobile_user.get("role")

    from services.media_delivery import resolve_media_delivery

    media_res = resolve_media_delivery(out.get("media_path"), viewer_id=v_id, viewer_role=v_role)
    avatar_res = resolve_media_delivery(out.get("profile_picture"), viewer_id=v_id, viewer_role=v_role)
    poster_res = resolve_media_delivery(out.get("poster_path"), viewer_id=v_id, viewer_role=v_role)

    out["media_url"] = media_res.get("url")
    out["avatar_url"] = avatar_res.get("url")
    out["poster_url"] = poster_res.get("url")
    if media_res.get("expires_at"):
        out["playback_expires_at"] = media_res["expires_at"]
    out.pop("media_path", None)
    out.pop("poster_path", None)
    out.pop("profile_picture", None)
    out.pop("story_music_path", None)
    if viewer_id and out.get("post_id"):
        pid = int(out["post_id"])
        out["viewer_liked"] = bool(fetch_one("SELECT 1 FROM likes WHERE post_id=%s AND child_id=%s", (pid, viewer_id)))
        out["viewer_saved"] = bool(fetch_one("SELECT 1 FROM saved_posts WHERE post_id=%s AND child_id=%s", (pid, viewer_id)))
    if out.get("post_id"):
        from services.tag_service import get_post_tags

        out["tags"] = get_post_tags(int(out["post_id"]))

    if out.get("is_story") and (out.get("story_music_id") or out.get("story_music_url")):
        out["story_music"] = {
            "music_id": out.get("story_music_id"),
            "title": out.get("story_music_title") or "Curated Music",
            "artist": out.get("story_music_artist") or "LittleNet",
            "audio_url": out.get("story_music_url"),
            "start_seconds": out.get("story_music_start") or 0,
            "duration_seconds": out.get("story_music_duration") or 30,
        }

    return _clean(out)

def _mobile_user_payload(user):
    profile = None
    quiz_required = False
    posts_seen = 0
    quiz_interval = 4
    if user.get("role") == "CHILD":
        uid = int(user["user_id"])
        profile = _profile_json(get_child_profile(uid))
        q_state = feed_quiz_state(uid)
        quiz_required = bool(q_state.get("required") or needs_onboarding_quiz(uid))
        posts_seen = int(q_state.get("posts_seen", 0))
        quiz_interval = int(q_state.get("interval", 4))
    return {
        "user_id": int(user["user_id"]),
        "username": user.get("username"),
        "full_name": user.get("full_name"),
        "email": user.get("email"),
        "role": user.get("role"),
        "age": user.get("age"),
        "profile": profile,
        "quiz_required": quiz_required,
        "posts_seen": posts_seen,
        "quiz_interval": quiz_interval,
    }

def _mobile_login_response(user, method="PASSWORD"):
    usage_key = None
    if user["role"] == "CHILD":
        started = start_session(user["user_id"])
        usage_key = started.get("session_key") if started else None
    token = _issue_token(user, usage_key)
    response = {
        "ok": True,
        "token": token,
        "auth_method": method,
        "user": _mobile_user_payload(user),
    }
    if user["role"] == "CHILD":
        uid = int(user["user_id"])
        response["onboarding"] = _onboarding_state(uid)
    return jsonify(_clean(response))

def _media_allowed(uid: int, role: str, ref: str) -> bool:
    cur = fetch_one(
        """SELECT cc.content_id, cc.min_age, cc.max_age, cc.publish_status, cat.display_name, cat.active,
                  cma.moderation_status, cma.is_safe
           FROM curated_media_assets cma
           JOIN curated_content cc ON cc.asset_id = cma.asset_id
           JOIN content_categories cat ON cat.category_id = cc.category_id
           WHERE cma.delivery_object_key = %s OR cma.original_object_key = %s OR cma.poster_object_key = %s OR cma.thumbnail_object_key = %s""",
        (ref, ref, ref, ref),
    )
    # Only a positively identified curated row receives curated-media policy.
    # This prevents malformed/adapted query results from widening access to
    # quarantined user uploads.
    if cur and cur.get("content_id") is not None:
        if role in {"ADMIN", "PARENT"}:
            return True
        if role == "CHILD":
            if cur.get("publish_status") != "PUBLISHED" or cur.get("moderation_status") != "ALLOWED" or not cur.get("is_safe"):
                return False
            from services.controls import effective_categories
            from services.curated_feed import _child_real_age

            if not cur.get("active") or cur.get("display_name") not in effective_categories(uid):
                return False
            child_age = _child_real_age(uid)
            return bool(cur["min_age"] <= child_age <= cur["max_age"])

    p = fetch_one(
        """SELECT post_id, child_id, moderation_status, is_safe, source_media_path, media_path, poster_path
           FROM posts
           WHERE media_path=%s OR story_music_path=%s OR poster_path=%s OR source_media_path=%s""",
        (ref, ref, ref, ref),
    )
    if p:
        mod_status = (p.get("moderation_status") or "").upper()
        if mod_status == "BLOCKED":
            return False
        if ref == p.get("source_media_path") or mod_status == "REVIEW":
            if role == "ADMIN":
                return True
            if role == "PARENT":
                return owns(uid, p["child_id"])
            return False
        if role == "ADMIN":
            return True
        if role == "PARENT":
            return owns(uid, p["child_id"])
        if post_visible_to(uid, p["post_id"]):
            return True
    m = fetch_one("SELECT sender_child_id,receiver_child_id,moderation_status FROM child_messages WHERE media_path=%s", (ref,))
    if m:
        if role == "ADMIN":
            return True
        if role == "PARENT":
            return owns(uid, m["sender_child_id"]) and m.get("moderation_status") == "REVIEW"
        if m.get("moderation_status") != "ALLOWED":
            return uid == m["sender_child_id"]
        return uid in {m["sender_child_id"], m["receiver_child_id"]} and can_interact(m["sender_child_id"], m["receiver_child_id"])
    f = fetch_one("SELECT child_id FROM child_profiles WHERE profile_picture=%s", (ref,))
    if f:
        if role == "ADMIN":
            return True
        if role == "PARENT":
            return owns(uid, f["child_id"])
        return can_discover_child(uid, f["child_id"])
    return ref == "uploads/profile_pictures/download.webp" and role in {"CHILD", "PARENT", "ADMIN"}

def _merge_signals(*signals):
    out = {
        "adult_score": 0.0,
        "violence_score": 0.0,
        "weapon_score": 0.0,
        "toxicity_score": 0.0,
        "general_score": 0.0,
        "partial_safety_failure": False,
        "total_safety_failure": False,
        "sources": [],
    }
    valid = [s for s in signals if s]
    if not valid:
        out["total_safety_failure"] = True
        return out
    for sig in valid:
        for key in ("adult_score", "violence_score", "weapon_score", "toxicity_score", "general_score"):
            out[key] = max(float(out.get(key, 0)), float(sig.get(key, 0) or 0))
        out["partial_safety_failure"] = out["partial_safety_failure"] or bool(sig.get("partial_safety_failure"))
        out["total_safety_failure"] = out["total_safety_failure"] or bool(sig.get("total_safety_failure"))
        out["sources"].append(sig.get("category", "UNKNOWN"))
    out["category"] = "ADULT" if out["adult_score"] >= Config.ADULT_HARD_BLOCK_THRESHOLD else "CONTENT"
    return out

def _resolve_parent_review(
    reviewer_id: int,
    event_id: int,
    requested: str,
    is_admin: bool = False,
    notes: str | None = None,
):
    requested = requested.upper()
    if requested not in {"APPROVE", "BLOCK"}:
        return False, "invalid_action"
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM moderation_events WHERE event_id=%s AND decision='REVIEW' AND status='OPEN' FOR UPDATE", (event_id,))
        event = cur.fetchone()
        if not event:
            conn.rollback()
            return False, "not_found"
        if not is_admin and not owns(reviewer_id, event["child_id"]):
            conn.rollback()
            return False, "forbidden"

        status = "ALLOWED" if requested == "APPROVE" else "BLOCKED"
        # Safety: a MESSAGE approval is only effective while the sender/receiver pair is
        # still an unblocked, approved connection. If the relationship broke (or the
        # message row vanished) while the item sat in REVIEW, the approval is safely
        # converted to a block so the message can never be delivered after the fact.
        # Mirrors the web parent review path in parent/routes.py.
        effective = requested
        if event["content_type"] == "MESSAGE" and event.get("content_id") and requested == "APPROVE":
            cur.execute(
                "SELECT sender_child_id,receiver_child_id FROM child_messages WHERE child_message_id=%s FOR UPDATE",
                (event["content_id"],),
            )
            msg_row = cur.fetchone()
            if not msg_row:
                effective = "BLOCK"
            else:
                a, b = msg_row["sender_child_id"], msg_row["receiver_child_id"]
                cur.execute(
                    "SELECT 1 FROM blocked_users WHERE (blocker_id=%s AND blocked_id=%s) OR (blocker_id=%s AND blocked_id=%s)",
                    (a, b, b, a),
                )
                blocked_pair = cur.fetchone()
                cur.execute(
                    """SELECT 1 FROM followers WHERE approved=TRUE AND approval_stage='ACTIVE'
                       AND ((child_id=%s AND following_child_id=%s) OR (child_id=%s AND following_child_id=%s))""",
                    (a, b, b, a),
                )
                connected = cur.fetchone()
                if blocked_pair or not connected:
                    effective = "BLOCK"
            status = "ALLOWED" if effective == "APPROVE" else "BLOCKED"
        p_row = None
        kind = "post"
        pub_media = None
        pub_poster = None
        if event["content_type"] in {"IMAGE", "VIDEO", "AUDIO", "TEXT"} and event.get("content_id"):
            post_id = int(event["content_id"])
            cur.execute("SELECT * FROM posts WHERE post_id=%s FOR UPDATE", (post_id,))
            p_row = cur.fetchone()
            if p_row:
                kind = "reel" if p_row.get("is_reel") else ("story" if p_row.get("is_story") else "post")
            if p_row and p_row.get("source_media_path"):
                media_type = p_row.get("media_type") or "IMAGE"
                if requested == "APPROVE":
                    from services.media_processor import sanitize_and_promote_media
                    try:
                        pub_media, pub_poster = sanitize_and_promote_media(
                            post_id, int(p_row["child_id"]), p_row["source_media_path"], kind, media_type
                        )
                        cur.execute(
                            """UPDATE posts
                               SET media_path=%s, poster_path=%s, moderation_status='ALLOWED',
                                   processing_status='ALLOWED', is_safe=TRUE, processing_completed_at=NOW(),
                                   processing_lease_token=NULL, processing_lease_expires_at=NULL
                               WHERE post_id=%s""",
                            (pub_media, pub_poster, post_id),
                        )
                    except Exception as exc:
                        # Fail-closed: do not publish unsanitized media; compensate if published
                        compensation_failed: list[str] = []
                        if pub_media:
                            from services.media_processor import delete_orphaned_media_refs

                            compensation_failed = delete_orphaned_media_refs(
                                (pub_media, pub_poster), context="review_approve_sanitization_failed"
                            )
                        compensation_note = (
                            f"; orphan_compensation_failed={len(compensation_failed)}"
                            if compensation_failed
                            else ""
                        )
                        cur.execute(
                            """UPDATE posts
                               SET moderation_status='BLOCKED', processing_status='FAILED',
                                   processing_error=%s, is_safe=FALSE, processing_completed_at=NOW(),
                                   processing_lease_token=NULL, processing_lease_expires_at=NULL
                               WHERE post_id=%s""",
                            (f"sanitization_failed: {exc}{compensation_note}", post_id),
                        )
                        cur.execute(
                            "INSERT INTO moderation_reviews(event_id,reviewer_id,action,notes) VALUES(%s,%s,%s,%s)",
                            (event_id, reviewer_id, "BLOCK", "Sanitization failed closed."),
                        )
                        cur.execute("UPDATE moderation_events SET status='RESOLVED' WHERE event_id=%s", (event_id,))
                        if is_admin:
                            cur.execute(
                                """INSERT INTO admin_audit_logs(admin_id,action,target_type,target_id,details)
                                   VALUES(%s,'MODERATION_BLOCK','MODERATION_EVENT',%s,%s::jsonb)""",
                                (reviewer_id, event_id, json.dumps({"result": "sanitization_failed"})),
                            )
                        conn.commit()
                        return False, "sanitization_failed"
                else:  # BLOCK
                    cur.execute(
                        """UPDATE posts
                           SET moderation_status='BLOCKED', processing_status='BLOCKED',
                               is_safe=FALSE, media_path=NULL, processing_completed_at=NOW(),
                               processing_lease_token=NULL, processing_lease_expires_at=NULL
                           WHERE post_id=%s""",
                        (post_id,),
                    )
            else:
                cur.execute(
                    """UPDATE posts
                       SET moderation_status=%s, processing_status=%s, is_safe=%s,
                           processing_lease_token=NULL, processing_lease_expires_at=NULL
                       WHERE post_id=%s""",
                    (status, status, requested == "APPROVE", post_id),
                )
        elif event["content_type"] == "COMMENT" and event.get("content_id"):
            cur.execute("UPDATE comments SET moderation_status=%s WHERE comment_id=%s", (status, event["content_id"]))
        elif event["content_type"] == "MESSAGE" and event.get("content_id"):
            cur.execute("UPDATE child_messages SET moderation_status=%s WHERE child_message_id=%s", (status, event["content_id"]))
        elif event["content_type"] == "USER" and event.get("content_id") and is_admin and requested == "BLOCK":
            cur.execute(
                "UPDATE users SET account_status='SUSPENDED' WHERE user_id=%s AND role='CHILD'",
                (event["content_id"],),
            )

        cur.execute(
            "INSERT INTO moderation_reviews(event_id,reviewer_id,action,notes) VALUES(%s,%s,%s,%s)",
            (event_id, reviewer_id, effective, ("Connection changed; approval safely converted to block." if effective != requested else notes)),
        )
        cur.execute("UPDATE moderation_events SET status='RESOLVED' WHERE event_id=%s", (event_id,))
        if is_admin:
            cur.execute(
                """INSERT INTO admin_audit_logs(admin_id,action,target_type,target_id,details)
                   VALUES(%s,%s,'MODERATION_EVENT',%s,%s::jsonb)""",
                (
                    reviewer_id,
                    f"MODERATION_{effective}",
                    event_id,
                    json.dumps({"child_id": event["child_id"], "content_type": event["content_type"]}),
                ),
            )
        # Commit DB state FIRST before external notifications and storage mutations
        conn.commit()

        # A message that survived REVIEW and was approved must now be delivered like a
        # normal send: the receiver gets a notification so it shows as new/unread.
        # Mirrors the web parent review path in parent/routes.py. BLOCKED messages are
        # never notified and never become visible to the receiver.
        if event["content_type"] == "MESSAGE" and event.get("content_id") and effective == "APPROVE":
            msg = fetch_one(
                "SELECT sender_child_id,receiver_child_id FROM child_messages WHERE child_message_id=%s",
                (event["content_id"],),
            )
            if msg:
                notify(
                    msg["receiver_child_id"],
                    "MESSAGE",
                    "A reviewed message is now available",
                    f"/chat/{msg['sender_child_id']}/",
                    msg["sender_child_id"],
                )

        if p_row:
            post_id = int(p_row["post_id"])
            if requested == "APPROVE":
                from services.publication_lifecycle import refresh_publication_visibility
                refresh_publication_visibility(post_id, int(p_row["child_id"]), is_reel=bool(p_row.get("is_reel")))
                if p_row.get("source_media_path"):
                    from services.media_processor import _notify_approved_followers
                    _notify_approved_followers(post_id, int(p_row["child_id"]), kind)
            if p_row.get("source_media_path"):
                from services.media_processor import block_and_cleanup_quarantine
                block_and_cleanup_quarantine(post_id, p_row["source_media_path"])

        return True, effective
    except Exception:
        conn.rollback()
        if requested == "APPROVE" and pub_media:
            # Compensate orphan published object on commit failure. Failures are
            # logged and queued to the durable outbox inside the helper; the
            # original exception is still re-raised below.
            from services.media_processor import delete_orphaned_media_refs

            delete_orphaned_media_refs((pub_media, pub_poster), context="review_approve_commit_failed")
        raise
    finally:
        conn.close()

def register_mobile_api(bp):
    @bp.errorhandler(_InvalidJsonBody)
    def _invalid_json_body(_exc):
        return jsonify(ok=False, error="invalid_request_body"), 400

    @bp.route("/api/mobile/v1/health")
    def mobile_health():
        return jsonify(ok=True, client="react-native", framework="expo", webview=False, api_versions=[1, 2])

    @bp.route("/api/mobile/v1/auth/login", methods=["POST"])
    @csrf.exempt
    @limiter.limit("30 per minute")
    def mobile_login():
        data = _json_dict()
        identifier = str(data.get("identifier") or data.get("email") or data.get("username") or "").strip()
        password = str(data.get("password") or "")
        mode = str(data.get("mode") or "kids").strip().lower()
        user = login_user(identifier, password)
        if not user:
            return jsonify(error="invalid_credentials"), 401
        expected = {"kids": "CHILD", "parent": "PARENT", "admin": "ADMIN"}.get(mode, "CHILD")
        if user.get("role") != expected:
            # Generic response: never reveal the account's actual role.
            return jsonify(error="invalid_credentials_for_mode"), 401
        if user.get("role") == "PARENT" and user.get("account_status") == "PENDING_APPROVAL":
            return jsonify(
                error="parent_verification_required",
                pending_token=_issue_pending_parent(user["user_id"], user.get("email") or ""),
            ), 428
        if user.get("account_status") != "ACTIVE":
            return jsonify(error="account_inactive"), 403
        return _mobile_login_response(user)

    @bp.route("/api/mobile/v1/auth/logout", methods=["POST"])
    @csrf.exempt
    @_require_mobile("CHILD", "PARENT", "ADMIN")
    def mobile_logout():
        token = _bearer_token()
        if token:
            thash = hashlib.sha256(token.encode()).hexdigest()
            uid = (g.mobile_claims or {}).get("uid")
            # Fail closed: if the revocation store cannot record this logout,
            # do not tell the client it is logged out.
            try:
                execute(
                    "INSERT INTO mobile_token_revocations (token_hash, user_id, revoked_at) VALUES (%s, %s, NOW()) ON CONFLICT (token_hash) DO NOTHING",
                    (thash, uid),
                )
            except Exception as exc:
                logging.getLogger(__name__).exception("logout: revocation-store insert failed: %s", exc)
                return jsonify(error="logout_failed"), 503
            # Atomic kill switch: bump session_version so every bearer token
            # for this user dies even if a revocation-row write raced.
            if uid:
                try:
                    _revoke_all_user_sessions(int(uid))
                except Exception as exc:
                    logging.getLogger(__name__).exception("logout: session_version bump failed: %s", exc)
                    return jsonify(error="logout_failed"), 503
        key = (g.mobile_claims or {}).get("usage_session_key")
        if key:
            try:
                close_session(key)
            except Exception:
                pass
        return jsonify(ok=True)

    @bp.route("/api/mobile/v1/music/curated", methods=["GET"])
    def mobile_curated_music():
        """Return pre-approved royalty-free curated tracks for story creation."""
        rows = fetch_all(
            "SELECT music_id, title, artist, category, audio_url, duration_seconds FROM curated_music WHERE is_active=TRUE ORDER BY music_id ASC"
        )
        return jsonify(ok=True, tracks=_clean(rows or []))

    @bp.route("/api/mobile/v1/auth/parent/register", methods=["POST"])
    @csrf.exempt
    @limiter.limit("20 per hour")
    def mobile_parent_register():
        data = _json_dict()
        try:
            result = begin_parent_registration(data)
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        except Exception:
            return jsonify(error="parent_registration_failed"), 500
        resp = {
            "ok": True,
            "pending_token": _issue_pending_parent(result["user_id"], result["email"]),
            "email_sent": bool(result.get("email_sent")),
        }
        if result.get("dev_code"):
            resp["dev_code"] = result["dev_code"]
        return jsonify(resp)

    @bp.route("/api/mobile/v1/auth/parent/verify-email", methods=["POST"])
    @csrf.exempt
    @limiter.limit("20 per minute")
    def mobile_parent_verify_email():
        data = _json_dict()
        pending = _load_pending_parent(str(data.get("pending_token") or ""))
        if not pending:
            return jsonify(error="pending_verification_expired"), 401
        ok, error, user = verify_parent_email_otp(int(pending["uid"]), str(data.get("otp") or ""))
        if not ok:
            return jsonify(error=error or "invalid_otp"), 400
        # Parent face/liveness verification has been removed from the
        # registration flow (device authentication now gates Parent Mode
        # locally). Email OTP ownership is the final server-side step:
        # activate the parent account here and return a signed-in session.
        # The status predicate is load-bearing: a SUSPENDED/REJECTED parent
        # must not self-reactivate by completing an OTP for a stale pending
        # row. Fail closed when no PENDING_APPROVAL row was flipped.
        activated = execute_count(
            "UPDATE users SET account_status='ACTIVE' WHERE user_id=%s AND role='PARENT' AND account_status='PENDING_APPROVAL'",
            (int(user["user_id"]),),
        )
        if activated != 1:
            return jsonify(error="parent_activation_failed"), 403
        user = fetch_one("SELECT * FROM users WHERE user_id=%s", (int(user["user_id"]),))
        if not user or user.get("account_status") != "ACTIVE":
            return jsonify(error="parent_activation_failed"), 500
        try:
            log(int(user["user_id"]), "PARENT_EMAIL_VERIFIED", {"method": "email_otp"})
        except Exception:
            pass
        return _mobile_login_response(user, "PARENT_EMAIL_OTP")

    @bp.route("/api/mobile/v1/auth/parent/resend-email", methods=["POST"])
    @csrf.exempt
    @limiter.limit("10 per 15 minutes")
    def mobile_parent_resend_email():
        data = _json_dict()
        pending = _load_pending_parent(str(data.get("pending_token") or ""))
        if not pending:
            return jsonify(error="pending_verification_expired"), 401
        ok, error, dev_code = resend_parent_email_otp(int(pending["uid"]), with_code=True)
        resp = {"ok": bool(ok), "error": None if ok else error}
        if dev_code:
            resp["dev_code"] = dev_code
        return jsonify(resp), (200 if ok else 503)

    @bp.route("/api/mobile/v1/auth/parent/email-status", methods=["POST"])
    @csrf.exempt
    @limiter.limit("60 per 15 minutes")
    def mobile_parent_email_status():
        data = _json_dict()
        pending = _load_pending_parent(str(data.get("pending_token") or ""))
        if not pending:
            return jsonify(error="pending_verification_expired"), 401

        email = str(pending.get("email") or "").strip().lower()
        if not email:
            return jsonify(ok=True, status="UNKNOWN", delivery_failed=False)

        try:
            row = fetch_one(
                """SELECT status, updated_at
                   FROM email_delivery_events
                   WHERE LOWER(recipient)=LOWER(%s)
                     AND email_type='PARENT_OTP'
                   ORDER BY updated_at DESC
                   LIMIT 1""",
                (email,),
            )
        except Exception:
            # Older deployments may not have the observability table until the
            # release migration runs. Do not break OTP verification because of it.
            row = None

        status = str((row or {}).get("status") or "UNKNOWN").upper()
        return jsonify(
            ok=True,
            status=status,
            delivery_failed=status in {"BOUNCED", "SUPPRESSED", "FAILED", "COMPLAINED"},
        )

    @bp.route("/api/mobile/v1/auth/forgot-password", methods=["POST"])
    @csrf.exempt
    @limiter.limit("10 per 15 minutes")
    def mobile_forgot_password():
        data = _json_dict()
        identifier = str(data.get("identifier") or "").strip()
        ok, message, details = request_password_reset(identifier)
        if not ok:
            return jsonify(ok=False, error=message), 400
        if not details:
            # Anti-enumeration: no account matched (or no code could be
            # sent), but the response is indistinguishable from success.
            return jsonify(ok=True, message=UNIFORM_RESET_MESSAGE)
        return jsonify(
            ok=True,
            user_id=details["user_id"],
            masked_email=details["masked_email"],
            is_parent_proxy=details["is_parent_proxy"],
            message=message or UNIFORM_RESET_MESSAGE,
        )

    @bp.route("/api/mobile/v1/auth/reset-password", methods=["POST"])
    @csrf.exempt
    @limiter.limit("10 per 15 minutes")
    def mobile_reset_password():
        data = _json_dict()
        try:
            user_id = int(data.get("user_id"))
        except (TypeError, ValueError):
            return jsonify(ok=False, error="Invalid user identifier."), 400
        code = str(data.get("code") or "").strip()
        new_password = str(data.get("new_password") or "")
        ok, msg = verify_and_reset_password(user_id, code, new_password)
        if not ok:
            return jsonify(ok=False, error=msg), 400
        return jsonify(ok=True, message=msg)

    @bp.route("/api/mobile/v1/me")
    @_require_mobile("CHILD", "PARENT", "ADMIN")
    def mobile_me():
        payload = {"ok": True, "user": _mobile_user_payload(g.mobile_user)}
        if str(g.mobile_user.get("role")) == "CHILD":
            payload["onboarding"] = _onboarding_state(int(g.mobile_user["user_id"]))
        return jsonify(_clean(payload))

    @bp.route("/api/mobile/v1/media")
    @_require_mobile("CHILD", "PARENT", "ADMIN")
    def mobile_media():
        ref = str(request.args.get("ref") or "")
        uid = int(g.mobile_user["user_id"])
        role = str(g.mobile_user["role"])
        if not ref or not _media_allowed(uid, role, ref):
            return jsonify(error="media_unavailable"), 404
        if ref.startswith("uploads/r2/"):
            try:
                from services.object_storage import signed_download_url

                return redirect(signed_download_url(ref), 302)
            except Exception:
                return jsonify(error="media_storage_unavailable"), 503
        if not ref.startswith("uploads/"):
            return jsonify(error="invalid_media_reference"), 400
        rel = ref[len("uploads/") :]
        local = os.path.join("uploads", rel)
        if os.path.exists(local):
            return send_from_directory("uploads", rel)
        demo = os.path.join("static", "demo", rel)
        if os.path.exists(demo):
            return send_from_directory(os.path.join("static", "demo"), rel)
        return jsonify(error="media_missing"), 404

    @bp.route("/api/mobile/v1/kids/home")
    @_require_mobile("CHILD")
    def mobile_kids_home():
        gate = _child_gate()
        if gate:
            return gate
        uid = int(g.mobile_user["user_id"])
        if not profile_exists(uid):
            create_child_profile(uid, {"full_name": g.mobile_user.get("full_name") or "Student", "bio": "Hey! I'm on LittleNet 🌟"})
        return jsonify(
            ok=True,
            profile=_profile_json(get_child_profile(uid)),
            stories=[_post_json(p, uid) for p in active_stories(uid)],
            posts=[_post_json(p, uid) for p in visible_posts(uid, False, 20, 0)],
            reels=[_post_json(p, uid) for p in visible_posts(uid, True, 8, 0)],
            suggested=[_clean({**dict(c), "avatar_url": _asset_url(c.get("profile_picture"))}) for c in get_random_children(uid)[:8]],
            controls=_clean(controls_for_child(uid)),
            minutes_today=minutes_today(uid),
        )

    @bp.route("/api/mobile/v1/kids/reels")
    @_require_mobile("CHILD")
    def mobile_kids_reels():
        gate = _child_gate("reels")
        if gate:
            return gate
        uid = int(g.mobile_user["user_id"])
        try:
            page = max(1, int(request.args.get("page", 1)))
        except (TypeError, ValueError):
            page = 1
        rows = visible_posts(uid, True, 10, (page - 1) * 10)
        return jsonify(ok=True, page=page, reels=[_post_json(p, uid) for p in rows])

    @bp.route("/api/mobile/v1/kids/discover")
    @_require_mobile("CHILD")
    def mobile_kids_discover():
        gate = _child_gate("discover")
        if gate:
            return gate
        uid = int(g.mobile_user["user_id"])
        q = str(request.args.get("q") or "").strip()
        if q and scan_pii(q).get("detected"):
            return jsonify(ok=True, pii_warning=True, children=[], posts=[])
        kids = discoverable_children(uid, q.lstrip("#") if q and not q.startswith("#") else None, 30)
        out = []
        for child in kids:
            row = dict(child)
            row["avatar_url"] = _asset_url(row.get("profile_picture"))
            row["is_following"] = is_following(uid, row["user_id"])
            row["is_pending"] = is_follow_pending(uid, row["user_id"])
            row.pop("profile_picture", None)
            out.append(_clean(row))
        posts = visible_posts(uid, False, 30, 0)
        if q:
            needle = q.lstrip("#").casefold()
            posts = [p for p in posts if needle in str(p.get("caption") or "").casefold() or needle in str(p.get("content_category") or "").casefold() or needle in str(p.get("full_name") or "").casefold()]
        return jsonify(ok=True, pii_warning=False, children=out, posts=[_post_json(p, uid) for p in posts])

    @bp.route("/api/mobile/v1/kids/profile", methods=["GET", "PUT"])
    @csrf.exempt
    @_require_mobile("CHILD")
    def mobile_kids_profile():
        gate = _child_gate()
        if gate:
            return gate
        uid = int(g.mobile_user["user_id"])
        if request.method == "PUT":
            data = _json_dict()
            current = get_child_profile(uid) or {}
            merged = dict(current)
            parent_managed = {"school_name", "location", "current_class", "date_of_birth"}
            if any(key in data for key in parent_managed):
                return jsonify(error="profile_field_parent_managed"), 400
            for key in ("full_name", "bio"):
                if key in data:
                    merged[key] = data.get(key)
            public_text = " ".join(str(merged.get(k) or "") for k in ("full_name", "school_name", "location", "current_class", "bio"))
            if scan_pii(public_text).get("detected"):
                return jsonify(error="profile_pii_blocked"), 400
            _, decision = evaluate(uid, "TEXT", public_text)
            if decision.action != "ALLOW":
                return jsonify(error="profile_safety_blocked"), 400
            create_child_profile(uid, merged)
            if any(k in data for k in ("skills", "interests", "ambitions")):
                replace_profile_tags(uid, data.get("skills") or [], data.get("interests") or [], data.get("ambitions") or [])
                parent_notify(uid, "PROFILE_APPROVAL", "Skills/interests/ambitions need approval", "/parent/content-approval/")
        profile = get_child_profile(uid)
        return jsonify(
            ok=True,
            profile=_profile_json(profile),
            counts=_clean(counts(uid)),
            posts=[_post_json(p, uid) for p in visible_profile_posts(uid, uid)],
            controls=_clean(controls_for_child(uid)),
            minutes_today=minutes_today(uid),
        )

    @bp.route("/api/mobile/v1/kids/notifications")
    @_require_mobile("CHILD")
    def mobile_kids_notifications():
        gate = _child_gate()
        if gate:
            return gate
        uid = int(g.mobile_user["user_id"])
        rows = fetch_all(
            """SELECT n.*,u.username actor_username,u.full_name actor_name,cp.profile_picture actor_avatar
               FROM notifications n LEFT JOIN users u ON u.user_id=n.actor_id
               LEFT JOIN child_profiles cp ON cp.child_id=n.actor_id
               WHERE n.user_id=%s ORDER BY n.created_at DESC LIMIT 100""",
            (uid,),
        )
        out = []
        for row in rows:
            item = dict(row)
            item["actor_avatar_url"] = _asset_url(item.pop("actor_avatar", None))
            out.append(_clean(item))
        return jsonify(ok=True, notifications=out)

    @bp.route("/api/mobile/v1/kids/notifications/read", methods=["POST"])
    @csrf.exempt
    @_require_mobile("CHILD")
    def mobile_kids_notifications_read():
        # Smallest safe authoritative mark-read: CHILD bearer only, own rows
        # only, idempotent. Reuses the same notifications table as the web
        # child surface (child/routes.py notifications_read).
        uid = int(g.mobile_user["user_id"])
        data = _json_dict()
        raw_ids = data.get("notification_ids", None)
        if raw_ids is None:
            execute("UPDATE notifications SET is_read=TRUE WHERE user_id=%s", (uid,))
            return jsonify(ok=True, marked="all")
        try:
            ids = [int(x) for x in (raw_ids or [])]
        except (TypeError, ValueError):
            return jsonify(error="invalid_notification_ids"), 400
        if not ids:
            return jsonify(ok=True, marked=0)
        marked = execute_count(
            "UPDATE notifications SET is_read=TRUE WHERE user_id=%s AND notification_id = ANY(%s) AND is_read=FALSE",
            (uid, ids),
        )
        return jsonify(ok=True, marked=marked)

    @bp.route("/api/mobile/v1/kids/messages")
    @_require_mobile("CHILD")
    def mobile_kids_messages():
        gate = _child_gate("messaging")
        if gate:
            return gate
        uid = int(g.mobile_user["user_id"])
        try:
            limit = max(1, min(int(request.args.get("limit", 20)), 50))
        except (TypeError, ValueError):
            limit = 20
        try:
            offset = max(0, int(request.args.get("offset", 0)))
        except (TypeError, ValueError):
            offset = 0
        # Fetch one extra row so has_more reflects whether another page exists.
        rows = conversations_page(uid, limit + 1, offset)
        has_more = len(rows) > limit
        out = []
        for row in rows[:limit]:
            item = dict(row)
            if not can_interact(uid, item["peer_id"]):
                continue
            last = {
                "message_text": item.pop("last_message_text"),
                "message_type": item.pop("last_message_type"),
                "sent_at": item.pop("last_sent_at"),
                "sender_child_id": item.pop("last_sender_child_id"),
                "is_seen": item.pop("last_is_seen"),
            }
            item["peer_avatar_url"] = _asset_url(item.pop("peer_avatar", None))
            item["last_message"] = _clean(last) if last["sent_at"] is not None else None
            out.append(_clean(item))
        return jsonify(ok=True, conversations=out, has_more=has_more)

    @bp.route("/api/mobile/v1/kids/chat/<int:peer_id>", methods=["GET", "POST"])
    @csrf.exempt
    @limiter.limit("60 per minute")
    @_require_mobile("CHILD")
    def mobile_kids_chat(peer_id):
        gate = _child_gate("messaging")
        if gate:
            return gate
        uid = int(g.mobile_user["user_id"])
        cid = conversation(uid, peer_id)
        if not cid:
            return jsonify(error="approved_connection_required"), 403
        if request.method == "GET":
            limit = request.args.get("limit", type=int)
            before_id = request.args.get("before_id", type=int)
            after_id = request.args.get("after_id", type=int)
            execute("UPDATE child_messages SET is_seen=TRUE,seen_at=NOW(),delivered_at=COALESCE(delivered_at,NOW()) WHERE conversation_id=%s AND receiver_child_id=%s AND moderation_status='ALLOWED'", (cid, uid))
            peer = fetch_one("SELECT user_id,username,full_name FROM users WHERE user_id=%s", (peer_id,)) or {}
            rows = messages(cid, uid, limit=limit, before_id=before_id, after_id=after_id)
            out = []
            for row in rows:
                item = dict(row)
                item["media_url"] = _asset_url(item.get("media_path"))
                item.pop("media_path", None)
                out.append(_clean(item))
            return jsonify(ok=True, peer=_clean(peer), messages=out, peer_typing=is_peer_typing(cid, uid))

        data = _json_dict()
        text = str(data.get("message_text") or "").strip()
        if not text:
            return jsonify(error="empty_message"), 400
        if len(text) > Config.MAX_USER_TEXT_CHARS:
            return jsonify(error="message_too_long"), 400
        if not can_interact(uid, peer_id):
            return jsonify(error="approved_connection_required"), 403
        pii = scan_pii(text)
        if pii.get("detected") and pii.get("policy_action") == "BLOCK":
            parent_notify(uid, "MESSAGE_BLOCKED", "Blocked attempt to share phone/contact info", "/parent/safety/")
            return jsonify(blocked=True, error="contact_sharing_blocked"), 400
        signals, local_decision = evaluate(uid, "TEXT", text)
        if local_decision.action == "BLOCK":
            parent_notify(uid, "MESSAGE_BLOCKED", local_decision.reason, "/parent/safety/")
            return jsonify(blocked=True, error="message_blocked", reason=local_decision.reason), 400
        final_decision = local_decision
        triggers = ("secret", "don't tell", "dont tell", "meet", "photo", "selfie", "private", "snap", "insta", "telegram", "phone", "number", "address", "alone")
        recent = fetch_all("SELECT sender_child_id,message_text FROM child_messages WHERE conversation_id=%s ORDER BY sent_at DESC LIMIT 20", (cid,))
        from safety.chat_context import contextual_chat_risk
        context_risk = contextual_chat_risk(recent, text)
        if local_decision.action == "REVIEW" or any(t in text.lower() for t in triggers) or context_risk["suspicious"]:
            if context_risk["suspicious"] and local_decision.action == "ALLOW":
                final_decision = Decision("REVIEW", 50.0, "multi-turn grooming pattern requires review")
                signals["contextual_cue_families"] = context_risk["cue_families"]
                signals["contextual_reason_code"] = context_risk["reason_code"]
            try:
                from services.ai import get_ai_client

                ai = get_ai_client().evaluate_chat_safety(recent, uid, peer_id, text)
                if ai.action == "BLOCK":
                    parent_notify(uid, "MESSAGE_BLOCKED", f"AI detected {ai.primary_category}", "/parent/safety/")
                    return jsonify(blocked=True, error="message_blocked", reason=ai.reason_code), 400
                if ai.action == "REVIEW" and local_decision.action == "ALLOW":
                    final_decision = Decision("REVIEW", max(float(local_decision.risk), float(ai.risk_score) * 100.0), f"contextual safety review: {ai.reason_code}")
            except Exception:
                final_decision = Decision("REVIEW", max(float(local_decision.risk), 50.0), "contextual safety unavailable")
        row = execute(
            "INSERT INTO child_messages(conversation_id,sender_child_id,receiver_child_id,message_type,message_text,moderation_status) VALUES(%s,%s,%s,'TEXT',%s,%s) RETURNING child_message_id",
            (cid, uid, peer_id, text, "ALLOWED" if final_decision.action == "ALLOW" else "REVIEW"),
            returning=True,
        )
        record(uid, "MESSAGE", row["child_message_id"], signals, final_decision)
        try:
            from services.analytics import capture as analytics_capture
            analytics_capture(uid, "message_sent", {"status": final_decision.action})
        except Exception:
            pass
        if final_decision.action == "REVIEW":
            parent_notify(uid, "REVIEW_REQUIRED", "A message needs safety review", "/parent/safety/")
        else:
            sender_name = g.mobile_user.get('full_name') or 'A friend'
            notify(peer_id, "MESSAGE", f"{sender_name} sent you a message", f"/chat/{uid}/", uid)
            try:
                from services.push_notifications import notify_new_chat_message
                notify_new_chat_message(peer_id, sender_name, cid)
            except Exception:
                pass
        return jsonify(ok=True, status=final_decision.action)

    @bp.route("/api/mobile/v1/kids/chat/<int:peer_id>/typing", methods=["POST"])
    @csrf.exempt
    @limiter.limit("20 per minute")
    @_require_mobile("CHILD")
    def mobile_kids_chat_typing(peer_id):
        # Typing heartbeat: ephemeral presence only. Requires the same approved
        # connection as messaging; the TTL is enforced server-side at read time.
        gate = _child_gate("messaging")
        if gate:
            return gate
        uid = int(g.mobile_user["user_id"])
        cid = conversation(uid, peer_id)
        if not cid:
            return jsonify(error="approved_connection_required"), 403
        set_typing(cid, uid)
        return jsonify(ok=True)

    @bp.route("/api/mobile/v1/kids/follow/<int:child_id>", methods=["POST"])
    @csrf.exempt
    @_require_mobile("CHILD")
    def mobile_kids_follow(child_id):
        gate = _child_gate("discover")
        if gate:
            return gate
        uid = int(g.mobile_user["user_id"])
        if child_id == uid:
            return jsonify(error="self_follow"), 400
        if not can_discover_child(uid, child_id):
            return jsonify(error="child_unavailable"), 404
        if is_following(uid, child_id) or is_follow_pending(uid, child_id):
            unfollow_child(uid, child_id)
            return jsonify(ok=True, status="removed")
        follow_child(uid, child_id)
        record_signal(uid, "CREATOR", child_id, "FOLLOW")
        parent_notify(uid, "FOLLOW_REQUEST", "A new connection request needs approval", "/parent/follow-requests/")
        return jsonify(ok=True, status="pending")

    @bp.route("/api/mobile/v1/kids/connections")
    @_require_mobile("CHILD")
    def mobile_kids_connections():
        gate = _child_gate("discover")
        if gate:
            return gate
        uid = int(g.mobile_user["user_id"])
        followers_rows = fetch_all(
            """SELECT DISTINCT u.user_id, u.full_name, u.username, cp.school_name, cp.profile_picture
               FROM followers f
               JOIN users u ON u.user_id = f.child_id
               LEFT JOIN child_profiles cp ON cp.child_id = u.user_id
               WHERE f.following_child_id = %s AND f.approved = TRUE AND f.approval_stage = 'ACTIVE'""",
            (uid,),
        )
        following_rows = fetch_all(
            """SELECT DISTINCT u.user_id, u.full_name, u.username, cp.school_name, cp.profile_picture
               FROM followers f
               JOIN users u ON u.user_id = f.following_child_id
               LEFT JOIN child_profiles cp ON cp.child_id = u.user_id
               WHERE f.child_id = %s AND f.approved = TRUE AND f.approval_stage = 'ACTIVE'""",
            (uid,),
        )
        suggested_raw = discoverable_children(uid, None, 15)

        def _fmt(list_rows, is_fol=True):
            out = []
            for r in list_rows:
                d = dict(r)
                d["avatar_url"] = _asset_url(d.pop("profile_picture", None))
                d["is_following"] = is_fol
                d["is_pending"] = False
                out.append(_clean(d))
            return out

        out_sug = []
        for s in suggested_raw:
            d = dict(s)
            d["avatar_url"] = _asset_url(d.pop("profile_picture", None))
            d["is_following"] = is_following(uid, d["user_id"])
            d["is_pending"] = is_follow_pending(uid, d["user_id"])
            out_sug.append(_clean(d))

        return jsonify(
            ok=True,
            followers=_fmt(followers_rows, False),
            following=_fmt(following_rows, True),
            suggested=out_sug,
        )

    @bp.route("/api/mobile/v1/kids/connections/requests")
    @_require_mobile("CHILD")
    def mobile_kids_requests():
        gate = _child_gate("discover")
        if gate:
            return gate
        uid = int(g.mobile_user["user_id"])
        incoming = fetch_all(
            """SELECT f.id, f.child_id as requester_id, u.full_name as requester_name, u.username as requester_username,
                      cp.profile_picture, cp.school_name, f.created_at, f.approval_stage
               FROM followers f
               JOIN users u ON u.user_id = f.child_id
               LEFT JOIN child_profiles cp ON cp.child_id = u.user_id
               WHERE f.following_child_id = %s AND f.approved = FALSE""",
            (uid,),
        )
        outgoing = fetch_all(
            """SELECT f.id, f.following_child_id as target_id, u.full_name as target_name, u.username as target_username,
                      cp.profile_picture, cp.school_name, f.created_at, f.approval_stage
               FROM followers f
               JOIN users u ON u.user_id = f.following_child_id
               LEFT JOIN child_profiles cp ON cp.child_id = u.user_id
               WHERE f.child_id = %s AND f.approved = FALSE""",
            (uid,),
        )

        def _fmt_req(rows, is_inc=True):
            out = []
            for r in rows:
                d = dict(r)
                d["avatar_url"] = _asset_url(d.pop("profile_picture", None))
                d["is_incoming"] = is_inc
                out.append(_clean(d))
            return out

        return jsonify(
            ok=True,
            incoming=_fmt_req(incoming, True),
            outgoing=_fmt_req(outgoing, False),
        )

    @bp.route("/api/mobile/v1/kids/posts/<int:post_id>/like", methods=["POST"])
    @csrf.exempt
    @_require_mobile("CHILD")
    def mobile_like(post_id):
        gate = _child_gate()
        if gate:
            return gate
        uid = int(g.mobile_user["user_id"])
        post = post_visible_to(uid, post_id)
        if not post:
            return jsonify(error="post_not_found"), 404
        if post["child_id"] != uid and not can_interact(uid, post["child_id"]):
            return jsonify(error="approved_connection_required"), 403
        exists = fetch_one("SELECT 1 FROM likes WHERE post_id=%s AND child_id=%s", (post_id, uid))
        if exists:
            execute("DELETE FROM likes WHERE post_id=%s AND child_id=%s", (post_id, uid))
            liked = False
        else:
            execute("INSERT INTO likes(post_id,child_id) VALUES(%s,%s)", (post_id, uid))
            liked = True
            record_signal(uid, "SOCIAL", post_id, "LIKE")
            owner_id = post["child_id"]
            if owner_id != uid and can_interact(owner_id, uid):
                actor_name = g.mobile_user.get('full_name') or 'A friend'
                notify(owner_id, "LIKE", f"{actor_name} liked your post", f"/post/{post_id}", uid)
                try:
                    from services.push_notifications import notify_new_like
                    notify_new_like(owner_id, actor_name, post_id)
                except Exception:
                    pass
        count = (fetch_one("SELECT COUNT(*) n FROM likes WHERE post_id=%s", (post_id,)) or {"n": 0})["n"]
        return jsonify(ok=True, liked=liked, likes=count)

    @bp.route("/api/mobile/v1/kids/posts/<int:post_id>/save", methods=["POST"])
    @csrf.exempt
    @_require_mobile("CHILD")
    def mobile_save_post(post_id):
        gate = _child_gate()
        if gate:
            return gate
        uid = int(g.mobile_user["user_id"])
        if not post_visible_to(uid, post_id):
            return jsonify(error="post_not_found"), 404
        exists = fetch_one("SELECT 1 FROM saved_posts WHERE child_id=%s AND post_id=%s", (uid, post_id))
        if exists:
            execute("DELETE FROM saved_posts WHERE child_id=%s AND post_id=%s", (uid, post_id))
            saved = False
        else:
            execute("INSERT INTO saved_posts(child_id,post_id) VALUES(%s,%s) ON CONFLICT DO NOTHING", (uid, post_id))
            saved = True
            record_signal(uid, "SOCIAL", post_id, "SAVE")
        return jsonify(ok=True, saved=saved)

    @bp.route("/api/mobile/v1/kids/posts/<int:post_id>/comments", methods=["GET"])
    @bp.route("/api/mobile/v1/kids/posts/<int:post_id>/comment", methods=["GET", "POST"])
    @csrf.exempt
    @_require_mobile("CHILD")
    def mobile_comment(post_id):
        gate = _child_gate()
        if gate:
            return gate
        uid = int(g.mobile_user["user_id"])
        post = post_visible_to(uid, post_id)
        if not post:
            return jsonify(error="post_not_found"), 404
        if request.method == "GET":
            rows = fetch_all(
                """SELECT c.comment_id, c.post_id, c.child_id, c.comment_text, c.created_at,
                          u.full_name, u.username, cp.profile_picture
                   FROM comments c
                   JOIN users u ON u.user_id = c.child_id
                   LEFT JOIN child_profiles cp ON cp.child_id = c.child_id
                   WHERE c.post_id = %s AND c.moderation_status = 'ALLOWED'
                   ORDER BY c.created_at ASC""",
                (post_id,),
            )
            out = []
            for r in rows:
                item = dict(r)
                item["avatar_url"] = _asset_url(item.pop("profile_picture", None))
                out.append(_clean(item))
            return jsonify(ok=True, comments=out)
        text = str((_json_dict()).get("text") or "").strip()
        if not text:
            return jsonify(error="empty_comment"), 400
        if len(text) > Config.MAX_USER_TEXT_CHARS:
            return jsonify(error="comment_too_long"), 400
        pii = scan_pii(text)
        if pii.get("detected") and pii.get("policy_action") == "BLOCK":
            parent_notify(uid, "COMMENT_BLOCKED", "Attempted contact/PII sharing in comment", "/parent/safety/")
            return jsonify(blocked=True, error="contact_sharing_blocked"), 400
        signals, decision = evaluate(uid, "TEXT", text)
        if decision.action == "BLOCK":
            record(uid, "COMMENT", None, signals, decision)
            parent_notify(uid, "COMMENT_BLOCKED", decision.reason, "/parent/safety/")
            return jsonify(blocked=True, error="comment_blocked", reason=decision.reason), 400
        row = execute(
            "INSERT INTO comments(post_id,child_id,comment_text,moderation_status) VALUES(%s,%s,%s,%s) RETURNING comment_id",
            (post_id, uid, text, "ALLOWED" if decision.action == "ALLOW" else "REVIEW"),
            returning=True,
        )
        if decision.action == "ALLOW":
            record_signal(uid, "SOCIAL", post_id, "COMMENT")
            owner_id = post["child_id"]
            if owner_id != uid and can_interact(owner_id, uid):
                actor_name = g.mobile_user.get('full_name') or 'A friend'
                notify(owner_id, "COMMENT", f"{actor_name} commented on your post", f"/post/{post_id}", uid)
                try:
                    from services.push_notifications import notify_new_comment
                    notify_new_comment(owner_id, actor_name, post_id)
                except Exception:
                    pass
        record(uid, "COMMENT", row["comment_id"], signals, decision)
        if decision.action == "REVIEW":
            parent_notify(uid, "REVIEW_REQUIRED", "A comment needs review", "/parent/safety/")
        return jsonify(ok=True, status=decision.action, comment_id=row["comment_id"])

    # --- Post/story safe delete (soft-delete + durable R2 media cleanup) ---
    # Convention: posts has no is_deleted column (unlike child_messages). The
    # dominant visibility convention (services/social.py feed/story/reel/profile
    # queries, _media_allowed) is moderation_status='ALLOWED' AND is_safe=TRUE,
    # and the CHECK on posts.moderation_status only permits
    # PENDING/ALLOWED/REVIEW/BLOCKED, so soft-delete = BLOCKED + is_safe=FALSE
    # with moderation_reason='user_deleted' marking an owner/parent delete.
    def _mobile_soft_delete_post_row(post):
        """Shared soft-delete + cleanup for owner/parent post deletion.

        Caller must have loaded and authorized the post row. Returns
        "already_deleted" when the row was already soft-deleted by this flow;
        otherwise performs the soft-delete, enqueues R2 media references, and
        hard-deletes engagement rows (likes/comments/saves/story views) that
        would otherwise dangle visibly.
        """
        from services.media_outbox import enqueue_post_media_deletes

        if str(post.get("moderation_reason") or "") == "user_deleted":
            return "already_deleted"
        execute(
            """UPDATE posts
               SET moderation_status='BLOCKED', is_safe=FALSE,
                   moderation_reason='user_deleted'
               WHERE post_id=%s""",
            (post["post_id"],),
        )
        enqueue_post_media_deletes(post, source_id=post["post_id"])
        execute("DELETE FROM likes WHERE post_id=%s", (post["post_id"],))
        execute("DELETE FROM comments WHERE post_id=%s", (post["post_id"],))
        execute("DELETE FROM saved_posts WHERE post_id=%s", (post["post_id"],))
        execute("DELETE FROM story_views WHERE post_id=%s", (post["post_id"],))
        return "deleted"

    @bp.route("/api/mobile/v1/kids/posts/<int:post_id>", methods=["DELETE"])
    @csrf.exempt
    @_require_mobile("CHILD")
    def mobile_kids_delete_post(post_id):
        gate = _child_gate()
        if gate:
            return gate
        uid = int(g.mobile_user["user_id"])
        post = fetch_one(
            """SELECT post_id, child_id, is_story, moderation_reason,
                      media_path, source_media_path, poster_path, story_music_path
               FROM posts WHERE post_id=%s""",
            (post_id,),
        )
        if not post:
            return jsonify(error="not_found"), 404
        if int(post["child_id"]) != uid:
            return jsonify(error="forbidden"), 403
        if _mobile_soft_delete_post_row(post) == "already_deleted":
            return jsonify(error="already_deleted"), 403
        return jsonify(ok=True)

    @bp.route("/api/mobile/v2/kids/stories/<int:story_id>", methods=["DELETE"])
    @csrf.exempt
    @_require_mobile("CHILD")
    def mobile_kids_delete_story(story_id):
        gate = _child_gate("stories")
        if gate:
            return gate
        uid = int(g.mobile_user["user_id"])
        story = fetch_one(
            """SELECT post_id, child_id, is_story, moderation_reason,
                      media_path, source_media_path, poster_path, story_music_path
               FROM posts WHERE post_id=%s""",
            (story_id,),
        )
        if not story or not story.get("is_story"):
            return jsonify(error="not_found"), 404
        if int(story["child_id"]) != uid:
            return jsonify(error="forbidden"), 403
        if _mobile_soft_delete_post_row(story) == "already_deleted":
            return jsonify(error="already_deleted"), 403
        return jsonify(ok=True)

    @bp.route("/api/mobile/v1/parent/posts/<int:post_id>", methods=["DELETE"])
    @csrf.exempt
    @_require_mobile("PARENT")
    def mobile_parent_delete_post(post_id):
        # No bearer-native parent post delete/block route existed in
        # mobile/api.py; this is the minimal one: same soft-delete semantics,
        # gated by the canonical parent-child mapping check. 404 (not 403) on
        # a failed mapping so post ids cannot be probed across families.
        pid = int(g.mobile_user["user_id"])
        post = fetch_one(
            """SELECT post_id, child_id, moderation_reason,
                      media_path, source_media_path, poster_path, story_music_path
               FROM posts WHERE post_id=%s""",
            (post_id,),
        )
        if not post or not owns(pid, int(post["child_id"])):
            return jsonify(error="not_found"), 404
        if _mobile_soft_delete_post_row(post) == "already_deleted":
            return jsonify(error="already_deleted"), 403
        return jsonify(ok=True)

    @bp.route("/api/mobile/v1/kids/posts", methods=["POST"])
    @csrf.exempt
    @limiter.limit("30 per hour")
    @_require_mobile("CHILD")
    def mobile_create_post():
        # Retired (integration hardening): synchronous multipart upload-through-Flask
        # contradicts the v2 direct-R2-quarantine pipeline (AGENTS.md rules 6/7).
        # Use POST /api/mobile/v2/uploads/session -> R2 PUT -> complete -> status.
        return jsonify(error="deprecated_use_v2_upload", use="/api/mobile/v2/uploads/session"), 410

    @bp.route("/api/mobile/v2/uploads/session", methods=["POST"])
    @csrf.exempt
    @limiter.limit("30 per hour")
    @_require_mobile("CHILD")
    def mobile_v2_upload_session():
        uid = int(g.mobile_user["user_id"])
        data = request.get_json(silent=True) or request.form or {}
        kind = str(data.get("kind") or "post").lower()
        if kind not in {"post", "reel", "story"}:
            return jsonify(error="invalid_kind"), 400

        feature = "reels" if kind == "reel" else "stories" if kind == "story" else "posting"
        gate = _child_gate(feature)
        if gate:
            return gate
        filename = str(data.get("filename") or "").strip()
        media_type = str(data.get("media_type") or "").upper()
        if not media_type:
            ct = str(data.get("content_type") or data.get("mime_type") or "").lower()
            if ct.startswith("image/"):
                media_type = "IMAGE"
            elif ct.startswith("video/"):
                media_type = "VIDEO"
            else:
                ext_test = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
                if ext_test in {"jpg", "jpeg", "png", "webp"}:
                    media_type = "IMAGE"
                elif ext_test in {"mp4", "mov", "webm", "mkv"}:
                    media_type = "VIDEO"
                elif kind in {"reel", "story_video"}:
                    media_type = "VIDEO"
                else:
                    media_type = "IMAGE"

        if media_type not in {"IMAGE", "VIDEO"}:
            return jsonify(error="invalid_media_type"), 400

        try:
            size_bytes = int(data.get("size_bytes") or data.get("file_size") or 0)
        except (ValueError, TypeError):
            return jsonify(error="invalid_file_size"), 400

        if size_bytes <= 0:
            return jsonify(error="file_size_required"), 400

        if media_type == "IMAGE":
            max_bytes = 20 * 1024 * 1024
        elif kind == "story":
            max_bytes = 50 * 1024 * 1024
        else:
            max_bytes = Config.MAX_CONTENT_LENGTH

        if size_bytes > max_bytes:
            return jsonify(error="file_size_exceeded", max_bytes=max_bytes), 400

        ext = str(data.get("extension") or "").lower().lstrip(".")
        if not ext and filename and "." in filename:
            ext = filename.rsplit(".", 1)[-1].lower().lstrip(".")
        if not ext:
            ext = "jpg" if media_type == "IMAGE" else "mp4"

        mime_type = str(data.get("mime_type") or data.get("content_type") or "").lower().strip()
        if not mime_type:
            if media_type == "IMAGE":
                mime_type = "image/jpeg" if ext in {"jpg", "jpeg"} else f"image/{ext}"
            else:
                mime_type = "video/mp4" if ext == "mp4" else f"video/{ext}"
        elif mime_type == "image/jpg":
            mime_type = "image/jpeg"

        if media_type == "IMAGE":
            valid_exts = {"jpg", "jpeg", "png", "webp"}
            valid_mimes = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
        else:
            valid_exts = {"mp4", "mov", "webm", "mkv"}
            valid_mimes = {"video/mp4", "video/quicktime", "video/webm", "video/x-matroska"}

        if ext not in valid_exts:
            return jsonify(error="unsupported_extension", allowed=sorted(list(valid_exts))), 400
        if mime_type and mime_type not in valid_mimes:
            return jsonify(error="unsupported_mime_type", allowed=sorted(list(valid_mimes))), 400

        upload_id = str(uuid.uuid4())
        object_key = f"uploads/r2/quarantine/{uid}/{upload_id}/source.{ext}"
        expires_seconds = 900
        expires_at = datetime.utcnow() + timedelta(seconds=expires_seconds)

        execute(
            """INSERT INTO upload_sessions(upload_id, child_id, object_key, media_type, kind,
                                          expected_size_bytes, mime_type, extension, status, expires_at)
               VALUES(%s, %s, %s, %s, %s, %s, %s, %s, 'PENDING', %s)""",
            (
                upload_id,
                uid,
                object_key,
                media_type,
                kind.upper(),
                size_bytes,
                mime_type,
                ext,
                expires_at,
            ),
        )

        from services import object_storage

        if os.environ.get("FORCE_DIRECT_UPLOAD_UNAVAILABLE") == "1" or os.environ.get("DIRECT_UPLOAD_UNAVAILABLE") == "1":
            return jsonify(
                error="direct_upload_unavailable",
                fallback_allowed=not Config._PRODUCTION,
            ), 503

        if object_storage.enabled():
            upload_url = object_storage.signed_upload_url(
                object_key, content_type=mime_type, expires_seconds=expires_seconds
            )
        elif Config._PRODUCTION and not os.getenv("PYTEST_CURRENT_TEST"):
            return jsonify(
                error="storage_configuration_error",
                fallback_allowed=False,
            ), 500
        else:
            upload_url = f"{Config.BASE_URL}/api/mobile/v2/uploads/mock-put/{upload_id}"

        return jsonify(
            ok=True,
            upload_id=upload_id,
            upload_url=upload_url,
            object_key=object_key,
            expires_at=expires_at.isoformat() + "Z",
            required_headers={"Content-Type": mime_type},
        )

    @bp.route("/api/mobile/v2/uploads/mock-put/<upload_id>", methods=["PUT"])
    @csrf.exempt
    def mobile_v2_mock_put(upload_id):
        # PRODUCTION GUARD: mock-PUT is a dev/CI convenience only.
        # Disabled whenever the server runs under HTTPS or when the explicit
        # opt-in env var ENABLE_MOCK_PUT is not set to "1".
        from config import Config  # avoid circular at module level

        if Config._PRODUCTION or os.environ.get("ENABLE_MOCK_PUT", "0") != "1":
            return jsonify(error="not_found"), 404
        session_row = fetch_one("SELECT * FROM upload_sessions WHERE upload_id=%s", (upload_id,))
        if not session_row:
            return jsonify(error="session_not_found"), 404
        mock_dir = Path("uploads/mock_quarantine") / str(session_row["child_id"]) / upload_id
        mock_dir.mkdir(parents=True, exist_ok=True)
        dest = mock_dir / f"source.{session_row['extension']}"
        chunk_size = 64 * 1024
        with dest.open("wb") as f:
            while True:
                chunk = request.stream.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
        return "", 200

    @bp.route("/api/mobile/v2/uploads/<upload_id>/complete", methods=["POST"])
    @csrf.exempt
    @limiter.limit("30 per hour")
    @_require_mobile("CHILD")
    def mobile_v2_upload_complete(upload_id):
        uid = int(g.mobile_user["user_id"])
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM upload_sessions WHERE upload_id=%s FOR UPDATE", (upload_id,))
            session_row = cur.fetchone()
            if not session_row:
                conn.rollback()
                return jsonify(error="upload_session_not_found"), 404

            if int(session_row["child_id"]) != uid:
                conn.rollback()
                return jsonify(error="forbidden_upload_owner_mismatch"), 403

            kind = str(session_row.get("kind") or "POST").upper()
            feature = "reels" if kind == "REEL" else "stories" if kind == "STORY" else "posting"
            gate = _child_gate(feature)
            if gate:
                conn.rollback()
                return gate

            cur.execute(
                "SELECT post_id, processing_status, moderation_status, processing_error FROM posts WHERE upload_id=%s OR source_media_path=%s LIMIT 1",
                (upload_id, session_row["object_key"]),
            )
            existing = cur.fetchone()

            if session_row["status"] == "CONSUMED" and existing:
                if existing["processing_status"] == "UPLOADED" and "dispatch_failed" in (existing.get("processing_error") or ""):
                    conn.rollback()
                    from services.job_queue import enqueue_media_job
                    try:
                        job_id = enqueue_media_job(existing["post_id"], uid, session_row["object_key"], session_row["kind"].upper())
                        execute("UPDATE posts SET processing_status='PROCESSING', job_id=%s, processing_error=NULL WHERE post_id=%s", (job_id, existing["post_id"]))
                        return jsonify(ok=True, post_id=existing["post_id"], status="PROCESSING", retry_dispatched=True)
                    except Exception as exc:
                        return jsonify(ok=False, error="job_dispatch_failed", retryable=True, post_id=existing["post_id"], upload_id=upload_id), 503

                conn.rollback()
                return jsonify(
                    ok=True,
                    post_id=existing["post_id"],
                    status=existing["processing_status"],
                    idempotent=True,
                )

            exp = session_row.get("expires_at")
            if exp:
                now = datetime.now(timezone.utc)
                if hasattr(exp, "tzinfo") and exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                elif not hasattr(exp, "tzinfo"):
                    exp = datetime.fromisoformat(str(exp)).replace(tzinfo=timezone.utc)
                if exp < now:
                    cur.execute("UPDATE upload_sessions SET status='EXPIRED' WHERE upload_id=%s", (upload_id,))
                    conn.commit()
                    return jsonify(error="upload_session_expired"), 400

            from services import object_storage

            if object_storage.enabled():
                meta = object_storage.head_object(session_row["object_key"])
                if not meta or meta.get("content_length", 0) <= 0:
                    conn.rollback()
                    return jsonify(error="media_object_missing_in_quarantine"), 400

                actual_bytes = int(meta["content_length"])
                expected_bytes = int(session_row["expected_size_bytes"])
                if actual_bytes != expected_bytes:
                    conn.rollback()
                    return jsonify(
                        error="media_size_mismatch",
                        actual_bytes=actual_bytes,
                        expected_bytes=expected_bytes,
                    ), 400

                actual_mime = (meta.get("content_type") or "").strip().lower()
                expected_mime = (session_row.get("mime_type") or "").strip().lower()
                if actual_mime and expected_mime and actual_mime != expected_mime:
                    conn.rollback()
                    return jsonify(
                        error="media_mime_mismatch",
                        actual_mime=actual_mime,
                        expected_mime=expected_mime,
                    ), 400
            else:
                mock_dir = Path("uploads/mock_quarantine") / str(session_row["child_id"]) / upload_id
                mock_file = mock_dir / f"source.{session_row['extension']}"
                if mock_file.is_file():
                    actual_bytes = mock_file.stat().st_size
                    expected_bytes = int(session_row["expected_size_bytes"])
                    if actual_bytes != expected_bytes:
                        conn.rollback()
                        return jsonify(
                            error="media_size_mismatch",
                            actual_bytes=actual_bytes,
                            expected_bytes=expected_bytes,
                        ), 400

            data = request.get_json(silent=True) or request.form or {}
            caption = str(data.get("caption") or "").strip()
            category = str(data.get("content_category") or "Other")
            category = category if category in SAFE_CATEGORIES else "Other"
            if category not in effective_categories(uid):
                conn.rollback()
                return jsonify(error="category_disabled_by_parent"), 403

            audience_raw = data.get("audience_age_group")
            if audience_raw is not None and str(audience_raw) not in {"ALL", "6-8", "9-11", "12-13", "14-18"}:
                conn.rollback()
                return jsonify(error="invalid_audience_age_group"), 400
            audience = str(audience_raw or "ALL")

            if caption and scan_pii(caption).get("detected"):
                parent_notify(uid, "CONTENT_BLOCKED", "Personal contact information cannot be shared in captions", "/parent/safety/")
                conn.rollback()
                return jsonify(error="caption_pii_blocked"), 400

            raw_tags = data.get("tags") or []
            if isinstance(raw_tags, str):
                raw_tags = [t.strip() for t in raw_tags.split(",") if t.strip()]

            from services.tag_service import validate_and_normalize_tags, save_post_tags

            validated_tags, tag_err = validate_and_normalize_tags(raw_tags, uid)
            if tag_err:
                conn.rollback()
                return jsonify(error=tag_err), 400

            # Cheap deterministic hard-block gate before we create/spawn a media
            # processing job. This catches obvious sexual solicitation, grooming,
            # self-harm, severe abuse and dangerous-challenge text without waking
            # a Modal worker or the T4. Non-obvious text still goes through the
            # full trained/ML moderation path in the background worker.
            precheck_text = " ".join([caption] + [f"#{t}" for t in validated_tags]).strip()
            if precheck_text:
                from safety.text_service import check_text_deterministic
                from safety.policy import decide as decide_safety
                from safety.moderation_service import safety_level as child_safety_level, record as record_moderation

                precheck_signals = check_text_deterministic(precheck_text)
                precheck_decision = decide_safety(
                    precheck_signals,
                    child_safety_level(uid),
                    Config.ADULT_HARD_BLOCK_THRESHOLD,
                )
                if precheck_decision.action == "BLOCK":
                    conn.rollback()
                    try:
                        record_moderation(uid, "TEXT", None, precheck_signals, precheck_decision)
                    except Exception:
                        pass
                    parent_notify(uid, "CONTENT_BLOCKED", precheck_decision.reason, "/parent/safety/")
                    return jsonify(
                        error="caption_safety_blocked",
                        reason=precheck_decision.reason,
                        pre_gpu=True,
                    ), 400

            kind = session_row["kind"].upper()
            media_type = session_row["media_type"].upper()

            location_name = str(data.get("location_name") or "").strip()[:120] or None
            music_id = data.get("music_id")
            music_row = None
            if kind == "STORY" and music_id:
                try:
                    cur.execute("SELECT * FROM curated_music WHERE music_id=%s AND is_active=TRUE", (int(music_id),))
                    music_row = cur.fetchone()
                except Exception:
                    music_row = None
            s_music_id = music_row["music_id"] if music_row else None
            s_music_title = music_row["title"] if music_row else None
            s_music_artist = music_row["artist"] if music_row else None
            s_music_url = music_row["audio_url"] if music_row else None
            s_music_start = int(data.get("music_start") or 0)
            s_music_dur = int(data.get("music_duration") or (music_row["duration_seconds"] if music_row else 30))

            if existing:
                post_id = existing["post_id"]
            else:
                cur.execute(
                    """INSERT INTO posts(child_id, media_type, source_media_path, caption, content_category,
                                       audience_age_group, is_story, is_reel, is_safe, moderation_status,
                                       processing_status, processing_started_at, location_name,
                                       story_music_id, story_music_title, story_music_artist, story_music_url,
                                       story_music_start, story_music_duration, upload_id, processing_attempts, last_attempt_at)
                       VALUES(%s, %s, %s, %s, %s, %s, %s, %s, FALSE, 'PENDING', 'PROCESSING', NOW(), %s, %s, %s, %s, %s, %s, %s, %s, 1, NOW())
                       RETURNING post_id""",
                    (
                        uid,
                        media_type,
                        session_row["object_key"],
                        caption,
                        category,
                        audience,
                        kind == "STORY",
                        kind == "REEL",
                        location_name,
                        s_music_id,
                        s_music_title,
                        s_music_artist,
                        s_music_url,
                        s_music_start,
                        s_music_dur,
                        upload_id,
                    ),
                )
                post_row = cur.fetchone()
                post_id = post_row["post_id"]

            cur.execute(
                "UPDATE upload_sessions SET status='CONSUMED', consumed_at=NOW() WHERE upload_id=%s",
                (upload_id,),
            )
            conn.commit()

            if validated_tags:
                save_post_tags(post_id, validated_tags)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        from services.job_queue import enqueue_media_job

        try:
            job_id = enqueue_media_job(post_id, uid, session_row["object_key"], kind)
            execute("UPDATE posts SET job_id=%s WHERE post_id=%s", (job_id, post_id))
            return jsonify(
                ok=True,
                post_id=post_id,
                status="PROCESSING",
            )
        except Exception as exc:
            execute(
                "UPDATE posts SET processing_status='UPLOADED', processing_error=%s WHERE post_id=%s",
                (f"dispatch_failed: {exc}", post_id),
            )
            return jsonify(
                ok=False,
                error="job_dispatch_failed",
                retryable=True,
                post_id=post_id,
                upload_id=upload_id,
            ), 503

    @bp.route("/api/mobile/v2/posts/<int:post_id>/processing-status", methods=["GET"])
    @_require_mobile("CHILD", "PARENT")
    def mobile_v2_processing_status(post_id):
        uid = int(g.mobile_user["user_id"])
        role = str(g.mobile_user["role"]).upper()

        post = fetch_one(
            """SELECT post_id, child_id, processing_status, moderation_status, is_safe,
                      media_path, poster_path, processing_error
               FROM posts WHERE post_id=%s""",
            (post_id,),
        )
        if not post:
            return jsonify(error="post_not_found"), 404

        owner_id = int(post["child_id"])
        if role == "CHILD" and owner_id != uid:
            return jsonify(error="forbidden_not_post_owner"), 403
        elif role == "PARENT" and not owns(uid, owner_id):
            return jsonify(error="forbidden_not_child_guardian"), 403

        st = post.get("processing_status") or "UPLOADED"
        return jsonify(
            ok=True,
            post_id=post_id,
            status=st,
            stage=st,
            moderation_status=post.get("moderation_status"),
            is_safe=bool(post.get("is_safe")),
            media_url=_asset_url(post.get("media_path")),
            poster_url=_asset_url(post.get("poster_path")),
            error=post.get("processing_error"),
            retryable=st == "UPLOADED" and bool(post.get("processing_error")),
        )

    @bp.route("/api/mobile/v2/posts/<int:post_id>/redrive", methods=["POST"])
    @csrf.exempt
    @_require_mobile("CHILD", "PARENT", "ADMIN")
    def mobile_v2_post_redrive(post_id):
        uid = int(g.mobile_user["user_id"])
        role = str(g.mobile_user["role"]).upper()
        post = fetch_one("SELECT child_id, processing_status FROM posts WHERE post_id=%s", (post_id,))
        if not post:
            return jsonify(error="post_not_found"), 404
        if role == "CHILD" and int(post["child_id"]) != uid:
            return jsonify(error="forbidden_not_post_owner"), 403
        elif role == "PARENT" and not owns(uid, int(post["child_id"])):
            return jsonify(error="forbidden_not_child_guardian"), 403

        from services.media_processor import redrive_media_job
        res = redrive_media_job(post_id)
        return jsonify(res), (200 if res.get("ok") else 400)

    @bp.route("/api/mobile/v2/maintenance/reap-stale-jobs", methods=["POST"])
    @csrf.exempt
    @_require_mobile("ADMIN")
    def mobile_v2_reap_stale_jobs():
        from services.media_processor import reap_stale_media_jobs
        try:
            raw_stale = int(request.args.get("stale_seconds") or 300)
        except (ValueError, TypeError):
            raw_stale = 300
        stale_sec = max(30, min(raw_stale, 86400))
        res = reap_stale_media_jobs(stale_seconds=stale_sec)
        # Bounded abandoned-upload sweep (same TTL-gated, LIMIT-bounded model):
        # direct-to-R2 quarantine objects whose upload session was never
        # completed have no post row, so the job reaper above cannot see them.
        try:
            from services.media_processor import reconcile_abandoned_upload_sessions

            res["abandoned_uploads"] = reconcile_abandoned_upload_sessions()
        except Exception as exc:
            res["abandoned_uploads"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        return jsonify(res)

    @bp.route("/api/mobile/v1/kids/learning")
    @_require_mobile("CHILD")
    def mobile_learning():
        uid = int(g.mobile_user["user_id"])
        return jsonify(ok=True, points=learning_points(uid), challenges=_clean(learning_challenges(uid)))

    @bp.route("/api/mobile/v1/kids/learning/<int:challenge_id>", methods=["POST"])
    @csrf.exempt
    @_require_mobile("CHILD")
    def mobile_learning_answer(challenge_id):
        uid = int(g.mobile_user["user_id"])
        challenge = fetch_one("SELECT * FROM learning_challenges WHERE challenge_id=%s AND active=TRUE", (challenge_id,))
        if not challenge:
            return jsonify(error="challenge_not_found"), 404
        allowed = {x["challenge_id"] for x in learning_challenges(uid)}
        if challenge_id not in allowed:
            return jsonify(error="challenge_not_available"), 403
        response = str((_json_dict()).get("response") or "").strip()
        expected = str(challenge.get("expected_answer") or "").strip()
        correct = True if not expected else response.casefold() == expected.casefold()
        points = int(challenge.get("points") or 0) if correct else 0
        execute(
            """INSERT INTO learning_challenge_attempts(child_id,challenge_id,response,completed,points_awarded)
               VALUES(%s,%s,%s,%s,%s)
               ON CONFLICT(child_id,challenge_id) DO UPDATE SET response=EXCLUDED.response,completed=EXCLUDED.completed,
               points_awarded=EXCLUDED.points_awarded,completed_at=NOW()""",
            (uid, challenge_id, response, correct, points),
        )
        return jsonify(ok=True, correct=correct, points_awarded=points, total_points=learning_points(uid))

    @bp.route("/api/mobile/v1/kids/quiz")
    @_require_mobile("CHILD")
    def mobile_quiz():
        uid = int(g.mobile_user["user_id"])
        state = feed_quiz_state(uid)
        if state.get("required"):
            row = required_feed_quiz(uid)
            rows = [row] if row else []
            reason = "feed_break"
        else:
            limit_arg = request.args.get("limit", type=int)
            default_limit = 2 if needs_onboarding_quiz(uid) else 5
            n = limit_arg if (limit_arg and 1 <= limit_arg <= 20) else default_limit
            rows = quizzes(uid, n)
            reason = "onboarding" if needs_onboarding_quiz(uid) else "practice"

        if not rows:
            return jsonify(error="quiz_bank_unavailable"), 503

        payload = []
        for row in rows:
            if not row:
                continue
            payload.append({
                "quiz_id": row["quiz_id"],
                "category": row.get("category", "Safety"),
                "question": row["question"],
                "options": [row["option_a"], row["option_b"], row["option_c"], row["option_d"]],
            })
        return jsonify(
            ok=True,
            reason=reason,
            required=bool((state.get("required") or needs_onboarding_quiz(uid)) and len(payload) > 0),
            quizzes=_clean(payload),
        )

    @bp.route("/api/mobile/v1/kids/quiz/<int:quiz_id>/answer", methods=["POST"])
    @csrf.exempt
    @_require_mobile("CHILD")
    def mobile_quiz_answer(quiz_id):
        uid = int(g.mobile_user["user_id"])
        answer = str((_json_dict()).get("answer") or "").strip()
        if not answer:
            return jsonify(error="answer_required"), 400

        row = fetch_one(
            "SELECT * FROM quizzes WHERE quiz_id=%s AND age_group=%s",
            (quiz_id, age_group(uid)),
        )
        if not row:
            return jsonify(error="quiz_not_available"), 404
        correct, correct_answer, xp, explanation = record_feed_answer(uid, quiz_id, answer)
        state = feed_quiz_state(uid)
        if state.get("required") and state.get("quiz_id") == quiz_id:
            complete_required_feed_quiz(uid, quiz_id)
        return jsonify(
            ok=True,
            correct=correct,
            correct_answer=correct_answer,
            xp=xp,
            explanation=explanation,
            onboarding_complete=not needs_onboarding_quiz(uid),
            required=bool(feed_quiz_state(uid).get("required")),
        )

    @bp.route("/api/mobile/v1/kids/feed-view/<int:post_id>", methods=["POST"])
    @csrf.exempt
    @_require_mobile("CHILD")
    def mobile_feed_view(post_id):
        uid = int(g.mobile_user["user_id"])
        if not post_visible_to(uid, post_id):
            return jsonify(error="post_not_found"), 404
        state = record_feed_view(uid, post_id)
        return jsonify(ok=True, **_clean(state))

    @bp.route("/api/mobile/v1/kids/settings")
    @_require_mobile("CHILD")
    def mobile_kids_settings():
        uid = int(g.mobile_user["user_id"])
        limit_row = fetch_one("SELECT daily_limit_minutes FROM child_time_limits WHERE child_id=%s", (uid,))
        daily_limit = int(limit_row["daily_limit_minutes"]) if limit_row else 60
        safety_row = fetch_one("SELECT safety_level FROM parent_safety_settings WHERE child_id=%s", (uid,))
        s_level = safety_row["safety_level"] if safety_row else "STRICT"
        return jsonify(
            ok=True,
            profile=_profile_json(get_child_profile(uid)),
            controls=_clean(controls_for_child(uid)),
            minutes_today=minutes_today(uid),
            daily_limit=daily_limit,
            safety_level=s_level,
        )

    @bp.route("/api/mobile/v1/kids/blocked-users")
    @_require_mobile("CHILD")
    def mobile_kids_blocked_users():
        uid = int(g.mobile_user["user_id"])
        rows = fetch_all(
            """SELECT u.user_id, u.username, u.full_name, cp.profile_picture, b.created_at
               FROM blocked_users b
               JOIN users u ON u.user_id = b.blocked_id
               LEFT JOIN child_profiles cp ON cp.child_id = u.user_id
               WHERE b.blocker_id = %s
               ORDER BY b.created_at DESC""",
            (uid,),
        )
        out = []
        for r in rows:
            item = dict(r)
            item["avatar_url"] = _asset_url(item.pop("profile_picture", None))
            out.append(_clean(item))
        return jsonify(ok=True, blocked_users=out)

    @bp.route("/api/mobile/v1/kids/block/<int:target_id>", methods=["POST"])
    @csrf.exempt
    @_require_mobile("CHILD")
    def mobile_kids_block(target_id):
        uid = int(g.mobile_user["user_id"])
        if target_id == uid:
            return jsonify(error="cannot_block_self"), 400
        data = _json_dict()
        action = str(data.get("action") or "block").lower()
        if action == "unblock":
            execute("DELETE FROM blocked_users WHERE blocker_id=%s AND blocked_id=%s", (uid, target_id))
            return jsonify(ok=True, blocked=False)
        execute("INSERT INTO blocked_users(blocker_id,blocked_id) VALUES(%s,%s) ON CONFLICT DO NOTHING", (uid, target_id))
        execute("DELETE FROM followers WHERE (child_id=%s AND following_child_id=%s) OR (child_id=%s AND following_child_id=%s)", (uid, target_id, target_id, uid))
        record_signal(uid, "CREATOR", target_id, "BLOCK")
        return jsonify(ok=True, blocked=True)

    @bp.route("/api/mobile/v1/kids/muted-users")
    @_require_mobile("CHILD")
    def mobile_kids_muted_users():
        uid = int(g.mobile_user["user_id"])
        rows = fetch_all(
            """SELECT u.user_id, u.username, u.full_name, cp.profile_picture, m.created_at
               FROM muted_users m
               JOIN users u ON u.user_id = m.muted_id
               LEFT JOIN child_profiles cp ON cp.child_id = u.user_id
               WHERE m.muter_id = %s
               ORDER BY m.created_at DESC""",
            (uid,),
        )
        out = []
        for r in rows:
            item = dict(r)
            item["avatar_url"] = _asset_url(item.pop("profile_picture", None))
            out.append(_clean(item))
        return jsonify(ok=True, muted_users=out)

    @bp.route("/api/mobile/v1/kids/mute/<int:target_id>", methods=["POST"])
    @csrf.exempt
    @_require_mobile("CHILD")
    def mobile_kids_mute(target_id):
        uid = int(g.mobile_user["user_id"])
        if target_id == uid:
            return jsonify(error="cannot_mute_self"), 400
        data = _json_dict()
        action = str(data.get("action") or "mute").lower()
        if action == "unmute":
            execute("DELETE FROM muted_users WHERE muter_id=%s AND muted_id=%s", (uid, target_id))
            return jsonify(ok=True, muted=False)
        execute("INSERT INTO muted_users(muter_id,muted_id) VALUES(%s,%s) ON CONFLICT DO NOTHING", (uid, target_id))
        record_signal(uid, "CREATOR", target_id, "MUTE")
        return jsonify(ok=True, muted=True)

    @bp.route("/api/mobile/v1/kids/report", methods=["POST"])
    @csrf.exempt
    @_require_mobile("CHILD")
    def mobile_kids_report():
        uid = int(g.mobile_user["user_id"])
        data = _json_dict()
        kind = str(data.get("target_type") or "").upper()
        try:
            tid = int(data.get("target_id", 0))
        except (TypeError, ValueError):
            return jsonify(error="invalid_target"), 400
        reason = str(data.get("reason") or "").strip()
        details = str(data.get("details") or "").strip()
        if kind not in {"USER", "POST", "COMMENT", "MESSAGE"} or not reason or not tid:
            return jsonify(error="invalid_report"), 400

        valid = False
        if kind == "USER":
            is_child = bool(fetch_one("SELECT 1 FROM users WHERE user_id=%s AND role='CHILD' AND user_id<>%s", (tid, uid)))
            has_interaction = bool(fetch_one("SELECT 1 FROM followers WHERE (child_id=%s AND following_child_id=%s) OR (child_id=%s AND following_child_id=%s)", (uid, tid, tid, uid)))
            has_conv = bool(fetch_one("SELECT 1 FROM child_conversations WHERE (child1_id=%s AND child2_id=%s) OR (child1_id=%s AND child2_id=%s)", (min(uid, tid), max(uid, tid), min(uid, tid), max(uid, tid))))
            valid = is_child and (has_interaction or has_conv or can_discover_child(uid, tid))
        elif kind == "POST":
            from services.social import post_visible_to
            valid = bool(post_visible_to(uid, tid))
        elif kind == "COMMENT":
            from services.social import post_visible_to
            row = fetch_one("SELECT post_id FROM comments WHERE comment_id=%s AND moderation_status='ALLOWED'", (tid,))
            valid = bool(row and post_visible_to(uid, row["post_id"]))
        elif kind == "MESSAGE":
            valid = bool(fetch_one("SELECT 1 FROM child_messages WHERE child_message_id=%s AND (sender_child_id=%s OR receiver_child_id=%s)", (tid, uid, uid)))

        if not valid:
            return jsonify(error="target_unavailable"), 404

        execute(
            "INSERT INTO reports(reporter_id, target_type, target_id, reason, details) VALUES(%s, %s, %s, %s, %s)",
            (uid, kind, tid, reason[:100], details[:2000]),
        )
        record_signal(uid, "CREATOR" if kind == "USER" else "SOCIAL", tid, "REPORT")
        parent_notify(uid, "REPORT_FILED", f"Report submitted for {kind.lower()}", "/parent/safety/")
        return jsonify(ok=True)

    @bp.route("/api/mobile/v1/parent/dashboard")
    @_require_mobile("PARENT")
    def mobile_parent_dashboard():
        pid = int(g.mobile_user["user_id"])
        kids = children(pid)
        for child in kids:
            cid = int(child["user_id"])
            try:
                child["minutes_today"] = minutes_today(cid)
            except Exception:
                child["minutes_today"] = 0
            try:
                child["limit"] = fetch_one("SELECT * FROM child_time_limits WHERE child_id=%s", (cid,))
            except Exception:
                child["limit"] = None
            try:
                child["safety"] = fetch_one("SELECT safety_level FROM parent_safety_settings WHERE child_id=%s", (cid,)) or {"safety_level": "STRICT"}
            except Exception:
                child["safety"] = {"safety_level": "STRICT"}
            try:
                child["open_reviews"] = (fetch_one("SELECT COUNT(*) n FROM moderation_events WHERE child_id=%s AND decision='REVIEW' AND status='OPEN'", (cid,)) or {"n": 0})["n"]
            except Exception:
                child["open_reviews"] = 0
            try:
                child["controls"] = controls_for_child(cid)
            except Exception:
                child["controls"] = {}
            try:
                child["presence"] = online_state(cid)
            except Exception:
                child["presence"] = {"online": False}
            try:
                child["behavior"] = behavior_summary(cid)
            except Exception:
                child["behavior"] = {"level": "STABLE", "trend": "stable", "reasons": []}
            try:
                quiz = fetch_one("SELECT COUNT(*) attempted,COUNT(*) FILTER (WHERE is_correct) correct FROM child_quiz_attempts WHERE child_id=%s AND attempted_at>=NOW()-INTERVAL '7 days'", (cid,)) or {"attempted": 0, "correct": 0}
                attempted = int(quiz.get("attempted") or 0)
                correct = int(quiz.get("correct") or 0)
                child["quiz_7d"] = {"attempted": attempted, "correct": correct, "accuracy": round(correct * 100 / attempted) if attempted else 0}
            except Exception:
                child["quiz_7d"] = {"attempted": 0, "correct": 0, "accuracy": 0}
            if child.get("profile_picture"):
                child["avatar_url"] = _asset_url(child.get("profile_picture"))
        try:
            unread = (fetch_one("SELECT COUNT(*) n FROM parent_notifications WHERE parent_id=%s AND is_read=FALSE", (pid,)) or {"n": 0})["n"]
        except Exception:
            unread = 0
        try:
            pending = pending_follows(pid)
        except Exception:
            pending = []
        return jsonify(ok=True, children=_clean(kids), unread=unread, pending=_clean(pending))

    @bp.route("/api/mobile/v1/parent/children", methods=["POST"])
    @csrf.exempt
    @_require_mobile("PARENT")
    def mobile_parent_create_child():
        data = _json_dict()
        try:
            child_id = create_child_for_verified_parent(int(g.mobile_user["user_id"]), data)
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        except Exception as exc:
            import logging
            logging.getLogger(__name__).exception("Failed to create child for parent %s: %s", g.mobile_user.get("user_id"), exc)
            err_msg = str(exc).lower()
            if "unique constraint" in err_msg or "duplicate key" in err_msg or "uniqueviolation" in err_msg:
                return jsonify(error="This username is already taken. Please choose another."), 400
            return jsonify(error="child_creation_failed", message="Unable to create child account. Please verify details and try again."), 400
        return jsonify(ok=True, child_id=child_id, next_steps=["age_quiz"]), 201

    @bp.route("/api/mobile/v1/parent/controls/<int:child_id>", methods=["GET", "PUT"])
    @csrf.exempt
    @_require_mobile("PARENT")
    def mobile_parent_controls(child_id):
        pid = int(g.mobile_user["user_id"])
        if not owns(pid, child_id):
            return jsonify(error="child_not_found"), 404
        if request.method == "PUT":
            data = _json_dict()
            flags = {
                "allow_reels", "allow_stories", "allow_messaging", "allow_posting", "allow_discover",
                "quiet_hours_enabled", "educational_only_feed",
            }
            if any(key in data and not isinstance(data[key], bool) for key in flags):
                return jsonify(error="invalid_controls"), 400
            if "allowed_categories" in data and (
                not isinstance(data["allowed_categories"], list)
                or any(not isinstance(category, str) for category in data["allowed_categories"])
            ):
                return jsonify(error="invalid_categories"), 400
            current = controls_for_child(child_id)
            merged = dict(current)
            merged.update({k: data[k] for k in data if k in {
                "allow_reels", "allow_stories", "allow_messaging", "allow_posting", "allow_discover",
                "quiet_hours_enabled", "quiet_start", "quiet_end", "educational_only_feed", "allowed_categories",
            }})
            form = MultiDict()
            for flag in ("allow_reels", "allow_stories", "allow_messaging", "allow_posting", "allow_discover", "quiet_hours_enabled", "educational_only_feed"):
                if bool(merged.get(flag)):
                    form.add(flag, "on")
            form.add("quiet_start", str(merged.get("quiet_start") or "21:00"))
            form.add("quiet_end", str(merged.get("quiet_end") or "07:00"))
            for category in merged.get("allowed_categories") or SAFE_CATEGORIES:
                form.add("allowed_categories", category)
            try:
                updated = save_controls(pid, child_id, form)
            except ValueError:
                return jsonify(error="invalid_quiet_hours"), 400
            log(child_id, "PARENT_CONTROLS_UPDATED", {"parent_id": pid, "before": current, "after": updated})
            notify(child_id, "PARENT_CONTROLS", "Parent Mode updated your LittleNet permissions", "/child/dashboard/", pid)
        limit_row = fetch_one("SELECT * FROM child_time_limits WHERE child_id=%s", (child_id,))
        return jsonify(
            ok=True,
            controls=_clean(controls_for_child(child_id)),
            time_limit=_clean(limit_row) if limit_row else None,
            categories=SAFE_CATEGORIES,
        )

    @bp.route("/api/mobile/v1/parent/child/<int:child_id>", methods=["DELETE"])
    @csrf.exempt
    @_require_mobile("PARENT")
    def mobile_parent_unlink_child(child_id):
        pid = int(g.mobile_user["user_id"])
        if not owns(pid, child_id):
            return jsonify(error="child_not_found"), 404
        execute("DELETE FROM parent_child_map WHERE child_id=%s AND (parent_id=%s OR verified_parent_id=%s)", (child_id, pid, pid))
        execute("UPDATE users SET account_status='DEACTIVATED' WHERE user_id=%s AND role='CHILD'", (child_id,))
        return jsonify(ok=True, message="child_unlinked")

    @bp.route("/api/mobile/v1/parent/child/<int:child_id>/viewing-insights")
    @csrf.exempt
    @_require_mobile("PARENT")
    def mobile_parent_child_viewing_insights(child_id):
        # Bearer-token alias of GET /api/parent/child/<child_id>/viewing-insights
        # (session-cookie auth there 401s the mobile client). Same parent-owns-
        # child gate and the same read-only aggregation helper.
        pid = int(g.mobile_user["user_id"])
        if not owns(pid, child_id):
            return jsonify(error="child_not_found"), 404
        return jsonify(success=True, **child_viewing_insights(child_id))

    @bp.route("/api/mobile/v1/parent/child/<int:child_id>/reset-password", methods=["POST"])
    @csrf.exempt
    @_require_mobile("PARENT")
    def mobile_parent_reset_child_password(child_id):
        pid = int(g.mobile_user["user_id"])
        data = _json_dict()
        new_password = str(data.get("new_password") or "")
        ok, msg = parent_reset_child_password(pid, child_id, new_password)
        if not ok:
            return jsonify(ok=False, error=msg), 400
        return jsonify(ok=True, message=msg)

    @bp.route("/api/mobile/v1/parent/time-limit/<int:child_id>", methods=["PUT"])
    @csrf.exempt
    @_require_mobile("PARENT")
    def mobile_parent_time_limit(child_id):
        pid = int(g.mobile_user["user_id"])
        if not owns(pid, child_id):
            return jsonify(error="child_not_found"), 404
        data = _json_dict()
        try:
            minutes = int(data.get("daily_limit_minutes"))
        except (TypeError, ValueError):
            return jsonify(error="invalid_limit"), 400
        if not 1 <= minutes <= 1440:
            return jsonify(error="invalid_limit"), 400
        strict = bool(data.get("strict_mode", True))
        execute("INSERT INTO child_time_limits(child_id,daily_limit_minutes,strict_mode) VALUES(%s,%s,%s) ON CONFLICT(child_id) DO UPDATE SET daily_limit_minutes=EXCLUDED.daily_limit_minutes,strict_mode=EXCLUDED.strict_mode,updated_at=NOW()", (child_id, minutes, strict))
        log(child_id, "SCREEN_TIME_LIMIT_UPDATED", {"parent_id": pid, "daily_limit_minutes": minutes, "strict_mode": strict})
        notify(child_id, "SCREEN_TIME", "Parent Mode updated your daily screen-time limit", "/child/dashboard/", pid)
        return jsonify(ok=True, limit=_clean(fetch_one("SELECT * FROM child_time_limits WHERE child_id=%s", (child_id,))))

    @bp.route("/api/mobile/v1/parent/time-limit/<int:child_id>/reset", methods=["POST"])
    @csrf.exempt
    @_require_mobile("PARENT")
    def mobile_parent_time_limit_reset(child_id):
        pid = int(g.mobile_user["user_id"])
        if not owns(pid, child_id):
            return jsonify(error="child_not_found"), 404
        # Clear today's logged usage logs and active session durations for this child
        execute("DELETE FROM child_usage_logs WHERE child_id=%s AND usage_date=CURRENT_DATE", (child_id,))
        execute("DELETE FROM child_usage_sessions WHERE child_id=%s AND ended_at IS NOT NULL AND started_at::date=CURRENT_DATE", (child_id,))
        execute("UPDATE child_usage_sessions SET started_at=NOW(), last_seen_at=NOW() WHERE child_id=%s AND ended_at IS NULL", (child_id,))
        execute("DELETE FROM activity_logs WHERE child_id=%s AND activity_type IN ('SCREEN_TIME_LIMIT_REACHED', 'SCREEN_TIME_WARNING') AND created_at::date=CURRENT_DATE", (child_id,))
        log(child_id, "SCREEN_TIME_RESET", {"parent_id": pid})
        notify(child_id, "SCREEN_TIME_RESET", "Your parent reset your screen time for today! Have fun.", "/child/dashboard/", pid)
        return jsonify(ok=True, message="Screen time reset successfully.", minutes_today=0)

    @bp.route("/api/mobile/v1/parent/time-limit/<int:child_id>/extend", methods=["POST"])
    @csrf.exempt
    @_require_mobile("PARENT")
    def mobile_parent_time_limit_extend(child_id):
        pid = int(g.mobile_user["user_id"])
        if not owns(pid, child_id):
            return jsonify(error="child_not_found"), 404
        data = _json_dict()
        try:
            extra = int(data.get("additional_minutes", 30))
        except (TypeError, ValueError):
            return jsonify(error="invalid_minutes"), 400
        if not 1 <= extra <= 720:
            return jsonify(error="invalid_minutes"), 400
        row = fetch_one("SELECT daily_limit_minutes, strict_mode FROM child_time_limits WHERE child_id=%s", (child_id,))
        current = int(row["daily_limit_minutes"]) if row else 60
        strict = bool(row["strict_mode"]) if row else True
        new_limit = min(1440, current + extra)
        execute(
            "INSERT INTO child_time_limits(child_id, daily_limit_minutes, strict_mode) VALUES(%s, %s, %s) "
            "ON CONFLICT(child_id) DO UPDATE SET daily_limit_minutes=EXCLUDED.daily_limit_minutes, updated_at=NOW()",
            (child_id, new_limit, strict),
        )
        execute("DELETE FROM activity_logs WHERE child_id=%s AND activity_type IN ('SCREEN_TIME_LIMIT_REACHED', 'SCREEN_TIME_WARNING') AND created_at::date=CURRENT_DATE", (child_id,))
        log(child_id, "SCREEN_TIME_EXTENDED", {"parent_id": pid, "additional_minutes": extra, "new_limit": new_limit})
        notify(child_id, "SCREEN_TIME_EXTENDED", f"Your parent added {extra} minutes of screen time!", "/child/dashboard/", pid)
        return jsonify(ok=True, message=f"Added {extra} minutes.", daily_limit_minutes=new_limit)

    @bp.route("/api/mobile/v1/parent/safety")
    @_require_mobile("PARENT")
    def mobile_parent_safety():
        pid = int(g.mobile_user["user_id"])
        rows = fetch_all(
            """SELECT e.*,u.full_name
               FROM moderation_events e JOIN users u ON u.user_id=e.child_id
               WHERE e.decision='REVIEW' AND e.status='OPEN'
                 AND EXISTS (
                   SELECT 1 FROM parent_child_map m
                   JOIN users p ON p.user_id=%s AND p.role='PARENT' AND p.account_status='ACTIVE'
                   WHERE m.child_id=e.child_id
                     AND m.approved=TRUE AND m.approval_status='APPROVED'
                     AND (m.parent_id=%s OR m.verified_parent_id=%s)
                 )
               ORDER BY e.created_at DESC""",
            (pid, pid, pid),
        )
        out = []
        for event in rows:
            item = dict(event)
            preview = None
            if item.get("content_type") in {"IMAGE", "VIDEO", "TEXT"} and item.get("content_id"):
                preview = fetch_one(
                    "SELECT media_type,media_path,source_media_path,poster_path,caption FROM posts WHERE post_id=%s",
                    (item["content_id"],),
                )
            elif item.get("content_type") == "COMMENT" and item.get("content_id"):
                preview = fetch_one("SELECT comment_text FROM comments WHERE comment_id=%s", (item["content_id"],))
            elif item.get("content_type") == "MESSAGE" and item.get("content_id"):
                preview = fetch_one("SELECT message_type,message_text,media_path,shared_post_id FROM child_messages WHERE child_message_id=%s", (item["content_id"],))
            if preview:
                preview = dict(preview)
                source_ref = preview.pop("source_media_path", None)
                published_ref = preview.pop("media_path", None)
                poster_ref = preview.pop("poster_path", None)
                media_ref = source_ref or published_ref
                if media_ref:
                    preview["media_url"] = _asset_url(media_ref)
                if poster_ref:
                    preview["poster_url"] = _asset_url(poster_ref)
            item["preview"] = _clean(preview)
            out.append(_clean(item))
        return jsonify(ok=True, events=out)

    @bp.route("/api/mobile/v1/parent/safety/<int:event_id>", methods=["POST"])
    @csrf.exempt
    @_require_mobile("PARENT")
    def mobile_parent_review(event_id):
        action = str((_json_dict()).get("action") or "").upper()
        ok, result = _resolve_parent_review(int(g.mobile_user["user_id"]), event_id, action)
        status = 200 if ok else 403 if result == "forbidden" else 404 if result == "not_found" else 400
        return jsonify(ok=ok, result=result), status

    @bp.route("/api/mobile/v1/parent/follow-requests")
    @_require_mobile("PARENT")
    def mobile_parent_follow_requests():
        return jsonify(ok=True, pending=_clean(pending_follows(int(g.mobile_user["user_id"]))))

    @bp.route("/api/mobile/v1/parent/follow-requests/action", methods=["POST"])
    @csrf.exempt
    @_require_mobile("PARENT")
    def mobile_parent_follow_action():
        data = _json_dict()
        try:
            child_id = int(data.get("child_id"))
            target_id = int(data.get("target_id"))
        except (TypeError, ValueError):
            return jsonify(error="invalid_ids"), 400
        if not owns(int(g.mobile_user["user_id"]), child_id):
            return jsonify(error="forbidden"), 403
        action = str(data.get("action") or "").lower()
        if action == "approve":
            changed = execute_count("UPDATE followers SET approved=TRUE WHERE child_id=%s AND following_child_id=%s AND approved=FALSE AND approval_stage IN ('REQUESTED','RECEIVER_PARENT_PENDING')", (child_id, target_id))
        elif action == "reject":
            changed = execute_count("DELETE FROM followers WHERE child_id=%s AND following_child_id=%s AND approved=FALSE AND approval_stage IN ('REQUESTED','RECEIVER_PARENT_PENDING')", (child_id, target_id))
        else:
            return jsonify(error="invalid_action"), 400
        if not changed:
            return jsonify(error="follow_request_not_found"), 404
        log(child_id, "PARENT_FOLLOW_ACTION", {"parent_id": int(g.mobile_user["user_id"]), "target_id": target_id, "action": action})
        if action == "approve":
            # Kid-side notification only; follow approval itself stays parent-side by design.
            # Fail-silent: a notification insert must never break the approval itself.
            # friend_name is resolved once, outside the guarded blocks, so a
            # failure in one channel cannot silently skip the other.
            try:
                target = fetch_one("SELECT full_name FROM users WHERE user_id=%s", (target_id,))
            except Exception:
                target = None
            friend_name = (target or {}).get("full_name") or "A friend"
            try:
                notify(child_id, "FRIEND_ADDED", f"{friend_name} is now your friend", f"/profile/{target_id}", target_id)
            except Exception:
                pass
            try:
                from services.push_notifications import notify_friend_added
                notify_friend_added(child_id, friend_name)
            except Exception:
                pass
        return jsonify(ok=True, action=action)

    @bp.route("/api/mobile/v1/parent/notifications", methods=["GET", "POST"])
    @csrf.exempt
    @_require_mobile("PARENT")
    def mobile_parent_notifications():
        pid = int(g.mobile_user["user_id"])
        if request.method == "POST":
            execute("UPDATE parent_notifications SET is_read=TRUE WHERE parent_id=%s AND is_read=FALSE", (pid,))
        rows = fetch_all("SELECT * FROM parent_notifications WHERE parent_id=%s ORDER BY created_at DESC LIMIT 100", (pid,))
        return jsonify(ok=True, notifications=_clean(rows))

    @bp.route("/api/mobile/v1/parent/activity/<int:child_id>")
    @_require_mobile("PARENT")
    def mobile_parent_activity(child_id):
        pid = int(g.mobile_user["user_id"])
        if not owns(pid, child_id):
            return jsonify(error="child_not_found"), 404
        rows = fetch_all(
            """SELECT log_id,activity_type,activity_data,created_at
               FROM activity_logs WHERE child_id=%s
               ORDER BY created_at DESC LIMIT 100""",
            (child_id,),
        )
        return jsonify(ok=True, events=_clean(rows))

    @bp.route("/api/mobile/v1/admin/dashboard")
    @_require_mobile("ADMIN")
    def mobile_admin_dashboard():
        counts_row = {
            "users": (fetch_one("SELECT COUNT(*) n FROM users", ()) or {"n": 0})["n"],
            "children": (fetch_one("SELECT COUNT(*) n FROM users WHERE role='CHILD'", ()) or {"n": 0})["n"],
            "parents": (fetch_one("SELECT COUNT(*) n FROM users WHERE role='PARENT'", ()) or {"n": 0})["n"],
            "open_reviews": (fetch_one("SELECT COUNT(*) n FROM moderation_events WHERE decision='REVIEW' AND status='OPEN'", ()) or {"n": 0})["n"],
        }
        return jsonify(ok=True, counts=_clean(counts_row))

    @bp.route("/api/mobile/v1/admin/reviews")
    @_require_mobile("ADMIN")
    def mobile_admin_reviews():
        rows = fetch_all("SELECT e.*,u.full_name,u.username FROM moderation_events e JOIN users u ON u.user_id=e.child_id WHERE e.decision='REVIEW' AND e.status='OPEN' ORDER BY e.created_at DESC LIMIT 100")
        return jsonify(ok=True, events=_clean(rows))

    @bp.route("/api/mobile/v2/kids/heartbeat", methods=["POST"])
    @csrf.exempt
    @_require_mobile("CHILD")
    def mobile_v2_kids_heartbeat():
        uid = int(g.mobile_user["user_id"])
        key = (g.mobile_claims or {}).get("usage_session_key")
        if key:
            try:
                heartbeat(key)
            except Exception:
                pass
        gate = _child_gate()
        if gate:
            return gate
        locked, remaining = lock_state(uid)
        used_resets = _kid_self_resets_today(uid)
        return jsonify(
            ok=True,
            minutes_today=minutes_today(uid),
            remaining_minutes=remaining,
            locked=locked,
            self_resets_used=used_resets,
            self_resets_remaining=max(0, 2 - used_resets),
        )

    @bp.route("/api/mobile/v1/kids/time-limit/status")
    @_require_mobile("CHILD")
    def mobile_kids_time_limit_status():
        uid = int(g.mobile_user["user_id"])
        locked, remaining = lock_state(uid)
        used = _kid_self_resets_today(uid)
        limit_row = fetch_one("SELECT daily_limit_minutes, strict_mode FROM child_time_limits WHERE child_id=%s", (uid,))
        return jsonify(
            ok=True,
            locked=locked,
            minutes_today=minutes_today(uid),
            daily_limit_minutes=int(limit_row["daily_limit_minutes"]) if limit_row else 60,
            strict_mode=bool(limit_row["strict_mode"]) if limit_row else True,
            remaining_minutes=remaining,
            resets_used=used,
            resets_remaining=max(0, 2 - used),
        )

    @bp.route("/api/mobile/v1/kids/time-limit/reset", methods=["POST"])
    @csrf.exempt
    @_require_mobile("CHILD")
    def mobile_kids_time_limit_self_reset():
        uid = int(g.mobile_user["user_id"])
        quiet = quiet_hours_state(uid)
        if quiet.get("active"):
            return jsonify(error="quiet_hours_active", message="Cannot reset screen time during quiet hours bedtime."), 403

        used = _kid_self_resets_today(uid)
        if used >= 2:
            return jsonify(
                error="self_resets_exhausted",
                message="You have used all 2 daily resets for today. Please ask your parent to add more time.",
                resets_used=used,
                resets_remaining=0,
            ), 403

        # Clear today's logged usage logs and active session durations
        execute("DELETE FROM child_usage_logs WHERE child_id=%s AND usage_date=CURRENT_DATE", (uid,))
        execute("DELETE FROM child_usage_sessions WHERE child_id=%s AND ended_at IS NOT NULL AND started_at::date=CURRENT_DATE", (uid,))
        execute("UPDATE child_usage_sessions SET started_at=NOW(), last_seen_at=NOW() WHERE child_id=%s AND ended_at IS NULL", (uid,))
        execute("DELETE FROM activity_logs WHERE child_id=%s AND activity_type IN ('SCREEN_TIME_LIMIT_REACHED', 'SCREEN_TIME_WARNING') AND created_at::date=CURRENT_DATE", (uid,))

        new_count = used + 1
        remaining = max(0, 2 - new_count)
        log(uid, "KID_SCREEN_TIME_SELF_RESET", {"reset_number": new_count, "remaining_resets": remaining})
        notify(uid, "SCREEN_TIME_RESET", f"You used daily reset #{new_count}. You have {remaining} reset(s) left today.", "/child/dashboard/")

        # Notify parents of child self-reset
        execute(
            """INSERT INTO parent_notifications(parent_id, child_id, notification_type, notification_message, target_url)
               SELECT parent_id, %s, 'SCREEN_TIME', 'Your child used daily screen-time reset #' || %s || ' (' || %s || ' remaining today).', '/parent/time-limit/?child_id=' || %s
               FROM parent_child_map WHERE child_id=%s AND parent_id IS NOT NULL""",
            (uid, str(new_count), str(remaining), str(uid), uid),
        )

        return jsonify(
            ok=True,
            message=f"Screen time reset! You have {remaining} reset(s) left today.",
            resets_used=new_count,
            resets_remaining=remaining,
            minutes_today=0,
        )

    @bp.route("/api/mobile/v2/kids/feed")
    @_require_mobile("CHILD")
    def mobile_kids_feed_v2():
        gate = _child_gate()
        if gate:
            return gate
        uid = int(g.mobile_user["user_id"])
        mode = request.args.get("mode", "for_you").strip().lower()
        try:
            cursor = max(0, int(request.args.get("cursor", 0)))
        except (TypeError, ValueError):
            cursor = 0
        try:
            limit = min(50, max(1, int(request.args.get("limit", 10))))
        except (TypeError, ValueError):
            limit = 10
        session_id = request.args.get("session_id")
        page = get_feed_page(uid, surface="FEED", cursor=cursor, limit=limit, session_id=session_id, mode=mode)
        from services.media_delivery import resolve_media_delivery
        for item in page["items"]:
            if item.get("media_reference"):
                m_res = resolve_media_delivery(item["media_reference"], viewer_id=uid, viewer_role="CHILD")
                item["media_url"] = m_res.get("url")
                if m_res.get("expires_at"):
                    item["playback_expires_at"] = m_res["expires_at"]
            if item.get("poster_reference"):
                p_res = resolve_media_delivery(item["poster_reference"], viewer_id=uid, viewer_role="CHILD")
                item["poster_url"] = p_res.get("url")
        return jsonify(ok=True, **_clean(page))

    @bp.route("/api/mobile/v2/kids/reels")
    @_require_mobile("CHILD")
    def mobile_kids_reels_v2():
        gate = _child_gate("reels")
        if gate:
            return gate
        uid = int(g.mobile_user["user_id"])
        try:
            cursor = max(0, int(request.args.get("cursor", 0)))
        except (TypeError, ValueError):
            cursor = 0
        try:
            limit = min(50, max(1, int(request.args.get("limit", 10))))
        except (TypeError, ValueError):
            limit = 10
        session_id = request.args.get("session_id")
        page = get_feed_page(uid, surface="REELS", cursor=cursor, limit=limit, session_id=session_id)
        from services.media_delivery import resolve_media_delivery
        for item in page["items"]:
            source_type = str(item.get("source_type") or "").upper()

            # Social Reels use just-in-time playback credentials. This avoids
            # minting signed R2/Stream credentials for every item in a page that
            # the child may never watch. The mobile player requests the current
            # and adjacent Reel through /reels/<post_id>/playback.
            if source_type == "SOCIAL":
                item["media_url"] = None
                item["playback_expires_at"] = None
                item["playback_ready"] = True
                item["delivery_type"] = "JIT"
            elif source_type == "CURATED":
                # Do not mint a signed R2 URL for every item in the page. That
                # made the metadata request exceed the mobile timeout during a
                # cold start. The player requests only the active/nearby item.
                item["media_url"] = None
                item["playback_expires_at"] = None
                item["playback_ready"] = True
                item["delivery_type"] = "JIT_CURATED"

            if item.get("poster_reference"):
                p_res = resolve_media_delivery(
                    item["poster_reference"],
                    viewer_id=uid,
                    viewer_role="CHILD",
                )
                item["poster_url"] = p_res.get("url")
        return jsonify(ok=True, **_clean(page))

    @bp.route("/api/mobile/v2/kids/reels/curated/<int:content_id>/playback")
    @_require_mobile("CHILD")
    def mobile_kids_curated_reel_playback_v2(content_id):
        gate = _child_gate("reels")
        if gate:
            return gate
        uid = int(g.mobile_user["user_id"])
        from services.curated_feed import authorize_curated_media
        try:
            playback = authorize_curated_media(uid, content_id)
        except FileNotFoundError:
            return jsonify(ok=False, error="curated_reel_not_found"), 404
        except PermissionError as exc:
            return jsonify(ok=False, error=str(exc) or "playback_denied"), 403
        if not playback.get("media_url"):
            return jsonify(ok=False, error="playback_denied"), 403
        return jsonify(
            ok=True,
            playback_url=playback.get("media_url"),
            playback_expires_at=playback.get("playback_expires_at"),
            poster_url=playback.get("poster_url"),
        )

    @bp.route("/api/mobile/v2/kids/reels/<int:post_id>/playback")
    @_require_mobile("CHILD")
    def mobile_kids_reel_playback_v2(post_id):
        gate = _child_gate("reels")
        if gate:
            return gate
        uid = int(g.mobile_user["user_id"])
        from services.video_delivery import resolve_video_playback
        playback = resolve_video_playback(post_id, viewer_id=uid, viewer_role="CHILD")
        if not playback.get("playback_url"):
            return jsonify(ok=False, error="playback_denied"), 403
        return jsonify(ok=True, **_clean(playback))

    @bp.route("/api/mobile/v2/media/playback/<int:post_id>")
    @_require_mobile()
    def mobile_media_playback_v2(post_id):
        user = g.mobile_user
        uid = int(user["user_id"])
        role = str(user.get("role", "CHILD")).upper()
        if role == "CHILD":
            gate = _child_gate()
            if gate:
                return gate
        from services.video_delivery import resolve_video_playback
        playback = resolve_video_playback(post_id, viewer_id=uid, viewer_role=role)
        if not playback.get("playback_url"):
            return jsonify(ok=False, error="playback_denied"), 403
        return jsonify(ok=True, **_clean(playback))

    @bp.route("/api/mobile/v2/kids/stories/<int:story_id>/view", methods=["POST"])
    @csrf.exempt
    @_require_mobile("CHILD")
    def mobile_kids_story_view(story_id):
        gate = _child_gate("stories")
        if gate:
            return gate
        uid = int(g.mobile_user["user_id"])
        from services.social import story_visible_to
        if not story_visible_to(uid, story_id):
            return jsonify(ok=False, error="story_not_found_or_forbidden"), 404
        data = _json_dict()
        try:
            ratio = min(1.0, max(0.0, float(data.get("completion_ratio", 1.0))))
        except (TypeError, ValueError):
            ratio = 1.0
        execute(
            """INSERT INTO story_views (post_id, child_id, viewed_at, first_viewed_at, last_viewed_at, completion_ratio)
               VALUES (%s, %s, NOW(), NOW(), NOW(), %s)
               ON CONFLICT (post_id, child_id)
               DO UPDATE SET last_viewed_at = NOW(),
                             completion_ratio = GREATEST(story_views.completion_ratio, EXCLUDED.completion_ratio)""",
            (story_id, uid, ratio),
        )
        count_row = fetch_one("SELECT COUNT(*) AS viewer_count FROM story_views WHERE post_id=%s", (story_id,))
        return jsonify(ok=True, viewer_count=int(count_row["viewer_count"] if count_row else 1))

    @bp.route("/api/mobile/v2/kids/stories/<int:story_id>/viewers")
    @_require_mobile("CHILD")
    def mobile_kids_story_viewers(story_id):
        gate = _child_gate("stories")
        if gate:
            return gate
        uid = int(g.mobile_user["user_id"])
        story = fetch_one("SELECT child_id FROM posts WHERE post_id=%s AND is_story=TRUE", (story_id,))
        if not story or story["child_id"] != uid:
            return jsonify(ok=False, error="forbidden_or_not_found"), 403
        viewers = fetch_all(
            """SELECT sv.child_id, sv.first_viewed_at, sv.last_viewed_at, sv.completion_ratio,
                      u.full_name, u.username, cp.profile_picture
               FROM story_views sv
               JOIN users u ON u.user_id = sv.child_id
               LEFT JOIN child_profiles cp ON cp.child_id = sv.child_id
               WHERE sv.post_id = %s
               ORDER BY sv.last_viewed_at DESC""",
            (story_id,),
        )
        viewer_rows = _clean(viewers)
        for viewer in viewer_rows:
            viewer["avatar_url"] = _asset_url(viewer.pop("profile_picture", None))
        return jsonify(ok=True, viewers=viewer_rows)

    @bp.route("/api/mobile/v2/device/register", methods=["POST"])
    @csrf.exempt
    @_require_mobile()
    def mobile_device_register():
        uid = int(g.mobile_user["user_id"])
        data = _json_dict()
        token = str(data.get("push_token") or data.get("token") or "").strip()
        platform = str(data.get("platform") or "android").strip()
        device_id = data.get("device_identifier")
        if not token:
            return jsonify(error="push_token_required"), 400
        from services.push_notifications import register_device_token
        ok = register_device_token(uid, platform, token, device_id)
        return jsonify(ok=ok)

    @bp.route("/api/mobile/v2/device/unregister", methods=["POST"])
    @csrf.exempt
    @_require_mobile()
    def mobile_device_unregister():
        uid = int(g.mobile_user["user_id"])
        data = _json_dict()
        token = str(data.get("push_token") or "").strip()
        if not token:
            return jsonify(error="push_token_required"), 400
        from services.push_notifications import revoke_device_token
        ok = revoke_device_token(uid, token)
        return jsonify(ok=ok)

    @bp.route("/api/mobile/v2/curated/media/<int:content_id>")
    @_require_mobile("CHILD")
    def mobile_curated_media(content_id):
        gate = _child_gate()
        if gate:
            return gate
        uid = int(g.mobile_user["user_id"])
        try:
            payload = authorize_curated_media(uid, content_id)
            return jsonify(ok=True, **_clean(payload))
        except FileNotFoundError:
            return jsonify(error="content_not_found"), 404
        except PermissionError as exc:
            return jsonify(error=str(exc)), 403

    @bp.route("/api/mobile/v2/kids/impressions", methods=["POST"])
    @csrf.exempt
    @_require_mobile("CHILD")
    def mobile_record_impression():
        gate = _child_gate()
        if gate:
            return gate
        uid = int(g.mobile_user["user_id"])
        data = _json_dict()
        session_id = str(data.get("session_id") or "").strip()
        source_type = str(data.get("source_type") or "POST").strip().upper()
        try:
            source_id = int(data.get("source_id"))
        except (TypeError, ValueError):
            return jsonify(error="invalid_source_id"), 400
        surface = str(data.get("surface") or "FEED").strip().upper()
        watched_ms = data.get("watched_ms")
        if watched_ms is not None:
            try:
                watched_ms = max(0, int(watched_ms))
            except (TypeError, ValueError):
                watched_ms = None
        completed = bool(data.get("completed", False))
        liked = bool(data.get("liked", False))
        saved = bool(data.get("saved", False))
        try:
            replay_count = max(0, min(20, int(data.get("replay_count", 0) or 0)))
        except (TypeError, ValueError):
            replay_count = 0

        state = feed_quiz_state(uid)
        if state.get("required"):
            return jsonify(error="quiz_required", gate="quiz", quiz_required=True), 428

        ok = record_feed_impression(
            uid, session_id, source_type, source_id, surface,
            watched_ms=watched_ms, completed=completed, liked=liked, saved=saved,
            replay_count=replay_count,
        )
        if not ok:
            return jsonify(error="invalid_session_item"), 403

        # Advance combined server counter for eligible substantially-viewed item
        view_res = record_feed_view(uid, source_id, source_type=source_type)
        if view_res.get("required"):
            return jsonify(
                ok=True,
                quiz_required=True,
                gate="quiz",
                posts_seen=view_res.get("posts_seen", 4),
                error="quiz_required",
            ), 428

        return jsonify(
            ok=True,
            quiz_required=False,
            posts_seen=view_res.get("posts_seen", 0),
        )

    @bp.route("/api/mobile/v2/kids/impressions/batch", methods=["POST"])
    @csrf.exempt
    @limiter.limit("60 per minute")
    @_require_mobile("CHILD")
    def mobile_record_impression_batch():
        gate = _child_gate()
        if gate:
            return gate
        uid = int(g.mobile_user["user_id"])
        data = _json_dict()
        events = data.get("events") or []
        if not isinstance(events, list):
            return jsonify(error="invalid_events_format"), 400
        if len(events) > 50:
            return jsonify(error="maximum 50 events allowed per batch"), 400
        if not events:
            return jsonify(ok=True, processed=0, recorded=0)

        processed = 0
        recorded = 0
        from services.curated_feed import record_feed_impression
        for ev in events:
            if not isinstance(ev, dict):
                continue
            sess_id = str(ev.get("session_id") or "").strip()
            src_type = str(ev.get("source_type") or "POST").strip().upper()
            try:
                src_id = int(ev.get("source_id"))
            except (TypeError, ValueError):
                continue
            surf = str(ev.get("surface") or "REELS").strip().upper()
            w_ms = ev.get("watched_ms")
            if w_ms is not None:
                try:
                    w_ms = max(0, int(w_ms))
                except (TypeError, ValueError):
                    w_ms = None
            comp = bool(ev.get("completed", False))
            lk = bool(ev.get("liked", False))
            sv = bool(ev.get("saved", False))
            try:
                rc = max(0, min(20, int(ev.get("replay_count", 0) or 0)))
            except (TypeError, ValueError):
                rc = 0

            try:
                was_recorded = record_feed_impression(
                    uid, sess_id, src_type, src_id, surf,
                    watched_ms=w_ms, completed=comp, liked=lk, saved=sv,
                    replay_count=rc,
                )
                processed += 1
                if was_recorded:
                    recorded += 1
            except Exception:
                pass

        return jsonify(ok=True, processed=processed, recorded=recorded)

    @bp.route("/api/mobile/v2/kids/recommendation-actions", methods=["POST"])
    @csrf.exempt
    @_require_mobile("CHILD")
    def mobile_recommendation_action():
        gate = _child_gate()
        if gate:
            return gate
        uid = int(g.mobile_user["user_id"])
        data = _json_dict()
        action = str(data.get("action") or "").upper()
        source_type = str(data.get("source_type") or "SOCIAL").upper()
        try:
            source_id = int(data.get("source_id"))
        except (TypeError, ValueError):
            return jsonify(error="invalid_source_id"), 400
        if action not in {"NOT_INTERESTED", "HIDE", "SEARCH_CLICK"}:
            return jsonify(error="invalid_action"), 400
        source_type = "CURATED" if source_type == "CURATED" else "SOCIAL"
        if not post_visible_to(uid, source_id) and source_type == "SOCIAL":
            return jsonify(error="post_not_found"), 404
        if action == "SEARCH_CLICK" and source_type == "CURATED":
            # Curated search results are authorized again by the normal
            # publication/age/Parent Mode query before recording the click.
            if not any(int(item["source_id"]) == source_id for item in search_curated_content(uid, str(data.get("query") or ""), 50)):
                return jsonify(error="content_not_found"), 404
        record_signal(uid, source_type, source_id, action)
        return jsonify(ok=True, action=action)

    @bp.route("/api/mobile/v2/kids/discover")
    @_require_mobile("CHILD")
    def mobile_kids_discover_v2():
        gate = _child_gate("discover")
        if gate:
            return gate
        uid = int(g.mobile_user["user_id"])
        q = str(request.args.get("q") or "").strip()
        if q and scan_pii(q).get("detected"):
            return jsonify(ok=True, pii_warning=True, children=[], posts=[], curated=[])

        kids = discoverable_children(uid, q.lstrip("#") if q and not q.startswith("#") else None, 30)
        out_kids = []
        for child in kids:
            row = dict(child)
            row["avatar_url"] = _asset_url(row.get("profile_picture"))
            row["is_following"] = is_following(uid, row["user_id"])
            row["is_pending"] = is_follow_pending(uid, row["user_id"])
            row.pop("profile_picture", None)
            out_kids.append(_clean(row))

        allowed_author_ids = [uid] + discoverable_child_ids(uid)
        if q:
            posts = search_visible_posts(uid, q, 30, allowed_author_ids=allowed_author_ids)
        else:
            posts = discoverable_posts(uid, False, 30, 0)

        curated = search_curated_content(uid, q, limit=20) if q else []
        if not q:
            # Instagram Explore parity: a fresh account has no social posts yet,
            # so the default Discover view falls back to safe curated picks
            # instead of rendering a blank page.
            from services.curated_feed import fetch_curated_candidates

            curated = fetch_curated_candidates(uid, "FEED", 20)
        for item in curated:
            if item.get("media_reference"):
                item["media_url"] = _asset_url(item["media_reference"])
            if item.get("poster_reference"):
                item["poster_url"] = _asset_url(item["poster_reference"])

        return jsonify(
            ok=True,
            pii_warning=False,
            children=out_kids,
            posts=[_post_json(p, uid) for p in posts],
            hashtags=_clean(visible_hashtags(uid, q, 10, allowed_author_ids=allowed_author_ids)),
            curated=_clean(curated),
        )
