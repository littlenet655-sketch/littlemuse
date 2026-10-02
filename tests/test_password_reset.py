import pytest
import bcrypt
from auth.password_reset import (
    request_password_reset,
    verify_and_reset_password,
    parent_reset_child_password,
    OTP_MAX_ATTEMPTS,
    _otp_hash,
)
from database.connection import execute, fetch_one


def test_password_reset_flow():
    # Setup test parent and child
    test_p_email = "test_parent_reset@example.com"
    test_c_uname = "test_child_reset_user"

    # Cleanup any previous runs
    execute("DELETE FROM users WHERE email=%s OR username=%s", (test_p_email, test_c_uname))

    # 1. Create parent
    p_hash = bcrypt.hashpw(b"OldParentPass123!", bcrypt.gensalt()).decode("utf-8")
    execute(
        "INSERT INTO users(username, full_name, email, password_hash, role, account_status) "
        "VALUES('test_p_reset', 'Test Parent', %s, %s, 'PARENT', 'ACTIVE')",
        (test_p_email, p_hash),
    )
    p_row = fetch_one("SELECT user_id FROM users WHERE email=%s", (test_p_email,))
    assert p_row is not None
    p_id = p_row["user_id"]

    # 2. Create child linked to parent
    c_hash = bcrypt.hashpw(b"OldChildPass123!", bcrypt.gensalt()).decode("utf-8")
    execute(
        "INSERT INTO users(username, full_name, email, password_hash, role, account_status) "
        "VALUES(%s, 'Test Child', %s, %s, 'CHILD', 'ACTIVE')",
        (test_c_uname, f"{test_c_uname}@kids.littlenet.internal", c_hash),
    )
    c_row = fetch_one("SELECT user_id FROM users WHERE username=%s", (test_c_uname,))
    assert c_row is not None
    c_id = c_row["user_id"]

    execute(
        "INSERT INTO parent_child_map(parent_id, child_id, parent_name, parent_email, approved, approval_status) "
        "VALUES(%s, %s, 'Test Parent', %s, TRUE, 'APPROVED')",
        (p_id, c_id, test_p_email),
    )

    try:
        # 3. Test Parent Forgot Password (direct email)
        ok, err, info = request_password_reset(test_p_email)
        assert ok is True
        assert info["user_id"] == p_id
        assert "test_parent_reset" in info["masked_email"] or "@example.com" in info["masked_email"]
        assert info["is_parent_proxy"] is False

        # 4. Test Child Forgot Password (routes to parent email proxy)
        ok, err, info = request_password_reset(test_c_uname)
        assert ok is True
        assert info["user_id"] == c_id
        assert info["is_parent_proxy"] is True

        # 5. Verify invalid OTP rejection
        ok, msg = verify_and_reset_password(c_id, "000000", "NewChildPass123!")
        assert ok is False
        assert "Incorrect" in msg or "invalid" in msg.lower()

        # 6. Verify password too short rejection
        ok, msg = verify_and_reset_password(c_id, "123456", "short")
        assert ok is False
        assert "at least 8 characters" in msg

        # 7. Parent resets child password directly from Parent Controls
        ok, msg = parent_reset_child_password(p_id, c_id, "NewParentGivenChildPass123!")
        assert ok is True
        c_updated = fetch_one("SELECT password_hash FROM users WHERE user_id=%s", (c_id,))
        assert bcrypt.checkpw(b"NewParentGivenChildPass123!", c_updated["password_hash"].encode("utf-8"))

        # 8. Admin user deletion cascades
        execute("DELETE FROM users WHERE user_id=%s AND role<>'ADMIN'", (c_id,))
        assert fetch_one("SELECT user_id FROM users WHERE user_id=%s", (c_id,)) is None
        assert fetch_one("SELECT map_id FROM parent_child_map WHERE child_id=%s", (c_id,)) is None

    finally:
        # Cleanup
        execute("DELETE FROM users WHERE email=%s OR username=%s", (test_p_email, test_c_uname))


def test_password_reset_cooldown_and_attempt_window():
    """Focused tests for the 60s resend cooldown and the 5-attempt window.

    Rules under test:
    1. A re-request inside the 60s cooldown does not churn the live code.
    2. A re-request after the cooldown churns the code but keeps the
       attempt counter (no fresh guessing budget).
    3. Once the 5-attempt budget is burned on a live code, re-requests do
       not issue a new code until the current one expires.
    4. An expired code re-request starts a fresh attempt budget.
    5. All responses stay uniform (no existence/oracle leakage).
    """
    test_email = "test_parent_cooldown@example.com"
    test_uname = "test_parent_cooldown_user"

    execute("DELETE FROM users WHERE email=%s OR username=%s", (test_email, test_uname))
    execute("DELETE FROM password_reset_otps")

    p_hash = bcrypt.hashpw(b"CooldownParentPass123!", bcrypt.gensalt()).decode("utf-8")
    execute(
        "INSERT INTO users(username, full_name, email, password_hash, role, account_status) "
        "VALUES(%s, 'Cooldown Parent', %s, %s, 'PARENT', 'ACTIVE')",
        (test_uname, test_email, p_hash),
    )
    p_row = fetch_one("SELECT user_id FROM users WHERE email=%s", (test_email,))
    assert p_row is not None
    p_id = p_row["user_id"]

    def row():
        return fetch_one(
            "SELECT code_hash, attempts, expires_at, sent_at FROM password_reset_otps WHERE user_id=%s",
            (p_id,),
        )

    try:
        # 1. First request issues a code with a fresh budget.
        ok, msg, info = request_password_reset(test_email)
        assert ok is True and info is not None
        first = row()
        assert first["attempts"] == 0
        assert first["expires_at"] is not None
        code_a = first["code_hash"]

        # 2. Immediate re-request (inside 60s cooldown): uniform response,
        #    code untouched, attempts untouched.
        ok, msg, info = request_password_reset(test_email)
        assert ok is True and info is None
        again = row()
        assert again["code_hash"] == code_a
        assert again["attempts"] == 0

        # 3. After cooldown: new code churned, attempt counter preserved.
        execute(
            "UPDATE password_reset_otps SET sent_at = NOW() - INTERVAL '61 seconds' WHERE user_id=%s",
            (p_id,),
        )
        # Simulate 2 wrong guesses already burned on the live code.
        execute(
            "UPDATE password_reset_otps SET attempts = 2 WHERE user_id=%s",
            (p_id,),
        )
        ok, msg, info = request_password_reset(test_email)
        assert ok is True and info is not None
        rechurned = row()
        assert rechurned["code_hash"] != code_a, "re-request after cooldown must churn the code"
        assert rechurned["attempts"] == 2, "re-request must not reset the attempt budget"
        code_b = rechurned["code_hash"]

        # 4. Burn the full 5-attempt budget with wrong codes (2 already burned).
        for _ in range(OTP_MAX_ATTEMPTS - 2):
            ok, msg = verify_and_reset_password(p_id, "000000", "CooldownNewPass123!")
            assert ok is False
        burned = row()
        assert burned["attempts"] >= 5

        # 5. After cooldown with a burned budget: uniform response, but NO
        #    new code is issued — the old (unknown-to-attacker) code stands.
        execute(
            "UPDATE password_reset_otps SET sent_at = NOW() - INTERVAL '61 seconds' WHERE user_id=%s",
            (p_id,),
        )
        ok, msg, info = request_password_reset(test_email)
        assert ok is True and info is None
        still = row()
        assert still["code_hash"] == code_b, "burned budget must block re-issue while code is live"
        assert still["attempts"] >= 5

        # Verify still reports the lockout while the code is live.
        ok, msg = verify_and_reset_password(p_id, "000000", "CooldownNewPass123!")
        assert ok is False and "Too many incorrect attempts" in msg

        # 6. After the code expires, a fresh request gets a fresh budget.
        execute(
            "UPDATE password_reset_otps SET expires_at = NOW() - INTERVAL '1 second' WHERE user_id=%s",
            (p_id,),
        )
        ok, msg, info = request_password_reset(test_email)
        assert ok is True and info is not None
        fresh = row()
        assert fresh["code_hash"] != code_b
        assert fresh["attempts"] == 0
    finally:
        execute("DELETE FROM users WHERE email=%s OR username=%s", (test_email, test_uname))
        execute("DELETE FROM password_reset_otps WHERE user_id=%s", (p_id,))
