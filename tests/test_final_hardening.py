import os
import tempfile
import urllib.error
from unittest.mock import MagicMock, patch
from pathlib import Path
from PIL import Image

import pytest


def test_resend_sandbox_is_distinguishable_from_verified():
    """get_mail_status rejects sandbox senders and accepts custom senders."""
    from mailg.send_email import get_mail_status

    # Case 1: Resend's shared sandbox sender is never submission-ready.
    with patch.dict(os.environ, {
        "RESEND_API_KEY": "re_test_123",
        "RESEND_FROM_EMAIL": "onboarding@resend.dev",
    }, clear=True):
        status = get_mail_status()
        assert status["ok"] is False
        assert status["mail_mode"] == "not_configured"
        assert status["is_production_ready"] is False

    # Case 2: A custom sender is accepted without the removed legacy flag.
    with patch.dict(os.environ, {
        "RESEND_API_KEY": "re_test_123",
        "RESEND_FROM_EMAIL": "no-reply@devpluse.in",
        "RESEND_DOMAIN_VERIFIED": "0",
    }, clear=True):
        status = get_mail_status()
        assert status["ok"] is True
        assert status["mail_mode"] == "resend_verified"
        assert status["is_production_ready"] is True

    # Case 3: The legacy flag is ignored in either direction.
    with patch.dict(os.environ, {
        "RESEND_API_KEY": "re_test_123",
        "RESEND_FROM_EMAIL": "safety@littlenet.safe",
        "RESEND_DOMAIN_VERIFIED": "1",
    }, clear=True):
        status = get_mail_status()
        assert status["ok"] is True
        assert status["mail_mode"] == "resend_verified"
        assert status["is_production_ready"] is True


def test_production_preflight_rejects_sandbox_only_mail():
    """Strict production preflight rejects sandbox mail mode."""
    from app import create_app
    app = create_app()

    # Test that readyz rejects sandbox in STRICT_PRODUCTION_PREFLIGHT mode
    with patch.dict(os.environ, {
        "RESEND_API_KEY": "re_test_123",
        "RESEND_FROM_EMAIL": "onboarding@resend.dev",
        "RESEND_DOMAIN_VERIFIED": "0",
        "STRICT_PRODUCTION_PREFLIGHT": "1",
    }, clear=True):
        with app.test_client() as client:
            with patch("app.fetch_one", return_value={"ok": 1}):
                with patch("safety.remote_client.enabled", return_value=False):
                    resp = client.get("/readyz")
                    assert resp.status_code == 503
                    data = resp.get_json()
                    assert data["status"] == "degraded"
                    assert data["mail_mode"] == "not_configured"

    # And passes when verified
    with patch.dict(os.environ, {
        "RESEND_API_KEY": "re_test_123",
        "RESEND_FROM_EMAIL": "safety@littlenet.safe",
        "RESEND_DOMAIN_VERIFIED": "1",
        "STRICT_PRODUCTION_PREFLIGHT": "1",
    }, clear=True):
        with app.test_client() as client:
            with patch("app.fetch_one", return_value={"ok": 1}):
                with patch("safety.remote_client.enabled", return_value=False):
                    resp = client.get("/readyz")
                    assert resp.status_code == 200
                    data = resp.get_json()
                    assert data["status"] == "ready"
                    assert data["mail_mode"] == "resend_verified"


def test_otp_send_failure_never_claims_code_sent():
    """When send_email returns False, begin_parent_registration reports email_sent=False."""
    from auth.parent_email_otp import begin_parent_registration

    with patch("auth.parent_email_otp._ensure_table"):
        with patch("auth.parent_email_otp._validate_registration", return_value=("testuser", "Test Parent", "parent@test.com", "Secret123!", "1980-01-01")):
            with patch("auth.parent_email_otp.get_db_connection") as mock_conn_fn:
                mock_conn = MagicMock()
                mock_cur = MagicMock()
                mock_conn.cursor.return_value.__enter__.return_value = mock_cur
                mock_conn_fn.return_value = mock_conn
                mock_cur.fetchone.side_effect = [None, {"user_id": 999}]

                with patch("auth.parent_email_otp._send_code", return_value=False):
                    res = begin_parent_registration({
                        "username": "testuser",
                        "full_name": "Test Parent",
                        "email": "parent@test.com",
                        "password": "SecretPassword123!",
                        "dob": "1980-01-01",
                        "guardian_declaration": "1",
                    })
                    assert res["email_sent"] is False
