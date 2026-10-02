"""Transactional media persistence helpers for child-created content.

Child media is moderated on ephemeral local disk, copied to the private R2 bucket,
and only then referenced by PostgreSQL. This ordering prevents an accepted DB row
from ever pointing at an unpersisted local child-media file. If the subsequent DB
write fails, callers compensate the private object immediately or queue a durable
retry in PostgreSQL.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

from services.object_storage import delete_reference, enabled, is_reference, upload_file


def persist_before_db(local_path: str | None, namespace: str, owner_id: int) -> str | None:
    """Persist one moderated local file to private R2 before its DB row is created."""
    if not local_path:
        return None
    if is_reference(local_path):
        return local_path
    if not enabled():
        raise RuntimeError("Cloudflare R2 is required before child media can be published")

    path = Path(local_path)
    if not path.is_file():
        raise FileNotFoundError(local_path)
    safe_name = path.name.replace(" ", "_")
    key = f"{namespace}/{int(owner_id)}/{uuid.uuid4().hex}_{safe_name}"
    reference = upload_file(str(path), key)
    try:
        os.remove(path)
    except OSError:
        pass
    return reference


def rollback_reference(reference: str | None) -> None:
    """Compensate an R2 upload when its database write did not commit."""
    if not reference or not is_reference(reference):
        return
    try:
        delete_reference(reference)
        return
    except Exception as exc:
        # Preserve retry intent if the bucket/network is unavailable. The object
        # remains private and unreferenced until the durable outbox removes it.
        try:
            from services.media_outbox import enqueue_delete

            enqueue_delete(reference, source_table="compensation")
        except Exception:
            # If both R2 and PostgreSQL are unavailable simultaneously there is no
            # durable coordinator left to write to. The private object is still not
            # reachable through LittleNet because no application row references it.
            raise RuntimeError("media rollback could not be persisted") from exc
