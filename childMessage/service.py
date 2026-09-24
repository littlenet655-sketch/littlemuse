from database.connection import fetch_one,fetch_all,execute
from services.social import can_interact


def conversation(a,b):
    """Return/create a conversation only while the pair is currently authorized."""
    if not can_interact(a,b):return None
    x,y=sorted((a,b))
    r=fetch_one('SELECT conversation_id FROM child_conversations WHERE child1_id=%s AND child2_id=%s',(x,y))
    if r:return r['conversation_id']
    try:
        return execute('INSERT INTO child_conversations(child1_id,child2_id) VALUES(%s,%s) RETURNING conversation_id',(x,y),returning=True)['conversation_id']
    except Exception:
        # A concurrent request may have created the same unique pair.
        r=fetch_one('SELECT conversation_id FROM child_conversations WHERE child1_id=%s AND child2_id=%s',(x,y))
        return r['conversation_id'] if r and can_interact(a,b) else None


def messages(cid, viewer, limit=None, before_id=None, after_id=None):
    """Read messages only for an authorized participant pair using fixed SQL."""
    conv = fetch_one(
        'SELECT child1_id,child2_id FROM child_conversations WHERE conversation_id=%s AND (child1_id=%s OR child2_id=%s)',
        (cid, viewer, viewer),
    )
    if not conv:
        return []
    peer = conv['child2_id'] if conv['child1_id'] == viewer else conv['child1_id']
    if not can_interact(viewer, peer):
        return []
    # Bound the page size like conversations_page does: an unbounded LIMIT
    # lets one caller force a full-history DB read (audit T1-005).
    try:
        safe_limit = max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        safe_limit = 100
    rows = fetch_all(
        """SELECT m.*, u.full_name,
                  rm.message_text AS reply_message_text,
                  rm.message_type AS reply_message_type,
                  rm.sender_child_id AS reply_sender_child_id,
                  COALESCE(
                    (SELECT jsonb_object_agg(grouped.emoji, grouped.n)
                     FROM (
                       SELECT mr.emoji, COUNT(*)::int AS n
                       FROM message_reactions mr
                       WHERE mr.message_id=m.child_message_id
                       GROUP BY mr.emoji
                     ) grouped),
                    '{}'::jsonb
                  ) AS reactions,
                  (SELECT mr2.emoji
                   FROM message_reactions mr2
                   WHERE mr2.message_id=m.child_message_id AND mr2.child_id=%s
                   LIMIT 1) AS viewer_reaction
           FROM child_messages m
           JOIN users u ON u.user_id = m.sender_child_id
           LEFT JOIN child_messages rm
             ON rm.child_message_id=m.reply_to_message_id
            AND rm.conversation_id=m.conversation_id
            AND rm.is_deleted=FALSE
            AND rm.moderation_status='ALLOWED'
           WHERE m.conversation_id = %s AND m.is_deleted = FALSE
             AND (
               m.moderation_status = 'ALLOWED'
               OR (m.sender_child_id = %s AND m.moderation_status = 'REVIEW')
             )
             AND (%s::bigint IS NULL OR m.child_message_id < %s::bigint)
             AND (%s::bigint IS NULL OR m.child_message_id > %s::bigint)
           ORDER BY m.sent_at DESC, m.child_message_id DESC
           LIMIT %s""",
        (viewer, cid, viewer, before_id, before_id, after_id, after_id, safe_limit),
    )
    return list(reversed(rows))


TYPING_TTL_SECONDS = 6


def set_typing(cid, user_id):
    """Record a typing heartbeat. Ephemeral: validity is decided at read time."""
    execute(
        """INSERT INTO chat_typing(conversation_id, user_id, updated_at)
           VALUES(%s, %s, NOW())
           ON CONFLICT (conversation_id, user_id)
           DO UPDATE SET updated_at = NOW()""",
        (cid, user_id),
    )
    # Opportunistic cleanup of stale heartbeats; cheap indexed delete.
    try:
        execute(
            "DELETE FROM chat_typing WHERE updated_at < NOW() - (%s || ' seconds')::interval",
            (TYPING_TTL_SECONDS * 4,),
        )
    except Exception:
        pass


def is_peer_typing(cid, viewer):
    """True if the other participant's typing heartbeat is fresh."""
    row = fetch_one(
        """SELECT 1 FROM chat_typing
           WHERE conversation_id = %s AND user_id != %s
             AND updated_at > NOW() - (%s || ' seconds')::interval
           LIMIT 1""",
        (cid, viewer, TYPING_TTL_SECONDS),
    )
    return bool(row)


def conversations_page(uid, limit=20, offset=0):
    """One page of uid's conversations with the latest visible message each.

    Single query: participants only (child1_id/child2_id), peer profile info,
    and the newest ALLOWED, non-deleted message per conversation via
    DISTINCT ON. The caller still applies can_interact per row on the page;
    this helper never returns conversations uid is not a participant of.
    """
    try:
        safe_limit = max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        safe_limit = 20
    try:
        safe_offset = max(0, int(offset))
    except (TypeError, ValueError):
        safe_offset = 0
    rows = fetch_all(
        """SELECT * FROM (
               SELECT DISTINCT ON (c.conversation_id)
                      c.conversation_id, c.child1_id, c.child2_id, c.created_at,
                      CASE WHEN c.child1_id=%s THEN u2.full_name ELSE u1.full_name END AS peer_name,
                      CASE WHEN c.child1_id=%s THEN u2.username ELSE u1.username END AS peer_username,
                      CASE WHEN c.child1_id=%s THEN c.child2_id ELSE c.child1_id END AS peer_id,
                      CASE WHEN c.child1_id=%s THEN cp2.profile_picture ELSE cp1.profile_picture END AS peer_avatar,
                      m.message_text AS last_message_text,
                      m.message_type AS last_message_type,
                      m.sent_at AS last_sent_at,
                      m.sender_child_id AS last_sender_child_id,
                      m.is_seen AS last_is_seen
               FROM child_conversations c
               JOIN users u1 ON u1.user_id = c.child1_id
               JOIN users u2 ON u2.user_id = c.child2_id
               LEFT JOIN child_profiles cp1 ON cp1.child_id = u1.user_id
               LEFT JOIN child_profiles cp2 ON cp2.child_id = u2.user_id
               LEFT JOIN child_messages m
                 ON m.conversation_id = c.conversation_id
                AND m.moderation_status = 'ALLOWED'
                AND m.is_deleted = FALSE
               WHERE c.child1_id = %s OR c.child2_id = %s
               ORDER BY c.conversation_id, m.sent_at DESC NULLS LAST, m.child_message_id DESC NULLS LAST
           ) t
           ORDER BY t.last_sent_at DESC NULLS LAST, t.conversation_id DESC
           LIMIT %s OFFSET %s""",
        (uid, uid, uid, uid, uid, uid, safe_limit, safe_offset),
    )
    return rows
