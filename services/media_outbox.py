"""Durable reconciliation for private R2 media queued by database triggers."""
from __future__ import annotations

from database.connection import execute, fetch_all


def enqueue_delete(reference: str, source_table: str = "compensation", source_id=None) -> None:
    """Persist a private-object deletion request for retry after transient failures."""
    if not reference or not str(reference).startswith("uploads/r2/"):
        return
    execute(
        """INSERT INTO media_delete_outbox(reference,source_table,source_id)
           VALUES(%s,%s,%s)
           ON CONFLICT(reference) DO UPDATE
             SET completed_at=NULL,last_error=NULL,source_table=EXCLUDED.source_table,
                 source_id=COALESCE(EXCLUDED.source_id,media_delete_outbox.source_id)""",
        (reference, source_table, source_id),
    )


def reconcile_pending_deletes(limit: int = 20) -> dict:
    try:
        limit = max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        limit = 20
    rows = fetch_all(
        """SELECT outbox_id,reference FROM media_delete_outbox
           WHERE completed_at IS NULL ORDER BY created_at,outbox_id LIMIT %s""",
        (limit,),
    )
    completed = 0
    failed = 0
    from services.object_storage import delete_reference

    for row in rows:
        try:
            delete_reference(row["reference"])
            execute(
                """UPDATE media_delete_outbox
                   SET completed_at=COALESCE(completed_at,NOW()),
                       attempts=attempts+1,last_error=NULL
                   WHERE outbox_id=%s""",
                (row["outbox_id"],),
            )
            completed += 1
        except Exception as exc:
            execute(
                """UPDATE media_delete_outbox SET attempts=attempts+1,last_error=%s
                   WHERE outbox_id=%s""",
                (f"{type(exc).__name__}: {exc}"[:1000], row["outbox_id"]),
            )
            failed += 1
    return {"checked": len(rows), "completed": completed, "failed": failed}


# R2 reference columns on the posts table, in enqueue order.
_POST_MEDIA_COLUMNS = ("source_media_path", "media_path", "poster_path", "story_music_path")


def enqueue_post_media_deletes(post, source_id=None) -> int:
    """Enqueue every stored media reference on a posts row for durable deletion.

    `post` is a mapping-like row (e.g. RealDictRow from fetch_one).
    enqueue_delete silently ignores anything that is not an R2 reference
    (legacy local paths, URLs, empty strings), so every media column is safe
    to pass unconditionally. Returns the number of columns holding a
    non-empty reference.
    """
    row = post or {}
    enqueued = 0
    for column in _POST_MEDIA_COLUMNS:
        reference = row.get(column)
        if reference:
            enqueue_delete(
                str(reference),
                source_table="posts",
                source_id=source_id if source_id is not None else row.get("post_id"),
            )
            enqueued += 1
    return enqueued
