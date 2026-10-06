"""head_object error semantics.

head_object must return None ONLY when the object is genuinely missing
(404 / NoSuchKey / NotFound). Auth failures (403), server errors (5xx),
endpoint failures, and timeouts must propagate: the upload-complete endpoint
treats missing as client fraud (410) but R2 errors as server errors (500),
and the media worker quarantines on None but records r2_preflight_failed on
raised errors. The old code caught every exception and returned None,
misreporting outages as "missing".
"""
from __future__ import annotations

import os

import pytest
from botocore.exceptions import ClientError, ConnectTimeoutError, EndpointConnectionError

from services import object_storage


def _client_error(code, status):
    return ClientError(
        {"Error": {"Code": code, "Message": "boom"},
         "ResponseMetadata": {"HTTPStatusCode": status}},
        "HeadObject",
    )


class FakeClient:
    def __init__(self, effect):
        self._effect = effect

    def head_object(self, Bucket, Key):
        if isinstance(self._effect, Exception):
            raise self._effect
        return self._effect


@pytest.fixture
def rig(monkeypatch):
    monkeypatch.setenv("R2_ACCOUNT_ID", "test")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("R2_BUCKET", "test-bucket")
    monkeypatch.delenv("LITTLENET_R2_WRITE_PREFIX", raising=False)
    os.environ.pop("R2_PUBLIC_BASE_URL", None)

    def use(effect):
        monkeypatch.setattr(object_storage, "_client", lambda: FakeClient(effect))

    return use


def test_missing_object_returns_none_404(rig):
    rig(_client_error("404", 404))
    assert object_storage.head_object("k") is None


def test_missing_object_returns_none_no_such_key(rig):
    rig(_client_error("NoSuchKey", 404))
    assert object_storage.head_object("k") is None


def test_forbidden_propagates(rig):
    rig(_client_error("AccessDenied", 403))
    with pytest.raises(ClientError):
        object_storage.head_object("k")


def test_server_error_propagates(rig):
    rig(_client_error("InternalError", 500))
    with pytest.raises(ClientError):
        object_storage.head_object("k")


def test_endpoint_failure_propagates(rig):
    rig(EndpointConnectionError(endpoint_url="https://r2.example"))
    with pytest.raises(EndpointConnectionError):
        object_storage.head_object("k")


def test_timeout_propagates(rig):
    rig(ConnectTimeoutError(endpoint_url="https://r2.example"))
    with pytest.raises(ConnectTimeoutError):
        object_storage.head_object("k")


def test_success_returns_metadata(rig):
    rig({"ContentLength": 123, "ContentType": "image/jpeg", "ETag": '"abc"'})
    meta = object_storage.head_object("k")
    assert meta == {"content_length": 123, "content_type": "image/jpeg", "etag": '"abc"'}
