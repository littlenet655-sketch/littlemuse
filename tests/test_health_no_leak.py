"""Health/readiness endpoints must not leak secrets, DSNs, paths or exception text."""
import json
import os
from unittest.mock import patch

import pytest

from app import create_app

SECRET = "re_SUPERSECRETKEY_123"
DSN_TEXT = "postgresql://user:pw@db.internal:5432/littlenet C:\\secret\\path"


@pytest.fixture
def client():
    app = create_app()
    with app.test_client() as c:
        yield c


def _assert_clean(resp):
    body = resp.get_data(as_text=True)
    for needle in (SECRET, "postgresql://", "db.internal", "secret\\path", "Traceback", "SECRET_KEY",
                   "AI_SHARED_SECRET", "DATABASE_URL", "R2_", "File \""):
        assert needle not in body, needle
    return json.loads(body)


def test_healthz_db_failure_hides_exception_text(client):
    with patch("app.fetch_one", side_effect=RuntimeError(DSN_TEXT)):
        resp = client.get("/healthz")
    assert resp.status_code == 503
    assert _assert_clean(resp) == {"status": "degraded", "database": False}


def test_readyz_failures_hide_exception_text_and_env(client):
    env = {"RESEND_API_KEY": SECRET, "RESEND_FROM_EMAIL": "no-reply@littlenet.in", "AI_SHARED_SECRET": "aisecret-xyz"}
    with patch.dict(os.environ, env), \
         patch("app.fetch_one", side_effect=RuntimeError(DSN_TEXT)), \
         patch("safety.remote_client.enabled", return_value=True), \
         patch("safety.remote_client.health", side_effect=RuntimeError(DSN_TEXT)):
        resp = client.get("/readyz")
    assert resp.status_code == 503
    data = _assert_clean(resp)
    assert "aisecret-xyz" not in json.dumps(data)
    assert set(data) == {"status", "database", "ai", "ai_mode", "mail", "mail_mode"}
    assert data["ai_mode"] == "remote_unavailable"


def test_readyz_ok_exposes_only_booleans_and_mode(client):
    env = {"RESEND_API_KEY": SECRET, "RESEND_FROM_EMAIL": "no-reply@littlenet.in", "RESEND_DOMAIN_VERIFIED": "1"}
    with patch.dict(os.environ, env), \
         patch("app.fetch_one", return_value={"ok": 1}), \
         patch("safety.remote_client.enabled", return_value=True), \
         patch("safety.remote_client.health", return_value={"ok": True, "mode": "passive_configured", "url": "https://secret.example"}):
        resp = client.get("/readyz")
    data = _assert_clean(resp)
    assert "secret.example" not in json.dumps(data)
    assert isinstance(data["database"], bool) and isinstance(data["ai"], bool)


def test_mobile_health_is_static_identity_only(client):
    resp = client.get("/api/mobile/v1/health")
    assert resp.status_code == 200
    assert _assert_clean(resp) == {
        "ok": True, "client": "react-native", "framework": "expo", "webview": False, "api_versions": [1, 2],
    }


def test_remote_health_default_is_passive_and_never_wakes_gpu(monkeypatch):
    from safety import remote_client

    monkeypatch.setenv("AI_SERVICE_URL", "https://ai.example")
    monkeypatch.delenv("AI_DEEP_HEALTH", raising=False)
    monkeypatch.delenv("AI_HEALTH_URL", raising=False)
    monkeypatch.setattr(remote_client.requests, "get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    out = remote_client.health()
    assert out["ok"] is True and out["gpu_woken"] is False
