"""Upload security fixtures (mock-only: no DB, no R2, no Modal).

Covers v2 upload-session create/complete, chat upload-session complete and the
legacy web avatar route.
"""
import io
from unittest.mock import patch

import pytest

from app import app
from mobile.api import _issue_token


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


def _headers(user_id=7):
    token = _issue_token({"user_id": user_id, "role": "CHILD", "full_name": "Kid"})
    return {"Authorization": f"Bearer {token}"}


def _user(user_id=7):
    return {
        "user_id": user_id, "username": "kid", "full_name": "Kid",
        "email": "kid@test.invalid", "role": "CHILD", "age": 10,
        "account_status": "ACTIVE", "session_version": 1,
    }


class _Cursor:
    def __init__(self, handler):
        self.handler, self.statements, self._row = handler, [], None

    def execute(self, sql, params=None):
        q = " ".join(str(sql).split())
        self.statements.append((q, params))
        self._row = self.handler(q, params)

    def fetchone(self):
        return self._row

    def fetchall(self):
        return [self._row] if self._row else []


class _Conn:
    def __init__(self, handler):
        self.cur = _Cursor(handler)
        self.committed = self.rolled_back = False

    def cursor(self):
        return self.cur

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass


def _create(client, payload):
    with patch("mobile.api._mobile_token_revoked", return_value=False), \
         patch("mobile.api.fetch_one", return_value=_user()), \
         patch("mobile.api._child_gate", return_value=None), \
         patch("mobile.api.effective_categories", return_value=["Other"]), \
         patch("mobile.api.execute") as ins:
        resp = client.post("/api/mobile/v2/uploads/session", headers=_headers(), json=payload)
    return resp, ins


# ── v2 upload-session create ─────────────────────────────────────────────────
@pytest.mark.parametrize(
    "payload,error",
    [
        ({"media_type": "IMAGE", "extension": "php", "mime_type": "image/jpeg", "size_bytes": 10}, "unsupported_extension"),
        ({"media_type": "IMAGE", "extension": "svg", "mime_type": "image/svg+xml", "size_bytes": 10}, "unsupported_extension"),
        ({"media_type": "IMAGE", "extension": "jpg", "mime_type": "text/html", "size_bytes": 10}, "unsupported_mime_type"),
        ({"media_type": "VIDEO", "extension": "mp4", "mime_type": "image/png", "size_bytes": 10}, "unsupported_mime_type"),
        ({"media_type": "IMAGE", "extension": "jpg", "mime_type": "image/jpeg", "size_bytes": 0}, "file_size_required"),
        ({"media_type": "IMAGE", "extension": "jpg", "mime_type": "image/jpeg", "size_bytes": 20 * 1024 * 1024 + 1}, "file_size_exceeded"),
        ({"media_type": "VIDEO", "extension": "mp4", "mime_type": "video/mp4", "size_bytes": 100 * 1024 * 1024 + 1}, "file_size_exceeded"),
        ({"media_type": "AUDIO", "extension": "mp3", "mime_type": "audio/mpeg", "size_bytes": 10}, "invalid_media_type"),
        ({"kind": "story", "media_type": "VIDEO", "extension": "mp4", "mime_type": "video/mp4", "size_bytes": 50 * 1024 * 1024 + 1}, "file_size_exceeded"),
    ],
)
def test_v2_session_create_rejects_bad_input_before_any_write(client, payload, error):
    resp, ins = _create(client, payload)
    assert resp.status_code == 400
    assert resp.get_json()["error"] == error
    ins.assert_not_called()


def test_v2_session_create_object_key_is_server_built_not_from_filename(client):
    resp, ins = _create(client, {
        "media_type": "IMAGE", "filename": "../../etc/passwd/../x.jpg",
        "mime_type": "image/jpeg", "size_bytes": 1024,
    })
    assert resp.status_code == 200
    key = resp.get_json()["object_key"]
    assert ".." not in key and "passwd" not in key and "etc/" not in key
    assert key.endswith("/source.jpg")
    assert "/quarantine/7/" in key
    ins.assert_called_once()


def test_v2_session_create_extension_cannot_smuggle_path(client):
    resp, _ = _create(client, {
        "media_type": "IMAGE", "extension": "jpg/../../x", "mime_type": "image/jpeg", "size_bytes": 10,
    })
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "unsupported_extension"


# ── v2 upload-session complete ───────────────────────────────────────────────
def _session_row(status="PENDING", **kw):
    row = {
        "upload_id": "u1", "child_id": 7, "object_key": "uploads/r2/p/quarantine/7/u1/source.jpg",
        "media_type": "IMAGE", "kind": "POST", "expected_size_bytes": 1000, "mime_type": "image/jpeg",
        "extension": "jpg", "status": status, "is_expired": False,
    }
    row.update(kw)
    return row


def _complete(client, row, meta, existing=None):
    def handler(q, _p):
        if "FROM upload_sessions" in q:
            return row
        if "FROM posts WHERE upload_id" in q:
            return existing
        return None

    conn = _Conn(handler)
    with patch("mobile.api._mobile_token_revoked", return_value=False), \
         patch("mobile.api.fetch_one", return_value=_user()), \
         patch("mobile.api._child_gate", return_value=None), \
         patch("mobile.api.get_db_connection", return_value=conn), \
         patch("services.object_storage.enabled", return_value=True), \
         patch("services.object_storage.head_object", return_value=meta), \
         patch("services.job_queue.enqueue_media_job", side_effect=AssertionError("must not enqueue")) as enq:
        resp = client.post("/api/mobile/v2/uploads/u1/complete", headers=_headers(), json={})
    return resp, conn, enq


@pytest.mark.parametrize(
    "meta,error",
    [
        (None, "media_object_missing_in_quarantine"),
        ({"content_length": 0, "content_type": "image/jpeg"}, "media_object_missing_in_quarantine"),
        ({"content_length": 999, "content_type": "image/jpeg"}, "media_size_mismatch"),
        ({"content_length": 1000, "content_type": "text/html"}, "media_mime_mismatch"),
    ],
)
def test_v2_complete_enforces_stored_object_size_and_mime(client, meta, error):
    resp, conn, _ = _complete(client, _session_row(), meta)
    assert resp.status_code == 400
    assert resp.get_json()["error"] == error
    assert conn.rolled_back and not conn.committed


def test_v2_complete_expired_session_is_rejected(client):
    resp, conn, _ = _complete(client, _session_row(is_expired=True), {"content_length": 1000, "content_type": "image/jpeg"})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "upload_session_expired"


def test_v2_complete_replay_is_idempotent_and_does_not_spawn(client):
    existing = {"post_id": 55, "processing_status": "PROCESSING", "moderation_status": "PENDING", "processing_error": None}
    resp, conn, enq = _complete(client, _session_row(status="CONSUMED"), None, existing=existing)
    body = resp.get_json()
    assert resp.status_code == 200 and body["idempotent"] is True and body["post_id"] == 55
    enq.assert_not_called()


def test_v2_complete_rejects_other_childs_session(client):
    resp, conn, _ = _complete(client, _session_row(child_id=99), {"content_length": 1000, "content_type": "image/jpeg"})
    assert resp.status_code == 403


# ── chat upload-session complete ─────────────────────────────────────────────
def _chat_complete(client, row, meta=None):
    def handler(q, _p):
        return row if "FROM chat_upload_sessions" in q else None

    conn = _Conn(handler)
    with patch("mobile.api._mobile_token_revoked", return_value=False), \
         patch("mobile.api.fetch_one", return_value=_user()), \
         patch("mobile.api._child_gate", return_value=None), \
         patch("mobile.api.conversation", return_value=1), \
         patch("mobile.api.can_interact", return_value=True), \
         patch("mobile.api.feature_allowed", return_value=True), \
         patch("mobile.api.get_db_connection", return_value=conn), \
         patch("services.object_storage.enabled", return_value=True), \
         patch("services.object_storage.head_object", return_value=meta), \
         patch("services.chat_media.moderate_chat_media", side_effect=AssertionError("must not moderate")) as mod:
        resp = client.post("/api/mobile/v2/kids/chat/8/uploads/c1/complete", headers=_headers(), json={})
    return resp, conn, mod


def _chat_row(**kw):
    row = {
        "upload_id": "c1", "child_id": 7, "peer_id": 8, "object_key": "uploads/r2/p/chat_quarantine/7/c1/source.jpg",
        "media_type": "IMAGE", "expected_size_bytes": 500, "mime_type": "image/jpeg", "extension": "jpg",
        "status": "PENDING", "message_id": None, "expires_at": None,
    }
    row.update(kw)
    return row


@pytest.mark.parametrize("status", ["BLOCKED", "EXPIRED", "CANCELLED"])
def test_chat_complete_terminal_session_cannot_be_refinalized(client, status):
    resp, conn, mod = _chat_complete(client, _chat_row(status=status), {"content_length": 500, "content_type": "image/jpeg"})
    assert resp.status_code == 409
    assert resp.get_json()["error"] == "upload_session_closed"
    mod.assert_not_called()
    assert not any("INSERT INTO child_messages" in s for s, _ in conn.cur.statements)


@pytest.mark.parametrize(
    "meta,error",
    [
        ({"content_length": 501, "content_type": "image/jpeg"}, "media_size_mismatch"),
        ({"content_length": 500, "content_type": "application/pdf"}, "media_mime_mismatch"),
        ({"content_length": 0, "content_type": "image/jpeg"}, "media_object_missing_in_quarantine"),
    ],
)
def test_chat_complete_enforces_stored_object_size_and_mime(client, meta, error):
    resp, conn, mod = _chat_complete(client, _chat_row(), meta)
    assert resp.status_code == 400
    assert resp.get_json()["error"] == error
    mod.assert_not_called()


# ── legacy web avatar route ──────────────────────────────────────────────────
def _avatar_client(monkeypatch, tmp_path):
    from flask import Flask
    import child.routes as cr

    monkeypatch.chdir(tmp_path)

    def fake_fetch_one(sql, params=None):
        return {"role": "CHILD", "account_status": "ACTIVE"} if "account_status" in sql else None

    monkeypatch.setattr("decorators.fetch_one", fake_fetch_one)
    monkeypatch.setattr(cr, "fetch_one", fake_fetch_one)
    flask_app = Flask(__name__)
    flask_app.secret_key = "t"
    flask_app.register_blueprint(cr.child_bp)
    c = flask_app.test_client()
    with c.session_transaction() as s:
        s["user_id"], s["role"] = 9, "CHILD"
    return c, cr


def _image_bytes(fmt, exif=False):
    from PIL import Image

    buf = io.BytesIO()
    im = Image.new("RGB", (16, 16), (200, 10, 10))
    if exif and fmt == "JPEG":
        ex = Image.Exif()
        ex[0x010F] = "LeakyCameraMake"
        im.save(buf, format=fmt, exif=ex)
    else:
        im.save(buf, format=fmt)
    return buf.getvalue()


class _Allow:
    action, reason = "ALLOW", "ok"


def test_avatar_strips_exif_and_stores_clean_jpeg(monkeypatch, tmp_path):
    c, cr = _avatar_client(monkeypatch, tmp_path)
    monkeypatch.setattr(cr, "evaluate", lambda *a, **k: ({}, _Allow()))
    saved = {}
    monkeypatch.setattr(cr, "execute", lambda sql, params=None, **k: saved.update(params=params))
    resp = c.post("/child/upload-profile-picture/", data={"photo": (io.BytesIO(_image_bytes("JPEG", exif=True)), "me.jpg")},
                  content_type="multipart/form-data")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    from PIL import Image

    stored = saved["params"][0].replace("\\", "/")  # os.path.join on Windows
    assert stored.startswith("uploads/profile_pictures/profile_9_")
    with Image.open(tmp_path / stored) as im:
        assert im.format == "JPEG"
        assert 0x010F not in im.getexif()


@pytest.mark.parametrize("name,payload", [("a.jpg", b"<svg onload=alert(1)>"), ("a.jpg", b""), ("a.jpg", b"GIF89a" + b"\x00" * 20)])
def test_avatar_rejects_non_images(monkeypatch, tmp_path, name, payload):
    c, cr = _avatar_client(monkeypatch, tmp_path)
    monkeypatch.setattr(cr, "evaluate", lambda *a, **k: (_ for _ in ()).throw(AssertionError("moderation reached")))
    resp = c.post("/child/upload-profile-picture/", data={"photo": (io.BytesIO(payload), name)}, content_type="multipart/form-data")
    assert resp.status_code in {400}
    assert not list((tmp_path / "uploads" / "profile_pictures").glob("*"))


def test_avatar_rejects_gif_even_if_decodable(monkeypatch, tmp_path):
    c, cr = _avatar_client(monkeypatch, tmp_path)
    monkeypatch.setattr(cr, "evaluate", lambda *a, **k: (_ for _ in ()).throw(AssertionError("moderation reached")))
    resp = c.post("/child/upload-profile-picture/", data={"photo": (io.BytesIO(_image_bytes("GIF")), "a.jpg")},
                  content_type="multipart/form-data")
    assert resp.status_code == 400
    assert not list((tmp_path / "uploads" / "profile_pictures").glob("*"))


def test_avatar_caps_stored_bytes_not_just_content_length(monkeypatch, tmp_path):
    c, cr = _avatar_client(monkeypatch, tmp_path)
    monkeypatch.setattr(cr, "evaluate", lambda *a, **k: (_ for _ in ()).throw(AssertionError("moderation reached")))
    real_getsize = cr.os.path.getsize
    monkeypatch.setattr(cr.os.path, "getsize", lambda p: 9 * 1024 * 1024 if "profile_" in str(p) else real_getsize(p))
    resp = c.post("/child/upload-profile-picture/", data={"photo": (io.BytesIO(_image_bytes("JPEG")), "a.jpg")},
                  content_type="multipart/form-data")
    assert resp.status_code == 413
    assert not list((tmp_path / "uploads" / "profile_pictures").glob("*"))
