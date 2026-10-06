"""Secure, enumeration-resistant password reset with durable email outbox."""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import bcrypt
from datetime import datetime, timezone
from database.connection import get_db_connection, execute, fetch_one, fetch_all
from mailg.send_email import send_email

UNIFORM_RESET_MESSAGE = "If an account matches that username or email, a verification code has been sent."
RESET_RESEND_COOLDOWN_SECONDS = 60
OTP_MAX_ATTEMPTS = 5
MAX_RESET_ROWS_PER_IP_WINDOW = 5
RESET_IP_WINDOW_SECONDS = 900  # 15 minutes

import base64
from cryptography.fernet import Fernet


def _get_outbox_cipher() -> Fernet:
    secret = os.getenv("SECRET_KEY") or os.getenv("FLASK_SECRET_KEY") or os.getenv("AI_SHARED_SECRET") or "littlenet-dev-secret-change-in-prod-xyz123"
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_outbox_body(body: str) -> str:
    """Encrypt email body at rest so plaintext OTP secrets are never stored in the outbox table."""
    cipher = _get_outbox_cipher()
    encrypted = cipher.encrypt(body.encode("utf-8")).decode("ascii")
    return f"enc:v1:{encrypted}"


def decrypt_outbox_body(data: str) -> str:
    """Decrypt outbox body at dispatch time."""
    if data and data.startswith("enc:v1:"):
        cipher = _get_outbox_cipher()
        raw = data[len("enc:v1:"):]
        return cipher.decrypt(raw.encode("ascii")).decode("utf-8")
    return data


def _otp_hash(user_id: int, code: str) -> str:
    secret = os.getenv("SECRET_KEY", "littlenet-dev-secret-change-in-prod-xyz123")
    salt = f"littlenet-pwd-reset-otp-v1:{user_id}:"
    return hmac.new(secret.encode("utf-8"), (salt + code).encode("utf-8"), hashlib.sha256).hexdigest()


def _mask_email(email: str) -> str:
    if not email or "@" not in email:
        return "***@***.***"
    local, _, domain = email.partition("@")
    if len(local) <= 2:
        masked_local = local[0] + "*" if local else "*"
    else:
        masked_local = local[0] + "*" * (len(local) - 2) + local[-1]
    return f"{masked_local}@{domain}"


def _ensure_table():
    """Defensive fallback for local tests running without dbmate adoption."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS password_reset_otps (
                    user_id INTEGER PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
                    code_hash TEXT NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
                    sent_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS password_reset_transactions (
                    reset_token TEXT PRIMARY KEY,
                    user_id INTEGER REFERENCES users(user_id) ON DELETE CASCADE,
                    code_hash TEXT NOT NULL,
                    request_ip TEXT,
                    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
                    max_attempts INTEGER NOT NULL DEFAULT 5,
                    expires_at TIMESTAMPTZ NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    is_decoy BOOLEAN NOT NULL DEFAULT FALSE,
                    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'COMPLETED', 'EXPIRED', 'REVOKED'))
                );
                CREATE TABLE IF NOT EXISTS password_reset_email_outbox (
                    outbox_id BIGSERIAL PRIMARY KEY,
                    reset_token TEXT NOT NULL REFERENCES password_reset_transactions(reset_token) ON DELETE CASCADE,
                    recipient TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    body_html TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
                    max_attempts INTEGER NOT NULL DEFAULT 5,
                    last_error TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    completed_at TIMESTAMPTZ
                );
            """)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def check_ip_reset_rate_limit(request_ip: str | None, max_per_window: int = MAX_RESET_ROWS_PER_IP_WINDOW, window_minutes: int | None = None) -> bool:
    window_secs = (window_minutes * 60) if window_minutes is not None else RESET_IP_WINDOW_SECONDS
    """Rate limit per IP before creating database reset transaction rows."""
    if not request_ip:
        return True
    ip = str(request_ip).strip()
    row = fetch_one(
        """
        SELECT count(*) AS cnt
        FROM password_reset_transactions
        WHERE request_ip = %s
          AND created_at > NOW() - make_interval(secs => %s)
        """,
        (ip, window_secs),
    )
    count = int((row or {}).get("cnt") or 0)
    return count < max_per_window


def reap_expired_reset_transactions() -> int:
    """Reap expired or finished reset transactions and outbox items idempotently."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM password_reset_transactions
                WHERE expires_at < NOW()
                   OR status IN ('COMPLETED', 'REVOKED')
            """)
            deleted = cur.rowcount
        conn.commit()
        return deleted
    except Exception:
        conn.rollback()
        return 0
    finally:
        conn.close()


def request_password_reset(identifier: str, request_ip: str | None = None) -> tuple[bool, str, dict | None]:
    """Generate an opaque reset transaction with anti-enumeration protection.

    Public requests are externally uniform across existing, unknown, suspended,
    no-email, and cooldown accounts.
    """
    _ensure_table()
    try:
        reap_expired_reset_transactions()
    except Exception:
        pass

    ident = (identifier or "").strip()
    if not ident:
        return False, "Username or email is required.", None

    ip = str(request_ip or "").strip() or "127.0.0.1"
    if not check_ip_reset_rate_limit(ip):
        return False, "Too many password reset requests. Please try again later.", None

    user = fetch_one(
        """
        SELECT user_id, username, full_name, email, role, account_status
        FROM users
        WHERE LOWER(email) = LOWER(%s) OR LOWER(username) = LOWER(%s)
        LIMIT 1
        """,
        (ident, ident),
    )

    is_eligible = False
    target_email = None
    is_parent_proxy = False

    if user and user.get("account_status") != "SUSPENDED":
        if user.get("role") == "CHILD":
            parent_rel = fetch_one(
                """
                SELECT p.email AS parent_email
                FROM parent_child_map m
                JOIN users p ON p.user_id = m.parent_id
                WHERE m.child_id = %s
                  AND m.approved = TRUE
                  AND p.account_status = 'ACTIVE'
                LIMIT 1
                """,
                (user["user_id"],),
            )
            if parent_rel and parent_rel.get("parent_email"):
                target_email = parent_rel["parent_email"].strip()
                is_parent_proxy = True
                is_eligible = True
        elif user.get("email") and "@" in user.get("email"):
            target_email = user["email"].strip()
            is_eligible = True

    # Cooldown check for eligible users
    if is_eligible and user:
        recent_tx = fetch_one(
            """
            SELECT code_hash, attempts, expires_at > NOW() AS live,
                   sent_at > NOW() - make_interval(secs => %s) AS within_cooldown
            FROM password_reset_otps
            WHERE user_id = %s
            """,
            (RESET_RESEND_COOLDOWN_SECONDS, user["user_id"]),
        )
        if not recent_tx:
            recent_tx = fetch_one(
                """
                SELECT reset_token, expires_at, created_at,
                       created_at > NOW() - make_interval(secs => %s) AS within_cooldown
                FROM password_reset_transactions
                WHERE user_id = %s AND status = 'ACTIVE' AND expires_at > NOW()
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (RESET_RESEND_COOLDOWN_SECONDS, user["user_id"]),
            )
        if recent_tx and (recent_tx.get("within_cooldown") or (recent_tx.get("live") and recent_tx.get("attempts", 0) >= OTP_MAX_ATTEMPTS)):
            _tx = fetch_one("SELECT reset_token FROM password_reset_transactions WHERE user_id = %s AND status = 'ACTIVE' AND expires_at > NOW() ORDER BY created_at DESC LIMIT 1", (user["user_id"],))
            _tok = (_tx.get("reset_token") if _tx else None) or f"prt_{secrets.token_hex(24)}"
            if not _tx or not _tx.get("reset_token"):
                execute("INSERT INTO password_reset_transactions (reset_token, user_id, code_hash, request_ip, attempts, max_attempts, expires_at, created_at, is_decoy, status) VALUES (%s, %s, %s, %s, %s, %s, NOW() + INTERVAL '15 minutes', NOW(), FALSE, 'ACTIVE')", (_tok, user["user_id"], recent_tx.get("code_hash", ""), ip, recent_tx.get("attempts", 0), OTP_MAX_ATTEMPTS))
            return True, UNIFORM_RESET_MESSAGE, {
                "reset_token": _tok,
                "user_id": user["user_id"],
                "username": user["username"],
                "masked_email": _mask_email(target_email) if target_email else "",
                "is_parent_proxy": is_parent_proxy,
                "is_decoy": False,
                "email_sent": False,
            }

    reset_token = f"prt_{secrets.token_hex(24)}"
    code = f"{secrets.randbelow(1_000_000):06d}"

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            if is_eligible and user and target_email:
                code_hash = _otp_hash(user["user_id"], code)
                cur.execute(
                    "UPDATE password_reset_transactions SET status = 'REVOKED' WHERE user_id = %s AND status = 'ACTIVE'",
                    (user["user_id"],),
                )
                cur.execute(
                    """
                    INSERT INTO password_reset_transactions
                        (reset_token, user_id, code_hash, request_ip, attempts, max_attempts, expires_at, created_at, is_decoy, status)
                    VALUES (%s, %s, %s, %s, 0, %s, NOW() + INTERVAL '15 minutes', NOW(), FALSE, 'ACTIVE')
                    """,
                    (reset_token, user["user_id"], code_hash, ip, OTP_MAX_ATTEMPTS),
                )
                cur.execute(
                    """
                    INSERT INTO password_reset_otps (user_id, code_hash, expires_at, attempts, sent_at)
                    VALUES (%s, %s, NOW() + INTERVAL '15 minutes', 0, NOW())
                    ON CONFLICT (user_id) DO UPDATE SET
                        code_hash = EXCLUDED.code_hash,
                        expires_at = EXCLUDED.expires_at,
                        attempts = CASE WHEN password_reset_otps.expires_at > NOW() THEN password_reset_otps.attempts ELSE 0 END,
                        sent_at = NOW()
                    """,
                    (user["user_id"], code_hash),
                )

                subject = "LittleNet Password Reset Verification Code"
                if is_parent_proxy:
                    body = f"""
                    <div style="font-family: Arial, sans-serif; max-width: 540px; margin: 0 auto; padding: 24px; border: 1px solid #E2E8F0; border-radius: 12px;">
                      <h2 style="color: #0095F6; margin-top: 0;">LittleNet Safety Alert & Password Reset</h2>
                      <p>Hello,</p>
                      <p>A password reset was requested for your child's account: <b>@{user['username']}</b> ({user['full_name']}).</p>
                      <p>Please enter the following 6-digit verification code in the LittleNet app:</p>
                      <div style="font-size: 32px; font-weight: bold; letter-spacing: 6px; color: #1E293B; background: #F1F5F9; padding: 16px; text-align: center; border-radius: 8px; margin: 20px 0;">
                        {code}
                      </div>
                      <p style="color: #64748B; font-size: 13px;">This code will expire in 15 minutes. If you or your child did not request this, you can safely ignore this email.</p>
                    </div>
                    """
                else:
                    body = f"""
                    <div style="font-family: Arial, sans-serif; max-width: 540px; margin: 0 auto; padding: 24px; border: 1px solid #E2E8F0; border-radius: 12px;">
                      <h2 style="color: #0095F6; margin-top: 0;">LittleNet Password Reset</h2>
                      <p>Hello {user['full_name']},</p>
                      <p>You requested to reset your LittleNet password. Enter the verification code below in the app:</p>
                      <div style="font-size: 32px; font-weight: bold; letter-spacing: 6px; color: #1E293B; background: #F1F5F9; padding: 16px; text-align: center; border-radius: 8px; margin: 20px 0;">
                        {code}
                      </div>
                      <p style="color: #64748B; font-size: 13px;">This code will expire in 15 minutes. If you did not request a password reset, please secure your account immediately.</p>
                    </div>
                    """

                cur.execute(
                    """
                    INSERT INTO password_reset_email_outbox
                        (reset_token, recipient, subject, body_html, attempts, max_attempts, created_at)
                    VALUES (%s, %s, %s, %s, 0, %s, NOW())
                    """,
                    (reset_token, target_email, subject, encrypt_outbox_body(body), OTP_MAX_ATTEMPTS),
                )
                conn.commit()

                return True, UNIFORM_RESET_MESSAGE, {
                    "reset_token": reset_token,
                    "user_id": user["user_id"],
                    "username": user["username"],
                    "masked_email": _mask_email(target_email),
                    "is_parent_proxy": is_parent_proxy,
                    "is_decoy": False,
                    "email_sent": True,
                }
            else:
                decoy_hash = _otp_hash(0, code)
                cur.execute(
                    """
                    INSERT INTO password_reset_transactions
                        (reset_token, user_id, code_hash, request_ip, attempts, max_attempts, expires_at, created_at, is_decoy, status)
                    VALUES (%s, NULL, %s, %s, 0, %s, NOW() + INTERVAL '15 minutes', NOW(), TRUE, 'ACTIVE')
                    """,
                    (reset_token, decoy_hash, ip, OTP_MAX_ATTEMPTS),
                )
                conn.commit()

                return True, UNIFORM_RESET_MESSAGE, {
                    "reset_token": reset_token,
                    "is_decoy": True,
                }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def process_password_reset_email_outbox(batch_size: int = 10) -> int:
    """Durable outbox dispatcher: send only still-valid reset emails.

    Expired/revoked transactions are reaped before dispatch, and the SELECT
    independently joins the parent transaction with an ACTIVE + future-expiry
    guard. This prevents a delayed cron/deployment from emailing a stale OTP.
    """
    reap_expired_reset_transactions()
    conn = get_db_connection()
    sent_count = 0
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT o.outbox_id, o.recipient, o.subject, o.body_html
                FROM password_reset_email_outbox o
                JOIN password_reset_transactions t ON t.reset_token = o.reset_token
                WHERE o.completed_at IS NULL
                  AND o.attempts < o.max_attempts
                  AND t.status = 'ACTIVE'
                  AND t.expires_at > NOW()
                ORDER BY o.created_at
                LIMIT %s
                FOR UPDATE OF o SKIP LOCKED
                """,
                (batch_size,),
            )
            rows = cur.fetchall()
            for row in rows:
                oid = row["outbox_id"]
                to_addr = row["recipient"]
                subj = row["subject"]
                html = decrypt_outbox_body(row["body_html"])
                try:
                    sent = send_email(to_addr, subj, html)
                    if sent:
                        cur.execute("UPDATE password_reset_email_outbox SET completed_at = NOW(), attempts = attempts + 1 WHERE outbox_id = %s", (oid,))
                        sent_count += 1
                    else:
                        cur.execute("UPDATE password_reset_email_outbox SET attempts = attempts + 1, last_error = 'mail transport rejected' WHERE outbox_id = %s", (oid,))
                except Exception as exc:
                    cur.execute("UPDATE password_reset_email_outbox SET attempts = attempts + 1, last_error = %s WHERE outbox_id = %s", (str(exc)[:250], oid))
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        conn.close()
    return sent_count


def verify_and_reset_password_by_token(reset_token: str, code: str, new_password: str) -> tuple[bool, str]:
    """Verify OTP and update password using opaque reset transaction handle."""
    _ensure_table()
    token = (reset_token or "").strip()
    if not token:
        return False, "Reset token is required."

    code_str = (code or "").strip()
    if len(code_str) != 6 or not code_str.isdigit():
        return False, "Please enter the 6-digit verification code sent to your email."

    new_pwd = (new_password or "").strip()
    if len(new_pwd) < 8:
        return False, "New password must be at least 8 characters long."

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT reset_token, user_id, code_hash, attempts, max_attempts, expires_at, is_decoy, status
                FROM password_reset_transactions
                WHERE reset_token = %s
                FOR UPDATE
                """,
                (token,),
            )
            row = cur.fetchone()
            if not row or row["status"] != "ACTIVE":
                conn.rollback()
                return False, "No active password reset request found. Please request a new code."

            if row["attempts"] >= row["max_attempts"]:
                conn.rollback()
                return False, "Too many incorrect attempts. Please wait for the current code to expire, then request a new one."

            cur.execute("SELECT NOW() AS now")
            now = cur.fetchone()["now"]
            expires_at = row["expires_at"]
            if getattr(expires_at, "tzinfo", None) is None and getattr(now, "tzinfo", None) is not None:
                expires_at = expires_at.replace(tzinfo=now.tzinfo)
            if now > expires_at:
                cur.execute("UPDATE password_reset_transactions SET status = 'EXPIRED' WHERE reset_token = %s", (token,))
                conn.commit()
                return False, "The verification code has expired. Please request a new one."

            if row["is_decoy"]:
                expected_hash = _otp_hash(0, code_str)
                hmac.compare_digest(row["code_hash"], expected_hash)
                cur.execute("UPDATE password_reset_transactions SET attempts = attempts + 1 WHERE reset_token = %s", (token,))
                conn.commit()
                return False, "Incorrect verification code. Please check your email and try again."

            expected_hash = _otp_hash(row["user_id"], code_str)
            if not hmac.compare_digest(row["code_hash"], expected_hash):
                cur.execute("UPDATE password_reset_transactions SET attempts = attempts + 1 WHERE reset_token = %s", (token,))
                conn.commit()
                return False, "Incorrect verification code. Please check your email and try again."

            cur.execute("SELECT account_status FROM users WHERE user_id = %s", (row["user_id"],))
            acct = cur.fetchone()
            if not acct or acct.get("account_status") == "SUSPENDED":
                conn.rollback()
                return False, "This account is suspended. Please contact safety support."

            new_hash = bcrypt.hashpw(new_pwd.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            cur.execute(
                "UPDATE users SET password_hash = %s, session_version = COALESCE(session_version, 1) + 1 WHERE user_id = %s",
                (new_hash, row["user_id"]),
            )
            cur.execute("UPDATE password_reset_transactions SET status = 'COMPLETED' WHERE reset_token = %s", (token,))
            cur.execute("DELETE FROM password_reset_otps WHERE user_id = %s", (row["user_id"],))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return True, "Password reset successfully. You can now sign in with your new password."


def verify_and_reset_password(user_id: int, code: str, new_password: str) -> tuple[bool, str]:
    """Verify OTP and set new password (backwards-compatible user_id interface)."""
    _ensure_table()
    code_str = (code or "").strip()
    if len(code_str) != 6 or not code_str.isdigit():
        return False, "Please enter the 6-digit verification code sent to your email."

    new_pwd = (new_password or "").strip()
    if len(new_pwd) < 8:
        return False, "New password must be at least 8 characters long."

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT code_hash, expires_at, attempts
                FROM password_reset_otps
                WHERE user_id = %s
                FOR UPDATE
                """,
                (user_id,),
            )
            row = cur.fetchone()
            if not row:
                conn.rollback()
                return False, "No active password reset request found. Please request a new code."

            attempts = row.get("attempts", 0)
            max_att = row.get("max_attempts", OTP_MAX_ATTEMPTS)
            if attempts >= max_att:
                conn.rollback()
                return False, "Too many incorrect attempts. Please wait for the current code to expire, then request a new one."

            cur.execute("SELECT NOW() AS now")
            now = cur.fetchone()["now"]
            expires_at = row["expires_at"]
            if getattr(expires_at, "tzinfo", None) is None and getattr(now, "tzinfo", None) is not None:
                expires_at = expires_at.replace(tzinfo=now.tzinfo)
            if now > expires_at:
                conn.rollback()
                return False, "The verification code has expired. Please request a new one."

            if not hmac.compare_digest(row["code_hash"], _otp_hash(user_id, code_str)):
                if "reset_token" in row:
                    cur.execute("UPDATE password_reset_transactions SET attempts = attempts + 1 WHERE reset_token = %s", (row["reset_token"],))
                cur.execute("UPDATE password_reset_otps SET attempts = attempts + 1 WHERE user_id = %s", (user_id,))
                conn.commit()
                return False, "Incorrect verification code. Please check your email and try again."

            cur.execute("SELECT account_status FROM users WHERE user_id=%s", (user_id,))
            acct = cur.fetchone()
            if not acct or acct.get("account_status") == "SUSPENDED":
                conn.rollback()
                return False, "This account is suspended. Please contact safety support."

            new_hash = bcrypt.hashpw(new_pwd.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            cur.execute("UPDATE users SET password_hash = %s, session_version = COALESCE(session_version, 1) + 1 WHERE user_id = %s", (new_hash, user_id))
            if "reset_token" in row:
                cur.execute("UPDATE password_reset_transactions SET status = 'COMPLETED' WHERE reset_token = %s", (row["reset_token"],))
            cur.execute("DELETE FROM password_reset_otps WHERE user_id = %s", (user_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return True, "Password reset successfully. You can now sign in with your new password."


def parent_reset_child_password(parent_id: int, child_id: int, new_password: str) -> tuple[bool, str]:
    """Allows an authenticated parent to directly reset their linked child's password."""
    new_pwd = (new_password or "").strip()
    if len(new_pwd) < 8:
        return False, "Child's new password must be at least 8 characters long."

    from parent.service import owns
    if not owns(parent_id, child_id):
        return False, "Unauthorized: You can only reset passwords for your own approved children."

    new_hash = bcrypt.hashpw(new_pwd.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    execute("UPDATE users SET password_hash = %s, session_version = COALESCE(session_version, 1) + 1 WHERE user_id = %s AND role = 'CHILD'", (new_hash, child_id))
    return True, "Child's password updated successfully."
