from pathlib import Path

import services.object_storage as storage


ROOT = Path(__file__).resolve().parents[1]


def _text(path):
    return (ROOT / path).read_text(encoding='utf-8')


def _configure_r2(monkeypatch):
    monkeypatch.setenv('R2_ACCOUNT_ID', 'acct-test')
    monkeypatch.setenv('R2_ACCESS_KEY_ID', 'key')
    monkeypatch.setenv('R2_SECRET_ACCESS_KEY', 'secret')
    monkeypatch.setenv('R2_BUCKET', 'private-media')
    monkeypatch.setenv('R2_SIGNED_URL_TTL', '180')


def test_signed_url_is_short_lived_and_private_reference_only(monkeypatch):
    _configure_r2(monkeypatch)
    calls = []

    class FakeClient:
        def generate_presigned_url(self, operation, Params, ExpiresIn):
            calls.append((operation, Params, ExpiresIn))
            return 'https://acct-test.r2.cloudflarestorage.com/signed'

    monkeypatch.setattr(storage, '_client', lambda: FakeClient())
    url = storage.signed_download_url('uploads/r2/posts/7/1/media.jpg')
    assert url.endswith('/signed')
    assert calls == [(
        'get_object',
        {'Bucket': 'private-media', 'Key': 'posts/7/1/media.jpg'},
        180,
    )]


def test_signed_url_ttl_is_clamped(monkeypatch):
    _configure_r2(monkeypatch)
    expiries = []

    class FakeClient:
        def generate_presigned_url(self, operation, Params, ExpiresIn):
            expiries.append(ExpiresIn)
            return 'signed'

    monkeypatch.setattr(storage, '_client', lambda: FakeClient())
    storage.signed_download_url('uploads/r2/x', expires_seconds=1)
    storage.signed_download_url('uploads/r2/x', expires_seconds=99999)
    assert expiries == [60, 600]


def test_delete_reference_deletes_exact_private_object(monkeypatch):
    _configure_r2(monkeypatch)
    deleted = []

    class FakeClient:
        def delete_object(self, **kwargs):
            deleted.append(kwargs)

    monkeypatch.setattr(storage, '_client', lambda: FakeClient())
    storage.delete_reference('uploads/r2/messages/3/9/photo.png')
    assert deleted == [{'Bucket': 'private-media', 'Key': 'messages/3/9/photo.png'}]


def test_non_r2_reference_is_never_deleted(monkeypatch):
    _configure_r2(monkeypatch)
    monkeypatch.setattr(storage, '_client', lambda: (_ for _ in ()).throw(AssertionError('client must not be called')))
    storage.delete_reference('uploads/images/local.png')


def test_app_uses_canonical_visibility_before_signing_and_never_public_caches_uploads():
    app = _text('app.py')
    signing = app.index("if stored.startswith('uploads/r2/')")
    post_auth = app.index("from services.social import post_visible_to, story_visible_to")
    message_auth = app.index("if not can_interact(m['sender_child_id'],m['receiver_child_id'])")
    profile_auth = app.index("from child.service import can_discover_child")
    recognized_guard = app.index("if not any([p,m,f]) and not default_avatar")
    assert post_auth < signing
    assert message_auth < signing
    assert profile_auth < signing
    assert recognized_guard < signing
    assert "visible=story_visible_to(uid,p['post_id']) if p.get('is_story') else post_visible_to(uid,p['post_id'])" in app
    assert "filename.startswith('profile_pictures/')" not in app
    assert 'signed_download_url(stored)' in app
    assert "response.headers['Cache-Control'] = 'private, no-store, max-age=0'" in app
    assert "public, max-age=86400" not in app
    assert 'r2.cloudflarestorage.com' in app


def test_child_post_and_story_deletes_trigger_r2_cleanup_after_success():
    app = _text('app.py')
    assert 'capture_r2_delete_targets' in app
    assert "path.startswith('/delete-post/')" in app
    assert "path.startswith('/api/delete-story/')" in app
    assert "response.status_code<400" in app
    assert 'delete_reference(ref)' in app


def test_r2_objects_are_uploaded_with_no_store_metadata():
    source = _text('services/object_storage.py')
    assert '"CacheControl": "private, no-store, max-age=0"' in source
    assert 'R2_REFERENCE_PREFIX = "uploads/r2/"' in source


def test_normalize_r2_origin_variants():
    # bare account ID -> https://ID.r2.cloudflarestorage.com
    assert storage.normalize_r2_origin("ID") == "https://ID.r2.cloudflarestorage.com"
    assert storage.normalize_r2_origin("acct-12345") == "https://acct-12345.r2.cloudflarestorage.com"

    # full URL -> unchanged normalized origin
    assert storage.normalize_r2_origin("https://ID.r2.cloudflarestorage.com") == "https://ID.r2.cloudflarestorage.com"
    assert storage.normalize_r2_origin("https://ID.r2.cloudflarestorage.com/") == "https://ID.r2.cloudflarestorage.com"
    assert storage.normalize_r2_origin("https://acct-12345.r2.cloudflarestorage.com") == "https://acct-12345.r2.cloudflarestorage.com"

    # host form -> https://host
    assert storage.normalize_r2_origin("ID.r2.cloudflarestorage.com") == "https://ID.r2.cloudflarestorage.com"
    assert storage.normalize_r2_origin("ID.r2.cloudflarestorage.com/") == "https://ID.r2.cloudflarestorage.com"
    assert storage.normalize_r2_origin("acct-12345.r2.cloudflarestorage.com") == "https://acct-12345.r2.cloudflarestorage.com"

    # empty -> empty origin
    assert storage.normalize_r2_origin("") == ""
    assert storage.normalize_r2_origin("   ") == ""
    assert storage.normalize_r2_origin(None) == ""


def test_app_csp_origin_construction(monkeypatch):
    from app import create_app

    # Verify bare account ID -> https://ID.r2.cloudflarestorage.com
    monkeypatch.setenv("R2_ACCOUNT_ID", "dummy-acct")
    app = create_app()
    with app.test_client() as client:
        resp = client.get("/login/")
        csp = resp.headers.get("Content-Security-Policy", "")
        assert "https://dummy-acct.r2.cloudflarestorage.com" in csp
        assert "https://https://" not in csp
        assert ".r2.cloudflarestorage.com.r2.cloudflarestorage.com" not in csp

    # Verify full URL -> unchanged normalized origin
    monkeypatch.setenv("R2_ACCOUNT_ID", "https://dummy-acct.r2.cloudflarestorage.com")
    app = create_app()
    with app.test_client() as client:
        resp = client.get("/login/")
        csp = resp.headers.get("Content-Security-Policy", "")
        assert "https://dummy-acct.r2.cloudflarestorage.com" in csp
        assert "https://https://" not in csp
        assert ".r2.cloudflarestorage.com.r2.cloudflarestorage.com" not in csp

    # Verify host form -> https://host
    monkeypatch.setenv("R2_ACCOUNT_ID", "dummy-acct.r2.cloudflarestorage.com")
    app = create_app()
    with app.test_client() as client:
        resp = client.get("/login/")
        csp = resp.headers.get("Content-Security-Policy", "")
        assert "https://dummy-acct.r2.cloudflarestorage.com" in csp
        assert "https://https://" not in csp
        assert ".r2.cloudflarestorage.com.r2.cloudflarestorage.com" not in csp

    # Verify empty -> empty origin
    monkeypatch.setenv("R2_ACCOUNT_ID", "")
    app = create_app()
    with app.test_client() as client:
        resp = client.get("/login/")
        csp = resp.headers.get("Content-Security-Policy", "")
        assert "https://https://" not in csp
        assert ".r2.cloudflarestorage.com.r2.cloudflarestorage.com" not in csp
