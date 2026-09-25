"""Behavioral proof of one canonical R2 reference lifecycle.

With LITTLENET_R2_WRITE_PREFIX=littlemuse, the physical R2 object key, the
persisted reference, the signed playback key, and the deletion target must all
agree. A fake boto client captures every Key so these tests prove the identity
end to end instead of asserting on source strings.

Complements:
- tests/test_littlemuse_resource_isolation.py (deployment namespace scoping)
- tests/test_release_experience_contracts.py::test_direct_upload_session_uses_deployment_scoped_r2_key
  (source-level contract that the worker keeps upload_file's return)
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest

from services import object_storage
from services import chat_media
from services.media_processor import (
    delete_orphaned_media_refs,
    reconcile_abandoned_upload_sessions,
    sanitize_and_promote_media,
)


def _make_jpeg_bytes() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (16, 16), (200, 30, 30)).save(buf, format="JPEG")
    return buf.getvalue()


_JPEG_BYTES = _make_jpeg_bytes()


class _FakeR2Client:
    """Captures (operation, key) for every boto call the storage layer makes."""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    def upload_file(self, Filename, Bucket, Key, ExtraArgs=None):
        self.calls.append(("upload", Key))

    def delete_object(self, Bucket, Key):
        self.calls.append(("delete", Key))
        return {}

    def generate_presigned_url(self, operation, Params, ExpiresIn):
        self.calls.append(("presign", Params["Key"]))
        return f"https://example.invalid/{operation}/{Params['Key']}"

    def head_object(self, Bucket, Key):
        self.calls.append(("head", Key))
        return {"ContentLength": 1234, "ContentType": "image/jpeg", "ETag": '"abc"'}

    def download_file(self, Bucket, Key, Filename):
        self.calls.append(("download", Key))
        Path(Filename).write_bytes(_JPEG_BYTES)


@pytest.fixture
def r2(monkeypatch):
    monkeypatch.setenv("LITTLENET_R2_WRITE_PREFIX", "littlemuse")
    monkeypatch.setenv("R2_BUCKET", "private-test")
    monkeypatch.setenv("R2_ACCOUNT_ID", "testacct")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "x")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "y")
    client = _FakeR2Client()
    monkeypatch.setattr(object_storage, "_client", lambda: client)
    monkeypatch.setattr(object_storage, "_enabled", lambda: True)
    monkeypatch.setattr(object_storage, "_acknowledge_deleted_reference", lambda ref: None)
    return client


def _keys(client, op):
    return [key for got_op, key in client.calls if got_op == op]


def test_presign_worker_playback_delete_resolve_to_one_identical_key(r2, tmp_path):
    # 1. presign: client PUTs bytes to the deployment-namespaced quarantine key
    quarantine_ref = object_storage.new_reference("quarantine/7/uid-1/source.jpg")
    assert quarantine_ref == "uploads/r2/littlemuse/quarantine/7/uid-1/source.jpg"
    object_storage.signed_upload_url(quarantine_ref, "image/jpeg")

    # 2. worker publishes the moderated bytes
    src = tmp_path / "media.jpg"
    src.write_bytes(_JPEG_BYTES)
    published_ref = object_storage.upload_file(str(src), "posts/7/42_media.jpg", content_type="image/jpeg")
    assert published_ref == "uploads/r2/littlemuse/posts/7/42_media.jpg"

    # 3. playback signs the persisted reference
    object_storage.signed_download_url(published_ref)

    # 4. deletion targets the same reference
    object_storage.delete_reference(published_ref)

    assert _keys(r2, "presign") == [
        "littlemuse/quarantine/7/uid-1/source.jpg",  # presigned PUT
        "littlemuse/posts/7/42_media.jpg",  # presigned GET (playback)
    ]
    assert _keys(r2, "upload") == ["littlemuse/posts/7/42_media.jpg"]
    assert _keys(r2, "delete") == ["littlemuse/posts/7/42_media.jpg"]
    # upload, playback-sign, and delete resolve to one identical physical key
    assert _keys(r2, "upload")[0] == _keys(r2, "presign")[1] == _keys(r2, "delete")[0]


def test_worker_persists_upload_file_return_verbatim(r2, monkeypatch):
    """Sentinel test: the promote path must keep upload_file's return verbatim.

    sanitize_and_promote_media is the shared promote step used by the async
    media-job worker and the chat moderation path. If it ever reconstructed
    the reference (dropping the deployment prefix), playback would sign a
    nonexistent key.
    """
    sentinel = "uploads/r2/littlemuse/posts/9/77_media.jpg#VERBATIM"
    monkeypatch.setattr(
        object_storage, "download_file", lambda ref, dest: Path(dest).write_bytes(_JPEG_BYTES)
    )
    monkeypatch.setattr(object_storage, "upload_file", lambda *a, **k: sentinel)

    media_ref, poster_ref = sanitize_and_promote_media(
        77, 9, "uploads/r2/littlemuse/quarantine/9/q/source.jpg", "post", "IMAGE"
    )
    assert media_ref == sentinel
    assert poster_ref is None


def test_delete_reference_deletes_the_in_namespace_key(r2):
    object_storage.delete_reference("uploads/r2/littlemuse/posts/7/42_media.jpg")
    assert r2.calls == [("delete", "littlemuse/posts/7/42_media.jpg")]


def test_out_of_namespace_reference_makes_zero_delete_calls(r2):
    # Clone protection: a cloned LittleMuse DB may reference old LittleNet
    # objects; its delete path must never remove those shared-bucket objects.
    object_storage.delete_reference("uploads/r2/posts/7/old.jpg")
    object_storage.delete_reference("not-a-reference-at-all")
    object_storage.delete_reference(None)
    assert [op for op, _ in r2.calls if op == "delete"] == []


def test_orphan_cleanup_deletes_the_same_key_and_enqueues_it_on_failure(r2, tmp_path, monkeypatch):
    src = tmp_path / "m.jpg"
    src.write_bytes(_JPEG_BYTES)
    ref = object_storage.upload_file(str(src), "posts/7/42_media.jpg", content_type="image/jpeg")

    failed = delete_orphaned_media_refs([ref, None], context="test-orphan")
    assert failed == []
    assert ("upload", "littlemuse/posts/7/42_media.jpg") in r2.calls
    assert ("delete", "littlemuse/posts/7/42_media.jpg") in r2.calls

    # Failure path: the identical ref is handed to the durable delete outbox.
    import services.media_outbox as outbox

    enqueued = []
    monkeypatch.setattr(outbox, "enqueue_delete", lambda ref, **kw: enqueued.append((ref, kw)))

    def _boom(reference):
        raise RuntimeError("r2 outage")

    monkeypatch.setattr(object_storage, "delete_reference", _boom)
    failed = delete_orphaned_media_refs([ref], context="test-orphan-fail")
    assert failed == [ref]
    assert [e[0] for e in enqueued] == [ref]


def test_abandoned_session_cleanup_resolves_canonical_key_and_marks_cancelled(r2, monkeypatch):
    import services.media_processor as mp

    row = {
        "upload_id": "uid-abc",
        "child_id": 7,
        "object_key": "uploads/r2/littlemuse/quarantine/7/uid-abc/source.jpg",
        "extension": "jpg",
    }
    monkeypatch.setattr(mp, "fetch_all", lambda sql, params=(): [row])
    updates = []
    monkeypatch.setattr(mp, "execute_count", lambda sql, params=(): updates.append((sql, params)) or 1)

    res = mp.reconcile_abandoned_upload_sessions(stale_seconds=3600)

    assert res["ok"] is True
    assert res["cleaned"] == ["uid-abc"]
    # The canonical deployment-namespaced key is what gets deleted...
    assert ("delete", "littlemuse/quarantine/7/uid-abc/source.jpg") in r2.calls
    # ...and the session is marked CANCELLED exactly once so it never sweeps twice.
    assert len(updates) == 1
    assert "CANCELLED" in updates[0][0]
    assert updates[0][1] == ("uid-abc",)


def test_chat_presign_moderate_promote_delete_chain_key_equality(r2, monkeypatch):
    # presign (mirrors mobile_kids_chat_upload_session)
    quarantine_ref = object_storage.new_reference("chat_quarantine/7/chat-uid-1/source.jpg")
    assert quarantine_ref == "uploads/r2/littlemuse/chat_quarantine/7/chat-uid-1/source.jpg"
    object_storage.signed_upload_url(quarantine_ref, "image/jpeg")

    # moderate -> promote (ALLOW path): the promoted ref is upload_file's
    # return verbatim, in the chat namespace with the deployment prefix
    sentinel = "uploads/r2/littlemuse/chat/7/55_media.jpg#VERBATIM"
    monkeypatch.setattr(
        object_storage, "download_file", lambda ref, dest: Path(dest).write_bytes(_JPEG_BYTES)
    )
    monkeypatch.setattr(object_storage, "upload_file", lambda *a, **k: sentinel)
    media_ref, _ = sanitize_and_promote_media(55, 7, quarantine_ref, "chat", "IMAGE")
    assert media_ref == sentinel

    # delete quarantine after promotion (mirrors chat_media._cleanup_quarantine)
    chat_media._cleanup_quarantine(quarantine_ref, message_id=55)

    assert _keys(r2, "presign") == ["littlemuse/chat_quarantine/7/chat-uid-1/source.jpg"]
    assert _keys(r2, "delete") == ["littlemuse/chat_quarantine/7/chat-uid-1/source.jpg"]
    # The key the client uploaded to is exactly the key deleted after promotion.
    assert _keys(r2, "presign")[0] == _keys(r2, "delete")[0]
