"""Email OTP gate for standalone Parent Mode registration.

The parent account is created in PENDING_APPROVAL state. Email OTP proves
email ownership; the account is activated once the OTP is verified. There is
no separate selfie/liveness step. OTP values are never stored in plaintext
and expire after ten minutes.
"""
import hashlib
import hmac
import os
import secrets
from datetime import date, datetime

from auth.service import hash_password
from config import Config
from database.connection import get_db_connection, fetch_one
from mailg.send_email import send_parent_otp_email
from services.identity import validate_name, validate_username

OTP_TTL_MINUTES = 10
OTP_MAX_ATTEMPTS = 5


def _dev_otp_enabled() -> bool:
    """Return True only for an explicit non-production development override.

    Read the environment at call time so tests/dev tooling can explicitly toggle
    the override without relying on Config's import-time snapshot. Production is
    still a hard deny regardless of the environment value.
    """
    raw = os.getenv("ENABLE_DEV_OTP", "0").strip().lower()
    requested = raw in {"1", "true", "yes", "on"}
    return bool(requested and not Config._PRODUCTION)


def _ensure_table():
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS parent_email_otps (
                    user_id INTEGER PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
                    code_hash TEXT NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
                    sent_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    verified_at TIMESTAMP
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
    secret = str(Config.SECRET_KEY or '')
    payload = f"parent-email-otp:{user_id}:{code}:{secret}".encode('utf-8')
    return hashlib.sha256(payload).hexdigest()


def _new_code():
    return f"{secrets.randbelow(1_000_000):06d}"


def _adult_age(dob_str):
    try:
        born = datetime.strptime((dob_str or '')[:10], '%Y-%m-%d').date()
    except (TypeError, ValueError):
        raise ValueError('Please provide a valid date of birth.')
    today = date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def _validate_registration(form):
    username = (form.get('username') or '').strip()
    full_name = (form.get('full_name') or '').strip()
    email = (form.get('email') or '').strip().lower()
    password = form.get('password') or ''
    dob_str = (form.get('dob') or form.get('date_of_birth') or '').strip()

    if not validate_username(username):
        raise ValueError('Username must be 3-30 safe characters.')
    if not validate_name(full_name):
        raise ValueError('Please enter a valid parent or guardian name.')
    if '@' not in email or email.startswith('@') or email.endswith('@'):
        raise ValueError('Please enter a valid email address.')
    if len(password) < 8:
        raise ValueError('Password must be at least 8 characters long.')
    if _adult_age(dob_str) < 18:
        raise ValueError('Adult verification failed: Parent must be 18 years of age or older.')
    if form.get('guardian_declaration') != '1':
        raise ValueError('Please confirm the adult guardian declaration.')

    # Deliberately no arithmetic/captcha-style guardian question here. Adult
    # status is proved by DOB validation and email ownership; verified email
    # OTP is the complete parent verification (no selfie/liveness step).
    return username, full_name, email, password, dob_str


def _send_code(user_id, email, full_name, code):
    body = f"""
    <h2>Verify your LittleNet Parent Account</h2>
    <p>Hello <strong>{full_name}</strong>,</p>
    <p>Your one-time verification code is:</p>
    <p style="font-size:30px;font-weight:800;letter-spacing:8px;margin:20px 0;">{code}</p>
    <p>This code expires in {OTP_TTL_MINUTES} minutes. Do not share it with anyone.</p>
    <p>Once verified, your Parent account is activated immediately.</p>
    <p>If you did not create a LittleNet Parent account, you can ignore this email.</p>
    """
    sent = bool(send_parent_otp_email(
        email,
        'LittleNet: Your 6-digit parent verification code',
        body,
    ))
    if _dev_otp_enabled():
        print(f"\n{'='*70}\n[PARENT OTP] Development verification code for User {user_id}: {code}\n{'='*70}\n")
    return sent


def _is_unique_violation(exc):
    """True for a unique-constraint violation, without importing the DB driver.

    psycopg2 reports SQLSTATE 23505 on the exception; the class-name fallback
    keeps the race guard working if the driver ever changes. Deliberately
    narrow: other integrity errors (check/FK) must not be misread as a lost
    registration race.
    """
    if getattr(exc, "pgcode", None) == "23505":
        return True
    return type(exc).__name__ == "UniqueViolation"


def _raise_duplicate_account(existing, username, email):
    """Raise the same duplicate-account ValueError the pre-insert check raises."""
    if (existing.get('username') or '').casefold() == username.casefold():
        raise ValueError(f"The username '{username}' already exists. Please choose a different username.")
    raise ValueError(f"The email '{email}' is already used by a LittleNet account. Please log in instead.")


def begin_parent_registration(form):
    """Create a pending parent account and send its first OTP."""
    _ensure_table()
    username, full_name, email, password, dob_str = _validate_registration(form)
    code = _new_code()

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id, username, email, role, account_status FROM users WHERE LOWER(username)=LOWER(%s) OR LOWER(email)=LOWER(%s) LIMIT 1",
                (username, email),
            )
            existing = cur.fetchone()
            if existing:
                _raise_duplicate_account(existing, username, email)

            try:
                cur.execute(
                    """
                    INSERT INTO users(username,full_name,email,password_hash,role,dob,account_status)
                    VALUES(%s,%s,%s,%s,'PARENT',%s,'PENDING_APPROVAL')
                    RETURNING user_id
                    """,
                    (username, full_name, email, hash_password(password), dob_str),
                )
            except Exception as exc:
                if not _is_unique_violation(exc):
                    raise
                # Lost a concurrent-registration race: UNIQUE(username) /
                # UNIQUE(email) fired between our check and our insert. Roll
                # back the aborted transaction, re-read the winning row, and
                # report the duplicate exactly as the pre-check would have, so
                # the success/failure contract is unchanged.
                conn.rollback()
                cur.execute(
                    "SELECT user_id, username, email, role, account_status FROM users WHERE LOWER(username)=LOWER(%s) OR LOWER(email)=LOWER(%s) LIMIT 1",
                    (username, email),
                )
                existing = cur.fetchone()
                if existing:
                    _raise_duplicate_account(existing, username, email)
                raise
            user_id = cur.fetchone()['user_id']
            cur.execute(
                """
                INSERT INTO parent_email_otps(user_id,code_hash,expires_at,attempts,sent_at,verified_at)
                VALUES(%s,%s,NOW() + INTERVAL '10 minutes',0,NOW(),NULL)
                ON CONFLICT(user_id) DO UPDATE SET
                    code_hash=EXCLUDED.code_hash,
                    expires_at=EXCLUDED.expires_at,
                    attempts=0,
                    sent_at=NOW(),
                    verified_at=NULL
                """,
                (user_id, _otp_hash(user_id, code)),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    sent = _send_code(user_id, email, full_name, code)
    dev_code = code if _dev_otp_enabled() else None
    return {'user_id': user_id, 'email': email, 'full_name': full_name, 'email_sent': sent, 'dev_code': dev_code}


def verify_parent_email_otp(user_id, code):
    """Verify parent email ownership and return the user row.

    The caller activates the parent account after a successful OTP check.
    Verified email OTP is the complete parent verification (the live
    selfie/liveness step was removed)."""
    _ensure_table()
    code = (code or '').strip()
    if len(code) != 6 or not code.isdigit():
        return False, 'Enter the 6-digit code from your email.', None

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT o.code_hash,o.expires_at,o.attempts,o.verified_at,
                       u.user_id,u.email,u.full_name,u.role,u.account_status
                FROM parent_email_otps o
                JOIN users u ON u.user_id=o.user_id
                WHERE o.user_id=%s
                FOR UPDATE
                """,
                (user_id,),
            )
            row = cur.fetchone()
            if not row or row.get('role') != 'PARENT':
                conn.rollback()
                return False, 'Verification request not found. Please register again.', None
            if row.get('verified_at'):
                # Replay: this OTP was already consumed. Fail closed instead
                # of returning success again.
                conn.rollback()
                return False, 'This code has already been used. Request a new code if needed.', None
            if row['attempts'] >= OTP_MAX_ATTEMPTS:
                conn.rollback()
                return False, 'Too many incorrect attempts. Request a new code.', None
            cur.execute('SELECT NOW() AS now')
            now = cur.fetchone()['now']
            expires_at = row['expires_at']
            if getattr(expires_at, 'tzinfo', None) is None and getattr(now, 'tzinfo', None) is not None:
                expires_at = expires_at.replace(tzinfo=now.tzinfo)
            if now > expires_at:
                conn.rollback()
                return False, 'That code has expired. Request a new code.', None

            if not hmac.compare_digest(row['code_hash'], _otp_hash(user_id, code)):
                # The attempts < OTP_MAX_ATTEMPTS predicate keeps parallel
                # wrong guesses from pushing the counter past the cap: once
                # capped, further increments are no-ops.
                cur.execute('UPDATE parent_email_otps SET attempts=attempts+1 WHERE user_id=%s AND attempts < %s', (user_id, OTP_MAX_ATTEMPTS))
                conn.commit()
                return False, 'Incorrect verification code.', None

            cur.execute('UPDATE parent_email_otps SET verified_at=NOW() WHERE user_id=%s', (user_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    user = fetch_one('SELECT * FROM users WHERE user_id=%s', (user_id,))
    return True, None, user


def resend_parent_email_otp(user_id, with_code=False):
    """Rotate the code for a parent who has not yet completed email verification."""
    _ensure_table()
    user = fetch_one(
        """SELECT u.user_id,u.email,u.full_name,u.role,u.account_status,o.verified_at
           FROM users u LEFT JOIN parent_email_otps o ON o.user_id=u.user_id
           WHERE u.user_id=%s""",
        (user_id,),
    )
    if not user or user.get('role') != 'PARENT' or user.get('account_status') not in ('PENDING_APPROVAL',):
        # Only a genuinely pending parent may be sent (or re-sent) a code:
        # SUSPENDED / REJECTED / DEACTIVATED accounts must not be able to
        # restart verification on their own.
        err = 'No pending parent verification was found.'
        return (False, err, None) if with_code else (False, err)
    if user.get('verified_at'):
        err = 'Email is already verified.'
        return (False, err, None) if with_code else (False, err)

    code = _new_code()
    code_hash = _otp_hash(user_id, code)
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Serialize concurrent resends for this user with a
            # transaction-scoped advisory lock. A SELECT ... FOR UPDATE on
            # the OTP row alone is NOT enough: on a first-ever resend the row
            # does not exist yet, so the SELECT locks nothing and two
            # parallel first resends could both INSERT — the second silently
            # killing the first code ("dead on arrival"). The advisory lock
            # always exists, so the second resend blocks here, then sees the
            # first one's fresh sent_at and is refused by the cooldown below.
            # (Advisory, not a users-row lock, to avoid row lock-ordering
            # deadlocks with the verify path's FOR UPDATE join.)
            cur.execute("SELECT pg_advisory_xact_lock(%s, %s)", (842101, int(user_id)))
            cur.execute(
                "SELECT sent_at, verified_at FROM parent_email_otps WHERE user_id=%s FOR UPDATE",
                (user_id,),
            )
            existing = cur.fetchone()
            if existing and existing.get('verified_at'):
                conn.rollback()
                err = 'Email is already verified.'
                return (False, err, None) if with_code else (False, err)
            if existing:
                # DB-side resend cooldown, evaluated inside the row lock.
                cur.execute(
                    "SELECT 1 FROM parent_email_otps WHERE user_id=%s AND sent_at > NOW() - INTERVAL '60 seconds'",
                    (user_id,),
                )
                if cur.fetchone():
                    conn.rollback()
                    err = 'A code was just sent. Please wait a minute before requesting another.'
                    return (False, err, None) if with_code else (False, err)
            cur.execute(
                """
                INSERT INTO parent_email_otps(user_id,code_hash,expires_at,attempts,sent_at,verified_at)
                VALUES(%s,%s,NOW() + INTERVAL '10 minutes',0,NOW(),NULL)
                ON CONFLICT(user_id) DO UPDATE SET
                    code_hash=EXCLUDED.code_hash,
                    expires_at=EXCLUDED.expires_at,
                    sent_at=NOW(),
                    verified_at=NULL
                """,
                (user_id, code_hash),
            )
            # NOTE: attempts are deliberately NOT reset here. Resetting them
            # on every resend let an attacker mint unlimited guesses by
            # spamming resend; the guess budget now survives resends.
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    # Only the committed code is ever emailed: it is generated above, written
    # in the transaction just committed, and no second resend can have
    # overwritten it without passing the in-lock cooldown.
    sent = _send_code(user_id, user['email'], user['full_name'], code)
    dev_code = code if Config.ENABLE_DEV_OTP and not Config._PRODUCTION else None
    if not sent and not dev_code:
        if os.getenv('RESEND_API_KEY'):
            err = 'Email delivery failed. Check the verified Resend sender/domain configuration and try again.'
            return (False, err, None) if with_code else (False, err)
        err = 'Email delivery is unavailable. Check Resend/SMTP configuration and try again.'
        return (False, err, None) if with_code else (False, err)
    return (True, None, dev_code) if with_code else (True, None)
