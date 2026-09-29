"""Parent-initiated full data reset for one child account ("Clear Everything").

Scope is deliberate and documented here because this is destructive:

  KEEP (never touched):
    - users row: username, password_hash, age, role, account_status
      (the child keeps the same login identity and password).
    - parent_child_map: the child-parent link is preserved.
    - child_profiles: identity the parent set at account creation
      (name/school/bio), not app activity.
    - parent_safety_settings: the parent's safety policy (STRICT/STANDARD/
      VERY_STRICT) is a safety choice, not app state; Reset Settings does
      not touch it either.
    - moderation_events / moderation_reviews: parent safety audit trail.
    - login_activity, parent_verifications, admin_audit_logs: security records.
    - reports: safety records.
    - user_device_tokens: device push registration keeps working.
    - child_skills / child_interests / child_ambitions: parent-approved
      profile attributes, not child app activity.

  CLEAR:
    - posts / reels / stories (with durable R2 media cleanup through
      media_delete_outbox -- never strand R2 objects; this includes
      media_assets variant keys, deleted_posts tombstone refs, and both
      participants' chat media in wiped conversations),
    - the child's comments / likes / saves on anyone's content,
    - follows, blocks, mutes (both directions),
    - chats: every 1:1 conversation the child participates in, removed for
      both participants so no half-conversation dangles (all message media
      enqueued before the cascade),
    - quiz attempts/progress/pools, learning-challenge attempts,
    - activity logs, parent weekly digests, notifications, parent
      notifications, usage logs/sessions,
    - pending screen-time extension requests,
    - recommendation / feed-session / personalization state,
    - user preferences (language back to default).

  RESET TO DEFAULTS (same scope as Reset Settings):
    - parent_control_settings (deleted; defaults re-read),
    - child_time_limits (60 min/day, strict mode, no bonus),
    - parent_quiz_settings (deleted),
    - users.parent_paused = FALSE.

Everything runs in ONE transaction under a per-child advisory lock, and the
media_delete_outbox rows are inserted with the same cursor so an R2 cleanup
is enqueued if and only if the data delete commits.
"""
from __future__ import annotations

from database.connection import get_db_connection
from services.object_storage import R2_REFERENCE_PREFIX

# Advisory-lock namespace: 842102 = usage sessions, 842103 = extension
# requests, 842104 = account clear-everything.
_CLEAR_LOCK_KEY = 842104


def _enqueue_ref(cur, reference, source_table, source_id) -> bool:
    """Mirror services.media_outbox.enqueue_delete but on this transaction's cursor."""
    ref = str(reference or "")
    if not ref.startswith(R2_REFERENCE_PREFIX):
        return False
    cur.execute(
        """INSERT INTO media_delete_outbox(reference,source_table,source_id)
           VALUES(%s,%s,%s)
           ON CONFLICT(reference) DO UPDATE
             SET completed_at=NULL,last_error=NULL,source_table=EXCLUDED.source_table,
                 source_id=COALESCE(EXCLUDED.source_id,media_delete_outbox.source_id)""",
        (ref, source_table, source_id),
    )
    return True


# (table, column) pairs cleared with WHERE <column> = child_id.
_CHILD_SCOPED_TABLES = (
    ("child_quiz_attempts", "child_id"),
    ("child_quiz_progress", "child_id"),
    ("child_personalized_quiz_pool", "child_id"),
    ("child_vocabulary_progress", "child_id"),
    ("child_xp", "child_id"),
    ("learning_challenge_attempts", "child_id"),
    ("activity_logs", "child_id"),
    ("child_usage_logs", "child_id"),
    ("child_usage_sessions", "child_id"),
    ("screen_time_extension_requests", "child_id"),
    ("feed_sessions", "child_id"),
    ("recommendation_signals", "child_id"),
    ("parent_notifications", "child_id"),
    ("notifications", "user_id"),
    ("parent_control_settings", "child_id"),
    ("parent_quiz_settings", "child_id"),
    ("user_preferences", "user_id"),
    ("comments", "child_id"),
    ("likes", "child_id"),
    ("saved_posts", "child_id"),
    ("content_saves", "child_id"),
    ("content_reactions", "child_id"),
    ("content_shares", "child_id"),
    ("content_impressions", "child_id"),
    ("story_views", "child_id"),
    ("story_reactions", "child_id"),
    ("chat_typing", "user_id"),
    ("message_reactions", "child_id"),
    ("deleted_posts", "child_id"),
    ("parent_weekly_digests", "child_id"),
)


def clear_everything_for_child(child_id: int, parent_id: int) -> dict:
    """Wipe one child's app data and restore defaults; keep login + parent link.

    Raises ValueError when the target is not an ACTIVE child account.
    Returns a summary dict of deleted-row counts per area.
    """
    child_id = int(child_id)
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT pg_advisory_xact_lock(%s, %s)", (_CLEAR_LOCK_KEY, child_id))
        cur.execute(
            "SELECT user_id, username, role, account_status FROM users WHERE user_id=%s",
            (child_id,),
        )
        user = cur.fetchone()
        if not user or user.get("role") != "CHILD":
            conn.rollback()
            raise ValueError("clear_everything_child_only")
        if user.get("account_status") != "ACTIVE":
            conn.rollback()
            raise ValueError("clear_everything_account_inactive")

        summary: dict = {"media_enqueued": 0}

        # ---- 1. R2 media: posts/reels/stories (quarantine + published refs) ----
        cur.execute(
            """SELECT post_id, source_media_path, media_path, poster_path, story_music_path
               FROM posts WHERE child_id=%s""",
            (child_id,),
        )
        for post in cur.fetchall():
            for column in ("source_media_path", "media_path", "poster_path", "story_music_path"):
                if _enqueue_ref(cur, (post or {}).get(column), "posts", (post or {}).get("post_id")):
                    summary["media_enqueued"] += 1

        # ---- 2. R2 media: in-flight post upload sessions (quarantine) ----
        cur.execute("SELECT object_key FROM upload_sessions WHERE child_id=%s", (child_id,))
        for row in cur.fetchall():
            if _enqueue_ref(cur, (row or {}).get("object_key"), "upload_sessions", None):
                summary["media_enqueued"] += 1

        # ---- 3. R2 media: in-flight chat upload sessions (quarantine) ----
        cur.execute("SELECT object_key FROM chat_upload_sessions WHERE child_id=%s", (child_id,))
        for row in cur.fetchall():
            if _enqueue_ref(cur, (row or {}).get("object_key"), "chat_upload_sessions", None):
                summary["media_enqueued"] += 1

        # ---- 4. R2 media: chat media in every conversation being wiped.
        # Conversations are deleted for BOTH participants (step 6), so the
        # peer's media messages would cascade-delete with their R2 objects
        # stranded. Enqueue media from all messages where the child is either
        # sender or receiver -- that covers every message in those 1:1
        # conversations. ----
        cur.execute(
            """SELECT child_message_id, media_path FROM child_messages
               WHERE media_path IS NOT NULL
                 AND (sender_child_id=%s OR receiver_child_id=%s)""",
            (child_id, child_id),
        )
        for row in cur.fetchall():
            if _enqueue_ref(cur, (row or {}).get("media_path"), "child_messages", (row or {}).get("child_message_id")):
                summary["media_enqueued"] += 1

        # ---- 4b. R2 media: media_assets rows (transcoded/sanitized variants).
        # media_assets carries its own R2 keys (source_r2_key,
        # published_reference, poster_reference) which can differ from the
        # posts-table columns; the posts DELETE cascades these rows, so their
        # keys must be enqueued first or the objects are stranded. ----
        cur.execute(
            """SELECT media_id, source_r2_key, published_reference, poster_reference
               FROM media_assets
               WHERE post_id IN (SELECT post_id FROM posts WHERE child_id=%s)""",
            (child_id,),
        )
        for row in cur.fetchall():
            for column in ("source_r2_key", "published_reference", "poster_reference"):
                if _enqueue_ref(cur, (row or {}).get(column), "media_assets", (row or {}).get("media_id")):
                    summary["media_enqueued"] += 1

        # ---- 4c. R2 media: deleted_posts tombstones. These rows hold
        # media_path/story_music_path from earlier deletes whose R2 objects
        # were never queued (the web delete path unlinks local files only).
        # Clear Everything wipes the tombstones, so enqueue first. ----
        cur.execute(
            "SELECT deleted_post_id, media_path, story_music_path FROM deleted_posts WHERE child_id=%s",
            (child_id,),
        )
        for row in cur.fetchall():
            for column in ("media_path", "story_music_path"):
                if _enqueue_ref(cur, (row or {}).get(column), "deleted_posts", (row or {}).get("deleted_post_id")):
                    summary["media_enqueued"] += 1

        # ---- 5. Content rows (posts delete cascades comments/likes/media_assets/
        # post_tags/saved_posts/story_reactions/story_views on the child's posts) ----
        cur.execute("DELETE FROM posts WHERE child_id=%s", (child_id,))
        summary["posts"] = cur.rowcount
        cur.execute("DELETE FROM upload_sessions WHERE child_id=%s", (child_id,))
        summary["upload_sessions"] = cur.rowcount
        cur.execute("DELETE FROM chat_upload_sessions WHERE child_id=%s", (child_id,))
        summary["chat_upload_sessions"] = cur.rowcount

        # ---- 6. Chats: conversations involving the child go for BOTH
        # participants (no dangling half-conversation); message rows cascade. ----
        cur.execute(
            "DELETE FROM child_conversations WHERE child1_id=%s OR child2_id=%s",
            (child_id, child_id),
        )
        summary["conversations"] = cur.rowcount

        # ---- 7. Social graph, both directions ----
        cur.execute(
            "DELETE FROM followers WHERE child_id=%s OR following_child_id=%s",
            (child_id, child_id),
        )
        summary["follows"] = cur.rowcount
        cur.execute(
            "DELETE FROM blocked_users WHERE blocker_id=%s OR blocked_id=%s",
            (child_id, child_id),
        )
        summary["blocks"] = cur.rowcount
        cur.execute(
            "DELETE FROM muted_users WHERE muter_id=%s OR muted_id=%s",
            (child_id, child_id),
        )
        summary["mutes"] = cur.rowcount

        # ---- 8. Everything else scoped to the child ----
        for table, column in _CHILD_SCOPED_TABLES:
            cur.execute(f"DELETE FROM {table} WHERE {column}=%s", (child_id,))
            summary[table] = cur.rowcount

        # ---- 9. Settings back to defaults (same scope as Reset Settings) ----
        cur.execute(
            """INSERT INTO child_time_limits(child_id,daily_limit_minutes,strict_mode,bonus_minutes,bonus_date)
               VALUES(%s,60,TRUE,0,NULL)
               ON CONFLICT(child_id) DO UPDATE SET
                 daily_limit_minutes=60,strict_mode=TRUE,bonus_minutes=0,bonus_date=NULL,updated_at=NOW()""",
            (child_id,),
        )
        cur.execute(
            "UPDATE users SET parent_paused=FALSE WHERE user_id=%s AND role='CHILD'",
            (child_id,),
        )
        # ---- 9b. Invalidate the child's auth sessions inside the transaction
        # so old tokens die atomically with the wipe (a post-transaction bump
        # that silently fails would leave stale tokens valid). ----
        cur.execute(
            "UPDATE users SET session_version=COALESCE(session_version,1)+1 WHERE user_id=%s AND role='CHILD'",
            (child_id,),
        )

        # ---- 10. Audit + notify (same durable log other parent actions use) ----
        cur.execute(
            """INSERT INTO activity_logs(child_id,activity_type,activity_data)
               VALUES(%s,'PARENT_CLEAR_EVERYTHING',%s::jsonb)""",
            (child_id, '{"cleared_by_parent": %d}' % int(parent_id)),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    # Notify outside the transaction so a notification failure cannot roll
    # back the reset. Auth sessions were already invalidated in-transaction
    # via the session_version bump above; restart_child_sessions finalizes
    # any usage-session bookkeeping defensively.
    try:
        from services.usage import restart_child_sessions
        from services.social import notify

        restart_child_sessions(child_id)
        notify(
            child_id,
            "PARENT_CONTROLS",
            "Your parent cleared your LittleNet activity and restored defaults. "
            "Your login and family link are unchanged.",
            "/child/dashboard/",
            int(parent_id),
        )
    except Exception:
        pass
    return summary
