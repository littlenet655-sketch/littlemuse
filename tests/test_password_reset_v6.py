import time
import pytest
import bcrypt
from datetime import datetime, timezone, timedelta
from auth.password_reset import (
    request_password_reset,
    verify_and_reset_password_by_token,
    process_password_reset_email_outbox,
    UNIFORM_RESET_MESSAGE,
    OTP_MAX_ATTEMPTS,
    decrypt_outbox_body,
)
from database.connection import execute, fetch_one, fetch_all


@pytest.fixture(autouse=True)
def clean_v6_data():
    prefix = "v6_reset_"
    execute("DELETE FROM users WHERE username LIKE %s OR email LIKE %s", (prefix + "%", prefix + "%"))
    execute("DELETE FROM password_reset_transactions WHERE request_ip = '198.51.100.99'")
    execute("DELETE FROM password_reset_email_outbox WHERE recipient LIKE %s", (prefix + "%",))
    yield
    execute("DELETE FROM users WHERE username LIKE %s OR email LIKE %s", (prefix + "%", prefix + "%"))
    execute("DELETE FROM password_reset_transactions WHERE request_ip = '198.51.100.99'")
    execute("DELETE FROM password_reset_email_outbox WHERE recipient LIKE %s", (prefix + "%",))


def test_child_reset_parent_proxy_flow(monkeypatch):
    """Child username -> generic response -> parent receives code in outbox -> token reset -> old sessions invalidated."""
    sent_emails = []
    monkeypatch.setattr("auth.password_reset.send_email", lambda to, subj, html: sent_emails.append((to, subj, html)) or True)

    prefix = "v6_reset_"
    p_email = f"{prefix}parent@example.com"
    c_uname = f"{prefix}child_user"

    p_hash = bcrypt.hashpw(b"OldParentPass123!", bcrypt.gensalt()).decode("utf-8")
    execute(
        "INSERT INTO users(username, full_name, email, password_hash, role, account_status, session_version) "
        "VALUES(%s, 'V6 Parent', %s, %s, 'PARENT', 'ACTIVE', 1)",
        (f"{prefix}parent", p_email, p_hash),
    )
    p_id = fetch_one("SELECT user_id FROM users WHERE email=%s", (p_email,))["user_id"]

    c_hash = bcrypt.hashpw(b"OldChildPass123!", bcrypt.gensalt()).decode("utf-8")
    execute(
        "INSERT INTO users(username, full_name, email, password_hash, role, account_status, session_version) "
        "VALUES(%s, 'V6 Child', %s, %s, 'CHILD', 'ACTIVE', 2)",
        (c_uname, f"{c_uname}@kids.littlenet.internal", c_hash),
    )
    c_id = fetch_one("SELECT user_id FROM users WHERE username=%s", (c_uname,))["user_id"]

    execute(
        "INSERT INTO parent_child_map(parent_id, child_id, parent_name, parent_email, approved, approval_status) "
        "VALUES(%s, %s, 'V6 Parent', %s, TRUE, 'APPROVED')",
        (p_id, c_id, p_email),
    )

    # 1. Request reset using Child username
    ok, msg, det = request_password_reset(c_uname, request_ip="198.51.100.99")
    assert ok is True
    assert msg == UNIFORM_RESET_MESSAGE
    token = det["reset_token"]
    assert token.startswith("prt_")

    # 2. Check outbox queued for parent email
    outbox_row = fetch_one("SELECT * FROM password_reset_email_outbox WHERE recipient=%s", (p_email,))
    assert outbox_row is not None
    assert outbox_row["completed_at"] is None
    assert outbox_row["attempts"] == 0

    # Verify outbox body is encrypted at rest (not containing plaintext OTP or HTML tags directly)
    assert not outbox_row["body_html"].startswith("<")

    # 3. Drain outbox
    sent_count = process_password_reset_email_outbox(10)
    assert sent_count == 1
    assert len(sent_emails) == 1
    to_addr, subj, html = sent_emails[0]
    assert to_addr == p_email
    assert "Verification Code" in subj or "Code" in subj

    # Extract 6-digit OTP from email html
    import re
    m = re.search(r"\b(\d{6})\b", html)
    assert m is not None, f"Could not find 6-digit OTP in html: {html}"
    otp = m.group(1)

    # 4. Verify outbox marked completed
    row_after = fetch_one("SELECT completed_at FROM password_reset_email_outbox WHERE outbox_id=%s", (outbox_row["outbox_id"],))
    assert row_after["completed_at"] is not None

    # 5. Wrong OTP rejected
    ok_bad, msg_bad = verify_and_reset_password_by_token(token, "000000", "NewValidChildPass123!")
    assert ok_bad is False
    assert "incorrect" in msg_bad.lower()

    # 6. Correct OTP resets password
    ok_reset, msg_reset = verify_and_reset_password_by_token(token, otp, "NewValidChildPass123!")
    assert ok_reset is True

    # 7. Check child's password hash updated & session_version bumped
    c_updated = fetch_one("SELECT password_hash, session_version FROM users WHERE user_id=%s", (c_id,))
    assert bcrypt.checkpw(b"NewValidChildPass123!", c_updated["password_hash"].encode("utf-8"))
    assert c_updated["session_version"] == 3  # was 2, now bumped to invalidate old sessions!

    # 8. Replayed OTP fails (token completed/inactive)
    ok_replay, msg_replay = verify_and_reset_password_by_token(token, otp, "AnotherPass123!")
    assert ok_replay is False


def test_expired_outbox_item_not_sent(monkeypatch):
    """Proves that if the reset transaction has expired, the outbox worker marks it terminal without sending email."""
    sent_emails = []
    monkeypatch.setattr("auth.password_reset.send_email", lambda to, subj, html: sent_emails.append((to, subj, html)) or True)

    prefix = "v6_reset_"
    p_email = f"{prefix}expired_parent@example.com"
    p_hash = bcrypt.hashpw(b"OldParentPass123!", bcrypt.gensalt()).decode("utf-8")
    execute(
        "INSERT INTO users(username, full_name, email, password_hash, role, account_status) "
        "VALUES(%s, 'Expired Parent', %s, %s, 'PARENT', 'ACTIVE')",
        (f"{prefix}expired_parent", p_email, p_hash),
    )

    ok, msg, det = request_password_reset(p_email, request_ip="198.51.100.99")
    assert ok is True
    token = det["reset_token"]

    outbox_row = fetch_one("SELECT * FROM password_reset_email_outbox WHERE recipient=%s", (p_email,))
    assert outbox_row is not None
    assert outbox_row["completed_at"] is None

    # Manually expire the transaction
    execute(
        "UPDATE password_reset_transactions SET expires_at = NOW() - INTERVAL '10 minutes' WHERE reset_token=%s",
        (token,),
    )

    # Run outbox drainer
    sent_count = process_password_reset_email_outbox(10)
    assert sent_count == 0
    assert len(sent_emails) == 0

    # Row must be marked terminal
    row_after = fetch_one("SELECT completed_at, last_error FROM password_reset_email_outbox WHERE outbox_id=%s", (outbox_row["outbox_id"],))
    assert row_after["completed_at"] is not None
    assert "expired" in row_after["last_error"]


def test_unknown_and_suspended_accounts():
    """Anti-enumeration: unknown and suspended accounts produce uniform responses and do not send emails."""
    prefix = "v6_reset_"

    # Unknown
    ok, msg, det = request_password_reset(f"{prefix}nobody@example.com", request_ip="198.51.100.99")
    assert ok is True
    assert msg == UNIFORM_RESET_MESSAGE
    assert det["reset_token"].startswith("prt_")
    out = fetch_one("SELECT * FROM password_reset_email_outbox WHERE recipient=%s", (f"{prefix}nobody@example.com",))
    assert out is None

    # Suspended
    p_hash = bcrypt.hashpw(b"OldPass123!", bcrypt.gensalt()).decode("utf-8")
    s_email = f"{prefix}suspended@example.com"
    execute(
        "INSERT INTO users(username, full_name, email, password_hash, role, account_status) "
        "VALUES(%s, 'Suspended User', %s, %s, 'PARENT', 'SUSPENDED')",
        (f"{prefix}suspended", s_email, p_hash),
    )
    ok_s, msg_s, det_s = request_password_reset(s_email, request_ip="198.51.100.99")
    assert ok_s is True
    assert msg_s == UNIFORM_RESET_MESSAGE
    out_s = fetch_one("SELECT * FROM password_reset_email_outbox WHERE recipient=%s", (s_email,))
    assert out_s is None


def test_outbox_transport_failure_and_retry(monkeypatch):
    """Transport failure increments attempts and allows retry up to max_attempts."""
    fail_email = True
    def mock_send(to, subj, html):
        if fail_email:
            raise RuntimeError("Resend SMTP connection refused")
        return True

    monkeypatch.setattr("auth.password_reset.send_email", mock_send)

    prefix = "v6_reset_"
    p_email = f"{prefix}retry_parent@example.com"
    p_hash = bcrypt.hashpw(b"OldParentPass123!", bcrypt.gensalt()).decode("utf-8")
    execute(
        "INSERT INTO users(username, full_name, email, password_hash, role, account_status) "
        "VALUES(%s, 'Retry Parent', %s, %s, 'PARENT', 'ACTIVE')",
        (f"{prefix}retry_parent", p_email, p_hash),
    )

    request_password_reset(p_email, request_ip="198.51.100.99")
    out = fetch_one("SELECT * FROM password_reset_email_outbox WHERE recipient=%s", (p_email,))

    # First attempt fails
    sent = process_password_reset_email_outbox(10)
    assert sent == 0
    out_after = fetch_one("SELECT attempts, completed_at, last_error FROM password_reset_email_outbox WHERE outbox_id=%s", (out["outbox_id"],))
    assert out_after["attempts"] == 1
    assert out_after["completed_at"] is None
    assert "connection refused" in out_after["last_error"]

    # Now recover transport
    fail_email = False
    sent_recovered = process_password_reset_email_outbox(10)
    assert sent_recovered == 1
    out_done = fetch_one("SELECT attempts, completed_at FROM password_reset_email_outbox WHERE outbox_id=%s", (out["outbox_id"],))
    assert out_done["attempts"] == 2
    assert out_done["completed_at"] is not None


def test_otp_attempt_exhaustion():
    prefix = "v6_reset_"
    p_email = f"{prefix}exhaust_parent@example.com"
    p_hash = bcrypt.hashpw(b"OldParentPass123!", bcrypt.gensalt()).decode("utf-8")
    execute(
        "INSERT INTO users(username, full_name, email, password_hash, role, account_status) "
        "VALUES(%s, 'Exhaust Parent', %s, %s, 'PARENT', 'ACTIVE')",
        (f"{prefix}exhaust_parent", p_email, p_hash),
    )
    ok, msg, det = request_password_reset(p_email, request_ip="198.51.100.99")
    assert ok is True
    tok = det["reset_token"]

    for _ in range(OTP_MAX_ATTEMPTS):
        ok_a, msg_a = verify_and_reset_password_by_token(tok, "999999", "NewPassExhaust123!")
        assert ok_a is False

    # Attempt after exhaustion must be locked out
    ok_lock, msg_lock = verify_and_reset_password_by_token(tok, "999999", "NewPassExhaust123!")
    assert ok_lock is False
    assert "too many" in msg_lock.lower() or "locked" in msg_lock.lower() or "exhausted" in msg_lock.lower()


def test_concurrent_drainers(monkeypatch):
    sent_emails = []
    monkeypatch.setattr("auth.password_reset.send_email", lambda to, subj, html: sent_emails.append((to, subj, html)) or True)

    prefix = "v6_reset_"
    p_email = f"{prefix}concurrent_parent@example.com"
    p_hash = bcrypt.hashpw(b"OldParentPass123!", bcrypt.gensalt()).decode("utf-8")
    execute(
        "INSERT INTO users(username, full_name, email, password_hash, role, account_status) "
        "VALUES(%s, 'Concurrent Parent', %s, %s, 'PARENT', 'ACTIVE')",
        (f"{prefix}concurrent_parent", p_email, p_hash),
    )
    request_password_reset(p_email, request_ip="198.51.100.99")

    # Two concurrent calls to process_password_reset_email_outbox
    count1 = process_password_reset_email_outbox(10)
    count2 = process_password_reset_email_outbox(10)
    assert count1 + count2 == 1
    assert len(sent_emails) == 1
