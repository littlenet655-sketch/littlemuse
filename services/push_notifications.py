"""Push Notification Service for LittleNet.

Supports Expo Push notifications for Android and iOS clients.
Enforces child privacy invariants:
- Never includes sensitive moderation evidence or face data in notifications.
- Never sends raw child private message text or precise geolocation.
- Auto-revokes invalid/expired push tokens returned by Expo.
"""
from __future__ import annotations

import logging

import requests
from typing import Any

from database.connection import execute, fetch_all

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


def register_device_token(
    user_id: int,
    platform: str,
    push_token: str,
    device_identifier: str | None = None,
) -> bool:
    """Register or refresh an active push token for a user."""
    token = str(push_token or "").strip()
    plat = str(platform or "android").strip().lower()
    if not token or not user_id:
        return False

    try:
        # One physical Expo token has exactly one current LittleNet owner.
        # Re-registering after an account switch atomically transfers ownership
        # instead of leaving the old account able to push private notifications
        # to the same device.
        execute(
            """INSERT INTO user_device_tokens (user_id, platform, push_token, device_identifier, created_at, last_seen_at, revoked_at)
               VALUES (%s, %s, %s, %s, NOW(), NOW(), NULL)
               ON CONFLICT (push_token)
               DO UPDATE SET user_id = EXCLUDED.user_id,
                             platform = EXCLUDED.platform,
                             device_identifier = COALESCE(EXCLUDED.device_identifier, user_device_tokens.device_identifier),
                             last_seen_at = NOW(),
                             revoked_at = NULL""",
            (int(user_id), plat, token, device_identifier),
        )
        return True
    except Exception as exc:
        logger.warning("Failed to register push token for user %s: %s", user_id, exc)
        return False


def revoke_device_token(user_id: int, push_token: str) -> bool:
    """Revoke a push token on logout or token expiration."""
    token = str(push_token or "").strip()
    if not token or not user_id:
        return False

    try:
        execute(
            "UPDATE user_device_tokens SET revoked_at = NOW() WHERE user_id = %s AND push_token = %s",
            (int(user_id), token),
        )
        return True
    except Exception as exc:
        logger.warning("Failed to revoke push token: %s", exc)
        return False


def get_active_tokens_for_user(user_id: int) -> list[str]:
    """Retrieve all non-revoked push tokens for a given user."""
    rows = fetch_all(
        "SELECT push_token FROM user_device_tokens WHERE user_id = %s AND revoked_at IS NULL",
        (int(user_id),),
    )
    return [str(r["push_token"]) for r in (rows or []) if r.get("push_token")]


def send_expo_push(
    tokens: list[str],
    title: str,
    body: str,
    data: dict[str, Any] | None = None,
    badge: int | None = None,
) -> bool:
    """Send batched push notification to Expo push service."""
    valid_tokens = [t for t in tokens if t.startswith("ExponentPushToken[") or t.startswith("ExpoPushToken[")]
    if not valid_tokens:
        return False

    # Privacy filter on payload data: strictly omit passwords, keys, face embeddings, raw text
    safe_data = {}
    if data:
        for k, v in data.items():
            if k not in {"password", "secret", "embedding", "raw_text", "location", "biometric_key"}:
                safe_data[k] = v

    messages = [
        {
            "to": t,
            "title": title,
            "body": body,
            "sound": "default",
            "data": safe_data,
            "priority": "high",
            **({"badge": badge} if badge is not None else {}),
        }
        for t in valid_tokens
    ]

    try:
        response = requests.post(
            EXPO_PUSH_URL,
            json=messages,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=8,
        )
        response.raise_for_status()
        resp_data = response.json()
        data_items = resp_data.get("data") or []
        for idx, item in enumerate(data_items):
            if item.get("status") == "error":
                details = item.get("details") or {}
                if details.get("error") == "DeviceNotRegistered" and idx < len(valid_tokens):
                    bad_token = valid_tokens[idx]
                    execute(
                        "UPDATE user_device_tokens SET revoked_at = NOW() WHERE push_token = %s",
                        (bad_token,),
                    )
        return True
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Expo push delivery error: %s", type(exc).__name__)
        return False


def notify_user_event(
    user_id: int,
    event_type: str,
    title: str,
    message: str,
    payload: dict[str, Any] | None = None,
) -> bool:
    """Dispatch a push notification to a user's registered devices."""
    tokens = get_active_tokens_for_user(user_id)
    if not tokens:
        return False

    data = {
        "event_type": event_type,
        **(payload or {}),
    }
    return send_expo_push(tokens, title=title, body=message, data=data)


def notify_parent_safety_event(parent_id: int, child_name: str, event_id: int, decision: str) -> bool:
    """Notify parent that child content needs safety review."""
    title = "LittleNet Safety Notice"
    msg = f"A new post by {child_name} requires your review."
    return notify_user_event(
        parent_id,
        event_type="SAFETY_REVIEW",
        title=title,
        message=msg,
        payload={"eventId": event_id, "decision": decision},
    )


def notify_child_content_status(child_id: int, post_id: int, status: str, kind: str = "post") -> bool:
    """Notify child when asynchronous moderation resolves."""
    kind_label = "Reel" if kind.lower() == "reel" else "Story" if kind.lower() == "story" else "post"
    if status == "ALLOWED":
        title = "Post Published! 🎉"
        msg = f"Your {kind_label} was approved and is now live."
    elif status == "REVIEW":
        title = "In Safety Review ⏳"
        msg = f"Your {kind_label} is being reviewed by your parent."
    else:
        title = "Post Not Published"
        msg = f"Your {kind_label} could not be shared due to safety rules."

    return notify_user_event(
        child_id,
        event_type="CONTENT_STATUS",
        title=title,
        message=msg,
        payload={"postId": post_id, "status": status},
    )


def notify_new_chat_message(recipient_id: int, sender_name: str, conversation_id: int) -> bool:
    """Notify a child when an approved friend sends a message."""
    return notify_user_event(
        recipient_id,
        event_type="NEW_MESSAGE",
        title=f"Message from {sender_name}",
        message=f"{sender_name} sent you a message.",
        payload={"conversationId": conversation_id},
    )


def notify_new_like(recipient_id: int, liker_name: str, post_id: int) -> bool:
    """Notify a child that an approved connection liked their post."""
    return notify_user_event(
        recipient_id,
        event_type="NEW_LIKE",
        title=f"New like from {liker_name}",
        message=f"{liker_name} liked your post.",
        payload={"postId": post_id},
    )


def notify_new_comment(recipient_id: int, commenter_name: str, post_id: int) -> bool:
    """Notify a child that an approved connection commented on their post."""
    return notify_user_event(
        recipient_id,
        event_type="NEW_COMMENT",
        title=f"New comment from {commenter_name}",
        message=f"{commenter_name} commented on your post.",
        payload={"postId": post_id},
    )


def notify_friend_added(recipient_id: int, friend_name: str) -> bool:
    """Notify a child that their parent approved a new friendship."""
    return notify_user_event(
        recipient_id,
        event_type="FRIEND_ADDED",
        title="New friend!",
        message=f"{friend_name} is now your friend.",
        payload={},
    )
