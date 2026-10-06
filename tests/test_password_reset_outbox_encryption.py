"""Regression tests for password reset outbox encryption at rest."""
import pytest
from unittest.mock import patch
from database.connection import execute, fetch_one
from auth.password_reset import (
    request_password_reset,
    process_password_reset_email_outbox,
    encrypt_outbox_body,
    decrypt_outbox_body,
)


def test_encrypt_decrypt_outbox_roundtrip():
    secret_text = "Verification code is 654321. Do not share."
    enc = encrypt_outbox_body(secret_text)
    assert enc.startswith("enc:v1:")
    assert "654321" not in enc
    dec = decrypt_outbox_body(enc)
    assert dec == secret_text


def test_password_reset_outbox_stores_no_plaintext_otp():
    """Verify that password_reset_email_outbox row has encrypted ciphertext, not plaintext OTP."""
    # Insert test user
    uid = 899123
    email = "enc_test_parent@example.com"
    execute("INSERT INTO users (user_id, role, account_status, email, username, full_name, password_hash) "
            "VALUES (%s, 'PARENT', 'ACTIVE', %s, 'enc_test_user', 'Enc Parent', 'hash123') "
            "ON CONFLICT (user_id) DO UPDATE SET email=%s", (uid, email, email))
    
    execute("DELETE FROM password_reset_email_outbox WHERE recipient = %s", (email,))
    
    ok, msg, data = request_password_reset("enc_test_user", "127.0.0.1")
    assert ok is True
    
    # Query outbox row directly
    row = fetch_one("SELECT body_html FROM password_reset_email_outbox WHERE recipient = %s ORDER BY created_at DESC LIMIT 1", (email,))
    assert row is not None
    body_stored = row["body_html"]
    
    # Crucial security assertion: Ciphertext format, zero plaintext code leaks
    assert body_stored.startswith("enc:v1:")
    
    # Verify dispatcher decrypts and sends successfully
    with patch("auth.password_reset.send_email", return_value=True) as mock_send:
        sent = process_password_reset_email_outbox(batch_size=5)
        assert sent >= 1
        assert mock_send.called
        sent_html = mock_send.call_args[0][2]
        assert "LittleNet Password Reset" in sent_html
        assert "Enter the verification code below" in sent_html
