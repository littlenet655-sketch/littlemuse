"""Password Reset Service for LittleNet.

Supports:
1. Requesting password reset OTP via registered email for Parents or Kids.
2. For Kids without personal emails, routing OTP to verified linked parent.
3. Verification of 6-digit OTP code and bcrypt updating of password.
4. Direct parent reset of child's password from Parent Controls.
"""
import hashlib
import hmac
import re
import secrets
from datetime import datetime

import bcrypt

from config import Config
from database.connection import get_db_connection, fetch_one, execute
from mailg.send_email import send_email

OTP_TTL_MINUTES = 15
OTP_MAX_ATTEMPTS = 5
# Minimum seconds between issuing a new reset code for the same user.
# Stops rapid re-requests from churning the victim's active code and from
# email-bombing the recipient. The response stays uniform either way.
RESET_RESEND_COOLDOWN_SECONDS = 60

# Uniform anti-enumeration response for password-reset requests. Returned
# whether or not an account matched (and whether or not a code was sent),
# so the response never reveals account existence or suspension status.
UNIFORM_RESET_MESSAGE = "If an account exists with that username or email, a reset code was sent."


def _ensure_table():
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS password_reset_otps (
                    user_id INTEGER PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
                    code_hash TEXT NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
                    sent_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _otp_hash(user_id, code):
    secret = str(Config.SECRET_KEY or "littlenet-default-secret")
    payload = f"pwd-reset:{user_id}:{code}:{secret}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _mask_email(email: str) -> str:
    if not email or "@" not in email:
        return "your registered email"
    user_part, domain = email.split("@", 1)
    if len(user_part) <= 2:
        masked_user = user_part[0] + "*"
    else:
        masked_user = user_part[0] + ("*" * (len(user_part) - 2)) + user_part[-1]
    return f"{masked_user}@{domain}"


def request_password_reset(identifier: str):
    """Request a password reset OTP for a username or email.

    Anti-enumeration: unknown identifiers, suspended accounts, and accounts
    with no usable email all receive the same success-shaped uniform
    response. The caller must never branch on existence/suspension pre-auth,
    so no code is sent in those cases but the response is indistinguishable.
    """
    _ensure_table()
    ident = (identifier or "").strip()
    if not ident:
        return False, "Please enter your username or email.", None

    user = fetch_one(
        """
        SELECT user_id, username, full_name, email, role, account_status
        FROM users
        WHERE LOWER(email) = LOWER(%s) OR LOWER(username) = LOWER(%s)
        LIMIT 1
        """,
        (ident, ident),
    )
    if not user:
        # Unknown identifier: uniform response, no code sent.
        return True, UNIFORM_RESET_MESSAGE, None

    if user.get("account_status") == "SUSPENDED":
        # Suspended: uniform response, no code sent. (Suspension is enforced
        # again at code-verification time; nothing here reveals it.)
        return True, UNIFORM_RESET_MESSAGE, None

    # Determine recipient email
    target_email = (user.get("email") or "").strip()
    is_parent_proxy = False

    # For any child account or accounts with placeholder emails, route OTP to the verified parent
    if user.get("role") == "CHILD" or not target_email or "@" not in target_email or target_email.endswith(".internal") or target_email.endswith("@littlenet.local"):
        parent_map = fetch_one(
            """
            SELECT pcm.parent_email, u.email AS parent_user_email, u.full_name AS parent_name
            FROM parent_child_map pcm
            JOIN users u ON u.user_id = COALESCE(pcm.verified_parent_id, pcm.parent_id)
            WHERE pcm.child_id = %s
              AND pcm.approved = TRUE
              AND pcm.approval_status = 'APPROVED'
              AND u.role = 'PARENT'
              AND u.account_status = 'ACTIVE'
            ORDER BY pcm.map_id DESC LIMIT 1
            """,
            (user["user_id"],),
        )
        if parent_map:
            target_email = (parent_map.get("parent_user_email") or parent_map.get("parent_email") or "").strip()
            is_parent_proxy = True


    if not target_email or "@" not in target_email:
        # No usable email: uniform response, no code sent. The distinct
        # "no parent email" / "no valid email" messages used to confirm the
        # account exists.
        return True, UNIFORM_RESET_MESSAGE, None

    # Resend cooldown: if a live (unexpired) code was issued within the
    # cooldown window, do not churn it and do not send another email.
    # Uniform response, so this reveals nothing about the account.
    #
    # Attempt budget is carried forward on re-issue: a fresh code never
    # resets the 5-attempt limit while the previous code is still live.
    # Otherwise requests after the cooldown would grant unlimited fresh
    # guessing windows against the unexpired OTP.
    existing = fetch_one(
        """
        SELECT attempts,
               expires_at > NOW() AS live,
               sent_at > NOW() - make_interval(secs => %s) AS within_cooldown
        FROM password_reset_otps
        WHERE user_id = %s
        LIMIT 1
        """,
        (RESET_RESEND_COOLDOWN_SECONDS, user["user_id"]),
    )
    attempts_carry = 0
    if existing:
        if existing.get("within_cooldown"):
            # Live code issued within cooldown: keep it, no new email.
            return True, UNIFORM_RESET_MESSAGE, None
        if existing.get("live"):
            attempts_carry = int(existing.get("attempts") or 0)
            if attempts_carry >= OTP_MAX_ATTEMPTS:
                # Budget burned: no new code until the current one expires.
                return True, UNIFORM_RESET_MESSAGE, None
        # Expired code (or no live code): fresh attempt budget.

    code = f"{secrets.randbelow(1_000_000):06d}"
    code_hash = _otp_hash(user["user_id"], code)

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO password_reset_otps (user_id, code_hash, expires_at, attempts, sent_at)
                VALUES (%s, %s, NOW() + INTERVAL '15 minutes', %s, NOW())
                ON CONFLICT (user_id) DO UPDATE SET
                    code_hash = EXCLUDED.code_hash,
                    expires_at = EXCLUDED.expires_at,
                    attempts = EXCLUDED.attempts,
                    sent_at = NOW()
                """,
                (user["user_id"], code_hash, attempts_carry),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    # Compose email
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
          <p style="color: #64748B; font-size: 13px;">This code will expire in 15 minutes. If you or your child did not request this, you can safely ignore this email or review child activity in Parent Mode.</p>
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

    sent = send_email(target_email, subject, body)

    return True, UNIFORM_RESET_MESSAGE, {
        "user_id": user["user_id"],
        "username": user["username"],
        "masked_email": _mask_email(target_email),
        "is_parent_proxy": is_parent_proxy,
        "email_sent": bool(sent),
    }


def verify_and_reset_password(user_id: int, code: str, new_password: str):
    """Verify OTP and set new password."""
    _ensure_table()
    code = (code or "").strip()
    if len(code) != 6 or not code.isdigit():
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

            if row["attempts"] >= OTP_MAX_ATTEMPTS:
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

            if not hmac.compare_digest(row["code_hash"], _otp_hash(user_id, code)):
                cur.execute("UPDATE password_reset_otps SET attempts = attempts + 1 WHERE user_id = %s", (user_id,))
                conn.commit()
                return False, "Incorrect verification code. Please check your email and try again."

            # Code valid: refuse suspended accounts even if the code was issued
            # before the suspension (post-auth check — reveals nothing
            # pre-auth since a valid code is required to reach here).
            cur.execute("SELECT account_status FROM users WHERE user_id=%s", (user_id,))
            acct = cur.fetchone()
            if not acct or acct.get("account_status") == "SUSPENDED":
                conn.rollback()
                return False, "This account is suspended. Please contact safety support."
            # Update password hash and increment session_version to invalidate prior bearer tokens
            new_hash = bcrypt.hashpw(new_pwd.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            cur.execute("UPDATE users SET password_hash = %s, session_version = COALESCE(session_version, 1) + 1 WHERE user_id = %s", (new_hash, user_id))
            cur.execute("DELETE FROM password_reset_otps WHERE user_id = %s", (user_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return True, "Password reset successfully. You can now sign in with your new password."


def parent_reset_child_password(parent_id: int, child_id: int, new_password: str):
    """Allows an authenticated parent to directly reset their linked child's password."""
    new_pwd = (new_password or "").strip()
    if len(new_pwd) < 8:
        return False, "Child's new password must be at least 8 characters long."

    # Reuse the canonical ownership gate so password reset cannot accept a
    # pending/stale guardian mapping that Parent Mode itself would reject.
    from parent.service import owns
    if not owns(parent_id, child_id):
        return False, "Unauthorized: You can only reset passwords for your own approved children."

    new_hash = bcrypt.hashpw(new_pwd.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    execute("UPDATE users SET password_hash = %s, session_version = COALESCE(session_version, 1) + 1 WHERE user_id = %s AND role = 'CHILD'", (new_hash, child_id))
    return True, "Child's password updated successfully."
