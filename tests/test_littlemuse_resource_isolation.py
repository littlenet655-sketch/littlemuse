from services import object_storage
from services.job_queue import ModalJobQueue


def test_littlemuse_r2_namespace_preserves_cloned_old_media(monkeypatch, tmp_path):
    monkeypatch.setenv("LITTLENET_R2_WRITE_PREFIX", "littlemuse")
    monkeypatch.setenv("R2_BUCKET", "private-test")
    calls = []

    class Client:
        def upload_file(self, *args, **kwargs):
            calls.append(("upload", args[2]))

        def delete_object(self, **kwargs):
            calls.append(("delete", kwargs["Key"]))

        def generate_presigned_url(self, operation, Params, ExpiresIn):
            calls.append(("sign", Params["Key"]))
            return "https://example.invalid/signed"

    monkeypatch.setattr(object_storage, "_client", lambda: Client())
    monkeypatch.setattr(object_storage, "_enabled", lambda: True)
    monkeypatch.setattr(object_storage, "_acknowledge_deleted_reference", lambda ref: None)
    path = tmp_path / "safe.jpg"
    path.write_bytes(b"image")

    ref = object_storage.upload_file(str(path), "posts/1/safe.jpg")
    assert ref == "uploads/r2/littlemuse/posts/1/safe.jpg"
    assert object_storage.new_reference("quarantine/1/id/source.jpg") == "uploads/r2/littlemuse/quarantine/1/id/source.jpg"
    object_storage.delete_reference("uploads/r2/posts/1/old.jpg")
    object_storage.delete_reference(ref)
    object_storage.signed_upload_url(object_storage.new_reference("quarantine/1/id/source.jpg"), "image/jpeg")
    assert calls == [
        ("upload", "littlemuse/posts/1/safe.jpg"),
        ("delete", "littlemuse/posts/1/safe.jpg"),
        ("sign", "littlemuse/quarantine/1/id/source.jpg"),
    ]


def test_modal_queue_uses_selected_app(monkeypatch):
    monkeypatch.setenv("LITTLENET_WEB_MODAL_APP", "littlemuse-web")
    assert ModalJobQueue().app_name == "littlemuse-web"
