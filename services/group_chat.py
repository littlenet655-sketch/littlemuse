"""Parent-gated group chat domain rules for LittleMuse."""
from __future__ import annotations

from typing import Iterable

from database.connection import execute, fetch_all, fetch_one, get_db_connection
from parent.service import owns
from services.controls import feature_allowed
from services.social import can_interact, notify, parent_notify

MAX_INVITEES = 5
MIN_INVITEES = 2
MAX_GROUP_MEMBERS = MAX_INVITEES + 1


def group_features_allowed(child_id: int) -> bool:
    return bool(
        feature_allowed(int(child_id), "messaging")
        and feature_allowed(int(child_id), "group_chats")
    )


def _normalize_member_ids(owner_id: int, values: Iterable[object]) -> list[int]:
    ids: list[int] = []
    for raw in values:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            raise ValueError("invalid_group_member")
        if value <= 0 or value == int(owner_id):
            raise ValueError("invalid_group_member")
        if value not in ids:
            ids.append(value)
    if not MIN_INVITEES <= len(ids) <= MAX_INVITEES:
        raise ValueError("group_member_count")
    return ids


def create_group(owner_id: int, title: str, member_ids: Iterable[object]) -> int:
    owner_id = int(owner_id)
    clean_title = " ".join(str(title or "").split()).strip()
    if len(clean_title) < 2 or len(clean_title) > 60:
        raise ValueError("invalid_group_title")
    if not group_features_allowed(owner_id):
        raise PermissionError("group_chats_disabled_by_parent")

    members = _normalize_member_ids(owner_id, member_ids)
    for member_id in members:
        if not can_interact(owner_id, member_id):
            raise PermissionError("approved_connection_required")
        if not group_features_allowed(member_id):
            raise PermissionError("member_group_chats_disabled")

    conn = get_db_connection()
    group_id = None
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO child_groups(owner_child_id,title,status)
               VALUES(%s,%s,'PENDING') RETURNING group_id""",
            (owner_id, clean_title),
        )
        group_id = int(cur.fetchone()["group_id"])
        cur.execute(
            """INSERT INTO child_group_members(
                   group_id,child_id,role,status,invited_by,child_accepted_at
               ) VALUES(%s,%s,'OWNER','PARENT_PENDING',%s,NOW())""",
            (group_id, owner_id, owner_id),
        )
        for member_id in members:
            cur.execute(
                """INSERT INTO child_group_members(
                       group_id,child_id,role,status,invited_by
                   ) VALUES(%s,%s,'MEMBER','INVITED',%s)""",
                (group_id, member_id, owner_id),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    parent_notify(
        owner_id,
        "GROUP_CHAT_APPROVAL",
        f"Approve the new group chat “{clean_title}” before it can open",
        f"/parent/groups/{group_id}/",
    )
    for member_id in members:
        notify(
            member_id,
            "GROUP_INVITE",
            f"You were invited to the group “{clean_title}”. Accepting still needs parent approval.",
            f"/groups/{group_id}/invite/",
            owner_id,
        )
    return int(group_id)


def _member_row(group_id: int, child_id: int):
    return fetch_one(
        """SELECT g.group_id,g.owner_child_id,g.title,g.status AS group_status,
                  gm.role,gm.status AS member_status,gm.last_read_message_id
           FROM child_groups g
           JOIN child_group_members gm ON gm.group_id=g.group_id
           WHERE g.group_id=%s AND gm.child_id=%s""",
        (int(group_id), int(child_id)),
    )


def can_access_group(group_id: int, child_id: int) -> bool:
    row = _member_row(group_id, child_id)
    return bool(
        row
        and row.get("group_status") == "ACTIVE"
        and row.get("member_status") == "ACTIVE"
        and group_features_allowed(child_id)
    )


def list_groups_for_child(child_id: int) -> dict:
    child_id = int(child_id)
    rows = fetch_all(
        """SELECT g.group_id,g.owner_child_id,g.title,g.status AS group_status,
                  gm.role,gm.status AS member_status,gm.last_read_message_id,g.updated_at,
                  (SELECT COUNT(*) FROM child_group_members x
                   WHERE x.group_id=g.group_id AND x.status='ACTIVE') AS active_members,
                  latest.group_message_id AS last_message_id,
                  latest.message_text AS last_message_text,
                  latest.sent_at AS last_message_at,
                  latest.sender_child_id AS last_sender_child_id,
                  COALESCE(
                    (SELECT COUNT(*) FROM child_group_messages unread
                     WHERE unread.group_id=g.group_id
                       AND unread.moderation_status='ALLOWED'
                       AND unread.is_deleted=FALSE
                       AND unread.sender_child_id<>%s
                       AND unread.group_message_id>COALESCE(gm.last_read_message_id,0)),
                    0
                  ) AS unread_count
           FROM child_groups g
           JOIN child_group_members gm ON gm.group_id=g.group_id
           LEFT JOIN LATERAL (
             SELECT m.group_message_id,m.message_text,m.sent_at,m.sender_child_id
             FROM child_group_messages m
             WHERE m.group_id=g.group_id
               AND m.moderation_status='ALLOWED'
               AND m.is_deleted=FALSE
             ORDER BY m.group_message_id DESC
             LIMIT 1
           ) latest ON TRUE
           WHERE gm.child_id=%s
             AND gm.status IN ('INVITED','PARENT_PENDING','ACTIVE')
             AND g.status<>'ARCHIVED'
           ORDER BY COALESCE(latest.sent_at,g.updated_at) DESC,g.group_id DESC""",
        (child_id, child_id),
    ) or []
    active = []
    invitations = []
    pending = []
    for row in rows:
        item = dict(row)
        state = item.get("member_status")
        if state == "ACTIVE" and item.get("group_status") == "ACTIVE" and group_features_allowed(child_id):
            active.append(item)
        elif state == "INVITED":
            invitations.append(item)
        elif state == "PARENT_PENDING":
            pending.append(item)
    return {"groups": active, "invitations": invitations, "pending": pending}


def respond_to_invite(group_id: int, child_id: int, accept: bool) -> str:
    group_id = int(group_id)
    child_id = int(child_id)
    row = _member_row(group_id, child_id)
    if not row or row.get("member_status") != "INVITED" or row.get("group_status") == "ARCHIVED":
        raise LookupError("group_invite_not_found")
    if not accept:
        execute(
            """UPDATE child_group_members
               SET status='DECLINED',updated_at=NOW()
               WHERE group_id=%s AND child_id=%s AND status='INVITED'""",
            (group_id, child_id),
        )
        return "DECLINED"
    if not group_features_allowed(child_id):
        raise PermissionError("group_chats_disabled_by_parent")
    owner_id = int(row["owner_child_id"])
    if not can_interact(child_id, owner_id):
        raise PermissionError("approved_connection_required")
    execute(
        """UPDATE child_group_members
           SET status='PARENT_PENDING',child_accepted_at=NOW(),updated_at=NOW()
           WHERE group_id=%s AND child_id=%s AND status='INVITED'""",
        (group_id, child_id),
    )
    parent_notify(
        child_id,
        "GROUP_CHAT_APPROVAL",
        f"Approve joining the group chat “{row['title']}”",
        f"/parent/groups/{group_id}/",
    )
    return "PARENT_PENDING"


def parent_pending_group_memberships(parent_id: int) -> list[dict]:
    rows = fetch_all(
        """SELECT g.group_id,g.title,g.owner_child_id,gm.child_id,gm.role,gm.status,
                  gm.child_accepted_at,u.full_name,u.username
           FROM child_group_members gm
           JOIN child_groups g ON g.group_id=gm.group_id
           JOIN users u ON u.user_id=gm.child_id
           JOIN parent_child_map pcm ON pcm.child_id=gm.child_id
           WHERE (pcm.parent_id=%s OR pcm.verified_parent_id=%s)
             AND gm.status='PARENT_PENDING'
             AND g.status<>'ARCHIVED'
           ORDER BY gm.updated_at ASC,g.group_id ASC""",
        (int(parent_id), int(parent_id)),
    ) or []
    return [dict(row) for row in rows]


def resolve_parent_membership(parent_id: int, group_id: int, child_id: int, approve: bool) -> str:
    parent_id = int(parent_id)
    group_id = int(group_id)
    child_id = int(child_id)
    if not owns(parent_id, child_id):
        raise PermissionError("child_not_found")
    row = _member_row(group_id, child_id)
    if not row or row.get("member_status") != "PARENT_PENDING":
        raise LookupError("group_request_not_found")

    if approve and not group_features_allowed(child_id):
        raise PermissionError("group_chats_disabled_by_parent")

    if not approve:
        if row.get("role") == "OWNER":
            execute("UPDATE child_groups SET status='ARCHIVED',updated_at=NOW() WHERE group_id=%s", (group_id,))
            execute(
                """UPDATE child_group_members
                   SET status=CASE WHEN child_id=%s THEN 'REMOVED'
                                   WHEN status IN ('INVITED','PARENT_PENDING') THEN 'REMOVED'
                                   ELSE status END,
                       updated_at=NOW()
                   WHERE group_id=%s""",
                (child_id, group_id),
            )
        else:
            execute(
                """UPDATE child_group_members
                   SET status='REMOVED',updated_at=NOW()
                   WHERE group_id=%s AND child_id=%s""",
                (group_id, child_id),
            )
        notify(child_id, "GROUP_APPROVAL", f"Group access for “{row['title']}” was not approved.", "/messages/", parent_id)
        return "REJECTED"

    execute(
        """UPDATE child_group_members
           SET status='ACTIVE',parent_approved_at=NOW(),
               parent_approved_by=%s,updated_at=NOW()
           WHERE group_id=%s AND child_id=%s""",
        (parent_id, group_id, child_id),
    )
    if row.get("role") == "OWNER":
        execute(
            """UPDATE child_groups SET status='ACTIVE',updated_at=NOW()
               WHERE group_id=%s AND status='PENDING'""",
            (group_id,),
        )
    notify(child_id, "GROUP_APPROVAL", f"Group access for “{row['title']}” is approved.", f"/groups/{group_id}/", parent_id)
    return "APPROVED"


def leave_group(group_id: int, child_id: int) -> str:
    row = _member_row(group_id, child_id)
    if not row or row.get("member_status") not in {"ACTIVE", "INVITED", "PARENT_PENDING"}:
        raise LookupError("group_not_found")
    if row.get("role") == "OWNER":
        execute("UPDATE child_groups SET status='ARCHIVED',updated_at=NOW() WHERE group_id=%s", (int(group_id),))
        execute(
            """UPDATE child_group_members
               SET status=CASE WHEN status='DECLINED' THEN status ELSE 'REMOVED' END,updated_at=NOW()
               WHERE group_id=%s""",
            (int(group_id),),
        )
        return "ARCHIVED"
    execute(
        """UPDATE child_group_members SET status='LEFT',updated_at=NOW()
           WHERE group_id=%s AND child_id=%s""",
        (int(group_id), int(child_id)),
    )
    return "LEFT"


def group_members(group_id: int, viewer_id: int) -> list[dict]:
    if not can_access_group(group_id, viewer_id):
        raise PermissionError("group_unavailable")
    rows = fetch_all(
        """SELECT gm.child_id,gm.role,gm.status,u.full_name,u.username,cp.profile_picture
           FROM child_group_members gm
           JOIN users u ON u.user_id=gm.child_id
           LEFT JOIN child_profiles cp ON cp.child_id=gm.child_id
           WHERE gm.group_id=%s AND gm.status='ACTIVE'
           ORDER BY CASE WHEN gm.role='OWNER' THEN 0 ELSE 1 END,u.full_name,u.user_id""",
        (int(group_id),),
    ) or []
    return [dict(row) for row in rows]


def group_messages(group_id: int, viewer_id: int, limit: int = 40, before_id: int | None = None) -> list[dict]:
    if not can_access_group(group_id, viewer_id):
        raise PermissionError("group_unavailable")
    safe_limit = max(1, min(int(limit or 40), 80))
    params = [int(viewer_id), int(group_id), int(viewer_id)]
    cursor_sql = ""
    if before_id:
        cursor_sql = " AND m.group_message_id < %s"
        params.append(int(before_id))
    params.append(safe_limit)
    # The cursor fragment is selected from a fixed boolean branch only; no user
    # text is ever interpolated into SQL identifiers or values.
    sql = """SELECT m.group_message_id,m.group_id,m.sender_child_id,m.message_text,
                    m.reply_to_group_message_id,m.moderation_status,m.sent_at,
                    u.full_name,u.username,cp.profile_picture,
                    rm.message_text AS reply_message_text,
                    rm.sender_child_id AS reply_sender_child_id,
                    COALESCE(
                      (SELECT jsonb_object_agg(x.emoji,x.n)
                       FROM (
                         SELECT r.emoji,COUNT(*)::int AS n
                         FROM group_message_reactions r
                         WHERE r.group_message_id=m.group_message_id
                         GROUP BY r.emoji
                       ) x),
                      '{}'::jsonb
                    ) AS reactions,
                    (SELECT r2.emoji FROM group_message_reactions r2
                     WHERE r2.group_message_id=m.group_message_id AND r2.child_id=%s
                     LIMIT 1) AS viewer_reaction
             FROM child_group_messages m
             JOIN users u ON u.user_id=m.sender_child_id
             LEFT JOIN child_profiles cp ON cp.child_id=m.sender_child_id
             LEFT JOIN child_group_messages rm
               ON rm.group_message_id=m.reply_to_group_message_id
              AND rm.group_id=m.group_id AND rm.is_deleted=FALSE
              AND rm.moderation_status='ALLOWED'
             WHERE m.group_id=%s AND m.is_deleted=FALSE
               AND (
                 m.moderation_status='ALLOWED'
                 OR (m.sender_child_id=%s AND m.moderation_status='REVIEW')
               )"""
    if before_id:
        sql += " AND m.group_message_id < %s"
    sql += " ORDER BY m.group_message_id DESC LIMIT %s"
    rows = fetch_all(sql, tuple(params)) or []
    return list(reversed([dict(row) for row in rows]))


def mark_group_read(group_id: int, child_id: int, message_id: int | None) -> None:
    if not message_id or not can_access_group(group_id, child_id):
        return
    execute(
        """UPDATE child_group_members
           SET last_read_message_id=GREATEST(COALESCE(last_read_message_id,0),%s),updated_at=NOW()
           WHERE group_id=%s AND child_id=%s AND status='ACTIVE'""",
        (int(message_id), int(group_id), int(child_id)),
    )
