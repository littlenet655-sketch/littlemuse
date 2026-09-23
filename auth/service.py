import os, uuid, secrets, re
import logging
from datetime import datetime, timezone, timedelta
import bcrypt
from jinja2 import Template
from database.connection import fetch_one, fetch_all, execute, get_db_connection
from mailg.send_email import send_email
from config import Config
from services.identity import validate_username, validate_name
from auth import login_throttle

logger = logging.getLogger(__name__)

def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(password, hashed):
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except Exception:
        return False

def get_parent_verification_data(token):
    """
    Fetches registration and child details associated with a parent verification token.
    """
    conn = get_db_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT 
                pcm.map_id,
                pcm.child_id,
                pcm.parent_id,
                pcm.parent_name,
                pcm.parent_email,
                pcm.verification_token,
                pcm.approval_token,
                pcm.approval_status,
                pcm.approved,
                u.username AS child_username,
                u.full_name AS child_name,
                u.age AS child_age,
                u.email AS child_email,
                u.created_at AS child_created_at
            FROM parent_child_map pcm
            JOIN users u ON pcm.child_id = u.user_id
            WHERE pcm.verification_token = %s OR pcm.approval_token = %s
        """, (token, token))
        data = cur.fetchone()
        return data
    finally:
        conn.close()

def _validate_token_guardian_form(map_data, form_data):
    """Shared validation for the token-based guardian verification form.

    Parent identity is proven by email ownership (the caller verifies an
    email OTP before activation); the form additionally requires an 18+
    date-of-birth declaration and explicit guardian consent. There is no
    selfie / liveness / face step.
    """
    parent_name = (form_data.get("parent_name") or map_data.get("parent_name") or "").strip()
    dob = (form_data.get("dob") or "").strip()
    consent = bool(form_data.get("consent"))

    if not parent_name:
        return None, "Please provide the parent or guardian full name."
    if not consent:
        return None, "You must confirm that you are the child's legal adult parent or guardian."
    if dob:
        try:
            birth_date = datetime.strptime(dob, "%Y-%m-%d").date()
            today = datetime.now(timezone.utc).date()
            declared_age = today.year - birth_date.year - (
                (today.month, today.day) < (birth_date.month, birth_date.day)
            )
            if declared_age < 18:
                return None, "Adult verification failed: Parent must be 18 years of age or older."
        except ValueError:
            return None, "Please provide a valid date of birth for the parent or guardian."
    return {"parent_name": parent_name, "dob": dob}, None


def _mask_parent_email(email):
    email = (email or "").strip()
    if "@" not in email:
        return email
    local, domain = email.split("@", 1)
    shown = local[:2] if len(local) > 2 else local[:1]
    return f"{shown}{'*' * max(2, len(local) - len(shown))}@{domain}"


def ensure_token_parent_pending(token, form_data):
    """Validate the guardian form for the child-approval token flow and ensure
    a parent account exists so an email OTP can be issued.

    Returns {"success": True, "parent_id": ..., "already_active": bool} or
    {"success": False, "error": ...}. New parents are created PENDING_APPROVAL
    (never ACTIVE here); already-ACTIVE parents skip the OTP step.
    """
    map_data = get_parent_verification_data(token)
    if not map_data:
        return {"success": False, "error": "Invalid or expired verification invitation link."}
    parent_email = map_data["parent_email"].strip().lower()

    valid, error = _validate_token_guardian_form(map_data, form_data)
    if error:
        return {"success": False, "error": error}
    # The 18+ date-of-birth declaration is required server-side on the initial
    # guardian form (the template also marks it required). It is deliberately
    # NOT required in process_parent_verification: the OTP-completion step
    # re-enters that function without form data, after the declaration was
    # already collected here.
    if not valid.get("dob"):
        return {"success": False, "error": "Please provide the parent or guardian date of birth (18+ declaration)."}

    conn = get_db_connection()
    if not conn:
        return {"success": False, "error": "Database error while processing verification."}
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT user_id, account_status FROM users WHERE LOWER(email)=%s AND role='PARENT'",
            (parent_email,),
        )
        row = cur.fetchone()
        if row and row.get("account_status") == "ACTIVE":
            return {"success": True, "already_active": True, "parent_id": row["user_id"]}
        if row:
            if row.get("account_status") != "PENDING_APPROVAL":
                # Suspended/rejected (or otherwise non-approved) accounts must
                # not self-reactivate through the invitation flow.
                return {"success": False, "error": "This account cannot be verified through this link. Please contact support."}
            parent_id = row["user_id"]
            cur.execute("UPDATE users SET full_name=%s WHERE user_id=%s", (valid["parent_name"], parent_id))
        else:
            raw_pw = form_data.get("password", "")
            if not raw_pw or len(raw_pw) < 8:
                return {"success": False, "error": "Please set a password of at least 8 characters for your new LittleNet parent account."}
            cur.execute(
                """INSERT INTO users(username, full_name, email, password_hash, role, account_status)
                   VALUES(%s, %s, %s, %s, 'PARENT', 'PENDING_APPROVAL')
                   RETURNING user_id""",
                (parent_email, valid["parent_name"], parent_email, hash_password(raw_pw)),
            )
            parent_id = cur.fetchone()["user_id"]
        conn.commit()
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        logger.exception("Database error while creating pending parent record")
        return {"success": False, "error": "Database error while processing verification."}
    finally:
        conn.close()
    return {"success": True, "already_active": False, "parent_id": parent_id}


def process_parent_verification(token, form_data):
    """Email-OTP-verified guardian check for the child-approval token flow.

    Parent face/selfie/liveness verification was removed by explicit product
    decision: identity is proven by ownership of the parent email address (the
    caller verifies an email OTP before invoking this for new parents; parents
    that already hold an ACTIVE account were verified at registration).
    Creates or activates the parent account, records the VERIFIED guardian
    audit row (the record the ``littlenet_guard_parent_child_approval`` DB
    trigger treats as authoritative), and returns an approval token for the
    child-approval step.
    """
    map_data = get_parent_verification_data(token)
    if not map_data:
        return {"success": False, "error": "Invalid or expired verification invitation link."}

    child_id = map_data["child_id"]
    parent_email = map_data["parent_email"].strip().lower()

    valid, error = _validate_token_guardian_form(map_data, form_data)
    if error:
        return {"success": False, "error": error}
    parent_name = valid["parent_name"]

    # Create or link Parent Account
    conn = get_db_connection()
    if not conn:
        return {"success": False, "error": "Database error while processing verification."}

    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT user_id, account_status FROM users WHERE LOWER(email)=%s AND role='PARENT'",
            (parent_email,),
        )
        parent_user = cur.fetchone()

        if parent_user:
            parent_id = parent_user["user_id"]
            prior_status = parent_user.get("account_status")
            if prior_status == "ACTIVE":
                # Already-verified parent (e.g. approving another child via the
                # already_active branch): update the name only, never touch
                # account_status here.
                cur.execute(
                    "UPDATE users SET full_name=%s WHERE user_id=%s",
                    (parent_name, parent_id),
                )
            elif prior_status == "PENDING_APPROVAL":
                # Activate only from PENDING_APPROVAL: the status predicate
                # makes a suspended/rejected account unable to self-reactivate
                # even if the status changed between the SELECT and this UPDATE.
                cur.execute(
                    "UPDATE users SET full_name=%s, account_status='ACTIVE' WHERE user_id=%s AND account_status='PENDING_APPROVAL'",
                    (parent_name, parent_id),
                )
                if cur.rowcount == 0:
                    conn.rollback()
                    return {"success": False, "error": "This account cannot be verified through this link. Please contact support."}
            else:
                # SUSPENDED / REJECTED / DEACTIVATED / unknown: refuse.
                conn.rollback()
                return {"success": False, "error": "This account cannot be verified through this link. Please contact support."}
        else:
            raw_pw = form_data.get("password", "")
            if not raw_pw or len(raw_pw) < 8:
                conn.rollback()
                return {"success": False, "error": "Please set a password of at least 8 characters for your new LittleNet parent account."}
            cur.execute(
                """INSERT INTO users(username, full_name, email, password_hash, role, account_status)
                   VALUES(%s, %s, %s, %s, 'PARENT', 'ACTIVE')
                   RETURNING user_id""",
                (parent_email, parent_name, parent_email, hash_password(raw_pw)),
            )
            parent_id = cur.fetchone()["user_id"]

        # Record Verification Audit (email-OTP based; no liveness/face evidence)
        masked = _mask_parent_email(parent_email)
        cur.execute(
            """INSERT INTO parent_verifications(
                   parent_user_id, child_id, verification_provider, verification_status,
                   document_type, masked_id,
                   consent_given, consent_timestamp, verified_at)
               VALUES(%s, %s, 'EMAIL_OTP', 'VERIFIED',
                      'GUARDIAN_DECLARATION', %s, TRUE, NOW(), NOW())""",
            (parent_id, child_id, masked),
        )

        # Generate secure approval token
        approval_token = str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(hours=48)

        auto_approved = form_data.get("auto_approve") == "1"
        if auto_approved:
            # Instant 1-Step Activation: the parent proved email ownership via OTP.
            cur.execute("UPDATE users SET account_status = 'ACTIVE' WHERE user_id = %s", (child_id,))
            cur.execute(
                """UPDATE parent_child_map
                   SET parent_id = %s,
                       verified_parent_id = %s,
                       approval_token = %s,
                       approved = TRUE,
                       approved_at = NOW(),
                       is_token_used = TRUE,
                       approval_status = 'APPROVED'
                   WHERE verification_token = %s OR approval_token = %s""",
                (parent_id, parent_id, approval_token, token, token),
            )
            cur.execute(
                """INSERT INTO parent_safety_settings(child_id, parent_id, safety_level)
                   VALUES(%s, %s, 'STRICT')
                   ON CONFLICT (child_id) DO UPDATE SET parent_id = EXCLUDED.parent_id""",
                (child_id, parent_id),
            )
            cur.execute(
                """INSERT INTO child_time_limits(child_id, daily_limit_minutes, strict_mode)
                   VALUES(%s, 60, TRUE)
                   ON CONFLICT (child_id) DO NOTHING""",
                (child_id,),
            )
            cur.execute(
                """INSERT INTO parent_control_settings(child_id, parent_id, allow_reels, allow_stories, allow_messaging, allow_posting, allow_discover, educational_only_feed)
                   VALUES(%s, %s, TRUE, TRUE, TRUE, TRUE, TRUE, FALSE)
                   ON CONFLICT (child_id) DO NOTHING""",
                (child_id, parent_id),
            )
        else:
            cur.execute(
                """UPDATE parent_child_map
                   SET parent_id = %s,
                       verified_parent_id = %s,
                       approval_token = %s,
                       approval_token_expires_at = %s,
                       approval_status = 'AWAITING_PARENT_APPROVAL',
                       is_token_used = FALSE
                   WHERE verification_token = %s OR approval_token = %s""",
                (parent_id, parent_id, approval_token, expires_at, token, token),
            )

        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.exception("Database error while processing parent verification")
        return {"success": False, "error": "Database error while processing verification."}
    finally:
        conn.close()

    # Send Approval Email to Parent
    base_url = Config.BASE_URL.rstrip('/')
    approval_url = f"{base_url}/parent/approve-child/{approval_token}/"
    approval_body = f"""
    <h2>LittleNet Parent Verification Complete</h2>
    <p>Your parent email ownership for <strong>{parent_name}</strong> has been successfully verified.</p>
    <p><a href="{approval_url}" style="display:inline-block;padding:12px 24px;background:#0095F6;color:#ffffff;text-decoration:none;border-radius:8px;font-weight:bold;">Review & Approve {map_data['child_name']}'s Account</a></p>
    """
    try:
        with open("mailg/templates/approval_email.html", "r", encoding="utf-8") as f:
            approval_body = Template(f.read()).render(
                parent_name=parent_name,
                child_name=map_data["child_name"],
                child_username=map_data["child_username"],
                child_age=map_data["child_age"],
                approval_url=approval_url
            )
    except Exception as e:
        print(f"[APPROVAL MAIL TEMPLATE WARN] {e}")

    send_email(
        parent_email,
        f"LittleNet: Review & Approve Child Account for {map_data['child_name']}",
        approval_body
    )

    return {
        "success": True,
        "status": "VERIFIED",
        "parent_id": parent_id,
        "parent_email": parent_email,
        "approval_token": approval_token,
        "masked_id": masked,
        "auto_approved": auto_approved
    }


def get_child_approval_details(approval_token, logged_in_parent_id):
    """
    Validates approval token, single-use status, expiration, and parent authorization.
    Returns structured data for the approval page or a specific invalid reason.
    """
    conn = get_db_connection()
    if not conn:
        return {"valid": False, "reason": "DATABASE_ERROR"}

    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT 
                pcm.map_id,
                pcm.child_id,
                pcm.parent_id,
                pcm.verified_parent_id,
                pcm.parent_name,
                pcm.parent_email,
                pcm.approval_token,
                pcm.approval_token_expires_at,
                pcm.approval_status,
                pcm.approved,
                pcm.is_token_used,
                u.username AS child_username,
                u.full_name AS child_name,
                u.age AS child_age,
                u.email AS child_email,
                u.account_status AS child_account_status,
                u.created_at AS child_created_at
            FROM parent_child_map pcm
            JOIN users u ON pcm.child_id = u.user_id
            WHERE pcm.approval_token = %s
        """, (approval_token,))

        data = cur.fetchone()
        if not data:
            return {"valid": False, "reason": "INVALID_TOKEN"}

        # Token already used or approved
        if data.get("is_token_used") or data.get("approved"):
            return {"valid": False, "reason": "TOKEN_ALREADY_USED", "data": data}

        # Check expiration
        if data.get("approval_token_expires_at"):
            now_utc = datetime.now(timezone.utc)
            expires_at = data["approval_token_expires_at"]
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if now_utc > expires_at:
                return {"valid": False, "reason": "TOKEN_EXPIRED", "data": data}

        # Authorization: Parent must be verified parent
        expected_parent_id = data.get("verified_parent_id") or data.get("parent_id")
        if expected_parent_id and logged_in_parent_id != expected_parent_id:
            return {"valid": False, "reason": "UNAUTHORIZED_PARENT", "data": data}

        # Query verification record
        cur.execute("""
            SELECT verification_status, masked_id, document_type
            FROM parent_verifications
            WHERE parent_user_id = %s AND child_id = %s
            ORDER BY verification_id DESC LIMIT 1
        """, (expected_parent_id, data["child_id"]))
        ver_row = cur.fetchone()
        if not ver_row or ver_row.get("verification_status") != "VERIFIED":
            return {"valid": False, "reason": "PARENT_VERIFICATION_REQUIRED", "data": data}
        verification_data = {
            "status": "VERIFIED",
            "masked_id": ver_row["masked_id"] if ver_row.get("masked_id") else "GUARDIAN-VERIFIED",
            "document_type": ver_row["document_type"] if ver_row.get("document_type") else "GUARDIAN_DECLARATION"
        }

        return {
            "valid": True,
            "child": {
                "child_id": data["child_id"],
                "full_name": data["child_name"],
                "username": data["child_username"],
                "age": data["child_age"],
                "email": data["child_email"],
                "created_at": data["child_created_at"]
            },
            "parent": {
                "name": data["parent_name"],
                "email": data["parent_email"]
            },
            "verification": verification_data,
            "map_id": data["map_id"],
            "token": approval_token
        }
    finally:
        conn.close()

def process_child_decision(approval_token, logged_in_parent_id, decision, rejection_reason=None):
    """
    Approves or declines a child account with single-use token invalidation.
    Strictly verifies that logged_in_parent_id matches the linked verified parent.
    """
    check = get_child_approval_details(approval_token, logged_in_parent_id)
    if not check["valid"]:
        return {"success": False, "error": f"Cannot complete action: {check['reason']}"}

    child_id = check["child"]["child_id"]
    child_name = check["child"]["full_name"]
    child_email = check["child"]["email"]
    parent_email = check["parent"]["email"]

    conn = get_db_connection()
    if not conn:
        return {"success": False, "error": "Database error while processing decision."}

    try:
        cur = conn.cursor()
        if decision.upper() == "APPROVE":
            cur.execute("UPDATE users SET account_status = 'ACTIVE' WHERE user_id = %s", (child_id,))
            cur.execute("""
                UPDATE parent_child_map
                SET approved = TRUE,
                    approved_at = NOW(),
                    is_token_used = TRUE,
                    approval_status = 'APPROVED'
                WHERE approval_token = %s
            """, (approval_token,))

            # Initialize default controls & safety settings
            cur.execute("""
                INSERT INTO parent_safety_settings(child_id, parent_id, safety_level)
                VALUES(%s, %s, 'STRICT')
                ON CONFLICT (child_id) DO UPDATE SET parent_id = EXCLUDED.parent_id
            """, (child_id, logged_in_parent_id))

            cur.execute("""
                INSERT INTO child_time_limits(child_id, daily_limit_minutes, strict_mode)
                VALUES(%s, 60, TRUE)
                ON CONFLICT (child_id) DO NOTHING
            """, (child_id,))

            cur.execute("""
                INSERT INTO parent_control_settings(child_id, parent_id, allow_reels, allow_stories, allow_messaging, allow_posting, allow_discover, educational_only_feed)
                VALUES(%s, %s, TRUE, TRUE, TRUE, TRUE, TRUE, FALSE)
                ON CONFLICT (child_id) DO NOTHING
            """, (child_id, logged_in_parent_id))

            cur.execute("""
                INSERT INTO activity_logs(child_id, activity_type, activity_data)
                VALUES(%s, 'PARENT_APPROVED', %s::jsonb)
            """, (child_id, f'{{"approved_by": {logged_in_parent_id}}}'))

            conn.commit()

            # Dispatch confirmation email to parent and child
            send_email(
                child_email,
                "LittleNet: Your Account Has Been Approved!",
                f"<h2>Welcome to LittleNet, {child_name}!</h2><p>Your parent has verified your account. You can now log in and explore Kids Mode!</p><p><a href='{Config.BASE_URL.rstrip('/')}/login/?mode=kids'>Log in to LittleNet</a></p>"
            )
            return {"success": True, "action": "APPROVED", "child_name": child_name}

        else:
            cur.execute("UPDATE users SET account_status = 'REJECTED' WHERE user_id = %s", (child_id,))
            cur.execute("""
                UPDATE parent_child_map
                SET approved = FALSE,
                    is_token_used = TRUE,
                    approval_status = 'REJECTED',
                    rejection_reason = %s
                WHERE approval_token = %s
            """, (rejection_reason or "Declined by supervising parent", approval_token))
            conn.commit()
            return {"success": True, "action": "DECLINED", "child_name": child_name}
    except Exception as e:
        conn.rollback()
        logger.exception("Database error while processing child decision")
        return {"success": False, "error": "Database error while processing decision."}
    finally:
        conn.close()

def approve_child_account(token):
    """Deprecated token-only approval path; intentionally fail closed.

    Child activation requires a verified Parent session and the normal
    ``process_child_decision`` authorization path.
    """
    raise RuntimeError("Direct token-only child approval is disabled; parent verification is required")

def parent_verification_complete(parent_user_id):
    """Authoritative check: has this PARENT completed identity verification?

    Used by admin account-status transitions so an admin can never activate
    an unverified/pending parent (UI hiding is not security). Evidence is
    read from existing authoritative records only — no new state invented:

    1. ``parent_verifications`` row with ``verification_status='VERIFIED'``
       (token guardian flow: verified email OTP + guardian consent + 18+
       declaration — the same record the database trigger
       ``littlenet_guard_parent_child_approval`` treats as authoritative), OR
    2. ``parent_email_otps.verified_at`` is set (standalone registration:
       verified email OTP is now the complete parent identity verification —
       the live selfie/liveness step was removed by explicit product decision).

    Security-bar note: prong 2 previously also required a face/liveness
    check at parent registration; that entire mechanism was removed by
    explicit product decision (all child and parent face artifacts removed).
    The remaining assurance for a parent is a server-validated 18+
    date-of-birth declaration, email ownership via a hashed / expiring /
    attempt-limited OTP, explicit guardian consent, and a password. The admin
    activation gates (web ``admin/routes.py`` and mobile
    ``mobile/admin_api.py``) still enforce this server-side.
    """
    try:
        uid = int(parent_user_id)
    except (TypeError, ValueError):
        return False
    verified = fetch_one(
        "SELECT 1 FROM parent_verifications WHERE parent_user_id=%s AND verification_status='VERIFIED' LIMIT 1",
        (uid,),
    )
    if verified:
        return True
    otp = fetch_one("SELECT verified_at FROM parent_email_otps WHERE user_id=%s", (uid,))
    return bool(otp and otp.get("verified_at"))

def login_user(identifier, password):
    val = (identifier or '').strip()
    pwd = password or ''
    row = fetch_one('SELECT * FROM users WHERE LOWER(email)=%s OR LOWER(username)=%s', (val.lower(), val.lower()))
    if not row:
        return None
    # Per-account failed-login throttle (T1-007). Keyed by the canonical
    # user_id so username/email aliases share one budget. A locked account
    # returns None exactly like a wrong password — the lockout is never
    # revealed, and no distinct throttling response exists.
    uid = row['user_id']
    if login_throttle.is_locked(uid):
        return None
    # Tolerate accidental leading/trailing whitespace in a pasted password, but
    # otherwise require a real bcrypt match. No hardcoded credential bypass.
    if not check_password(pwd, row['password_hash']) and not (
        pwd != pwd.strip() and check_password(pwd.strip(), row['password_hash'])
    ):
        login_throttle.record_failure(uid)
        return None
    if row['account_status']!='ACTIVE' and row['account_status'] != 'PENDING_APPROVAL':
        return None
    # Successful authentication clears the accumulated failure state.
    login_throttle.clear(uid)
    return row

def profile_exists(child_id):
    return bool(fetch_one('SELECT 1 FROM child_profiles WHERE child_id=%s', (child_id,)))

def register_parent_account(token, form):
    password = form.get('password', '')
    if len(password)<8:return False,'weak_password'
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute('SELECT * FROM parent_child_map WHERE (approval_token=%s OR verification_token=%s) AND approved=TRUE FOR UPDATE', (token, token))
        mapping = cur.fetchone()
        if not mapping:
            conn.rollback()
            return False, 'invalid_token'
        if mapping.get('parent_id'):
            conn.rollback()
            return False, 'already_linked'
        email = mapping['parent_email'].lower()
        cur.execute("SELECT * FROM users WHERE LOWER(email)=%s AND role='PARENT'", (email,))
        existing = cur.fetchone()
        if existing:
            if not check_password(password, existing['password_hash']):
                conn.rollback()
                return False, 'wrong_existing_parent_password'
            parent_id = existing['user_id']
        else:
            cur.execute("INSERT INTO users(username,full_name,email,password_hash,role,account_status) VALUES(%s,%s,%s,%s,'PARENT','ACTIVE') RETURNING user_id", (email, mapping['parent_name'], email, hash_password(password)))
            parent_id = cur.fetchone()['user_id']
        cur.execute('UPDATE parent_child_map SET parent_id=%s WHERE map_id=%s AND parent_id IS NULL', (parent_id, mapping['map_id']))
        cur.execute("INSERT INTO parent_safety_settings(child_id,parent_id,safety_level) VALUES(%s,%s,'STRICT') ON CONFLICT(child_id) DO UPDATE SET parent_id=EXCLUDED.parent_id", (mapping['child_id'], parent_id))
        conn.commit()
        return True, None
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def create_child_by_parent(parent_id, form):
    """Atomically create + approve a child from an authenticated Parent Mode account."""
    username = (form.get('username') or '').strip()
    if not validate_username(username):
        raise ValueError('invalid_username')
    full_name = (form.get('full_name') or '').strip() or username.capitalize()
    if not validate_name(full_name):
        full_name = username.capitalize()
    try:
        age = int(form.get('age') or 10)
    except (TypeError, ValueError):
        age = 10
    if not 6 <= age <= 16:
        age = 10
    password = form.get('password', '')
    if len(password) < 8:
        raise ValueError('weak_password')
    email = (form.get('email') or '').strip().lower()
    if not email or '@' not in email:
        email = f"{username.lower()}@kids.littlenet.internal"
    try:
        limit = int(form.get('daily_limit') or 60)
    except (TypeError, ValueError):
        limit = 60
    if not 1 <= limit <= 1440:
        limit = 60
    safety = (form.get('safety_level') or 'STRICT').upper()
    if safety not in {'STANDARD', 'STRICT', 'VERY_STRICT'}:
        safety = 'STRICT'
    parent = fetch_one("SELECT * FROM users WHERE user_id=%s AND role='PARENT' AND account_status='ACTIVE'", (parent_id,))
    if not parent:
        raise ValueError('invalid_parent')
    confirm_token = str(uuid.uuid4())
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        # The child account is provisioned with every control/safety row already
        # in place, but stays PENDING_APPROVAL (cannot log in) until the parent
        # clicks the emailed confirmation link. This is a deliberate second step
        # so a mistyped form submit or a shared device can't silently activate a
        # new child login -- the parent must confirm from their own inbox.
        cur.execute("""INSERT INTO users(username,full_name,email,password_hash,role,age,account_status)
          VALUES(%s,%s,%s,%s,'CHILD',%s,'PENDING_APPROVAL') RETURNING user_id""",
          (username, full_name, email, hash_password(password), age))
        child_id = cur.fetchone()['user_id']
        cur.execute("""INSERT INTO parent_child_map(child_id,parent_id,parent_name,parent_email,approval_token,approved,approval_status,is_token_used)
          VALUES(%s,%s,%s,%s,%s,FALSE,'PENDING_EMAIL_CONFIRMATION',FALSE)""", (child_id, parent_id, parent['full_name'], parent['email'], confirm_token))
        cur.execute("""INSERT INTO child_profiles(child_id,parent_id,full_name,date_of_birth,age,school_name,location,current_class,bio)
          VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""", (child_id, parent_id, full_name, form.get('date_of_birth') or None, age, form.get('school_name'), form.get('location'), form.get('current_class'), form.get('bio') or "Hey! I'm on LittleNet 🌟"))
        cur.execute("INSERT INTO parent_safety_settings(child_id,parent_id,safety_level) VALUES(%s,%s,%s)", (child_id, parent_id, safety))
        cur.execute("INSERT INTO child_time_limits(child_id,daily_limit_minutes,strict_mode) VALUES(%s,%s,%s)", (child_id, limit, form.get('strict_mode') != 'off'))
        
        allow_reels = form.get('allow_reels', '1') in ('1', 'on', 'true', True)
        allow_stories = form.get('allow_stories', '1') in ('1', 'on', 'true', True)
        allow_messaging = form.get('allow_messaging', '1') in ('1', 'on', 'true', True)
        allow_posting = form.get('allow_posting', '1') in ('1', 'on', 'true', True)
        allow_discover = form.get('allow_discover', '1') in ('1', 'on', 'true', True)
        educational_only = form.get('educational_only_feed', '0') in ('1', 'on', 'true', True)

        cur.execute("""INSERT INTO parent_control_settings(child_id,parent_id,allow_reels,allow_stories,allow_messaging,allow_posting,allow_discover,educational_only_feed)
          VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""", (child_id, parent_id, allow_reels, allow_stories, allow_messaging, allow_posting, allow_discover, educational_only))
        cur.execute("INSERT INTO activity_logs(child_id,activity_type,activity_data) VALUES(%s,'ACCOUNT_CREATED_BY_PARENT',%s::jsonb)", (child_id, '{"awaiting_email_confirmation":true}'))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    confirm_url = f"{Config.BASE_URL.rstrip('/')}/parent/confirm-child/{confirm_token}/"
    send_email(
        parent['email'],
        f"LittleNet: Confirm {full_name}'s new account",
        f"""<h2>Confirm {full_name}'s LittleNet account</h2>
        <p>You just created a Kids Mode account for <strong>{full_name}</strong> (@{username}) on LittleNet.</p>
        <p>For safety, the account stays inactive until you confirm it was really you:</p>
        <p><a href="{confirm_url}" style="display:inline-block;padding:12px 24px;background:#20c997;color:#ffffff;text-decoration:none;border-radius:8px;font-weight:bold;">Confirm & activate account</a></p>
        <p>If you did not request this, ignore this email and the account will remain inactive.</p>"""
    )
    return child_id, confirm_token
