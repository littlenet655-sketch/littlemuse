"""OTP hardening fixtures (mock-only: no database, no email, no network)."""
from datetime import datetime, timedelta, timezone

import pytest

from auth import parent_email_otp as otp
from auth import password_reset as pr


class _Cur:
    def __init__(self, handler):
        self.handler, self.statements, self._row = handler, [], None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        q = " ".join(str(sql).split())
        self.statements.append((q, params))
        self._row = self.handler(q, params)

    def fetchone(self):
        return self._row


class _Conn:
    def __init__(self, handler):
        self.cur = _Cur(handler)
        self.committed = self.rolled_back = False

    def cursor(self):
        return self.cur

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass

    def sql(self):
        return [s for s, _ in self.cur.statements]


NOW = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)


def _verify(monkeypatch, row, code="123456", user_id=5):
    def handler(q, _p):
        if "FROM parent_email_otps o" in q:
            return row
        if q.startswith("SELECT NOW()"):
            return {"now": NOW}
        return None

    conn = _Conn(handler)
    monkeypatch.setattr(otp, "_ensure_table", lambda: None)
    monkeypatch.setattr(otp, "get_db_connection", lambda: conn)
    monkeypatch.setattr(otp, "fetch_one", lambda *a, **k: {"user_id": user_id})
    return otp.verify_parent_email_otp(user_id, code), conn


def _row(code="123456", user_id=5, **kw):
    base = {
        "code_hash": otp._otp_hash(user_id, code), "expires_at": NOW + timedelta(minutes=5),
        "attempts": 0, "verified_at": None, "user_id": user_id, "email": "p@x.invalid",
        "full_name": "P", "role": "PARENT", "account_status": "PENDING_APPROVAL",
    }
    base.update(kw)
    return base


# ── generation / hashing ─────────────────────────────────────────────────────
def test_code_is_six_digits_and_uses_csprng():
    import inspect

    assert "secrets.randbelow" in inspect.getsource(otp._new_code)
    assert "secrets.randbelow" in inspect.getsource(pr.request_password_reset)
    assert all(len(otp._new_code()) == 6 and otp._new_code().isdigit() for _ in range(50))


def test_hash_is_user_bound_and_not_plaintext():
    assert otp._otp_hash(1, "123456") != otp._otp_hash(2, "123456")
    assert "123456" not in otp._otp_hash(1, "123456")
    assert pr._otp_hash(1, "123456") != pr._otp_hash(2, "123456")


def test_parent_signup_normalizes_email_lowercase():
    username, _name, email, _password, _dob = otp._validate_registration({
        "username": "parentok", "full_name": "Parent Ok",
        "email": "  Parent.OK@Example.COM  ", "password": "password1",
        "dob": "1990-01-01", "guardian_declaration": "1",
    })
    assert username == "parentok" and email == "parent.ok@example.com"


# ── parent email OTP verify ──────────────────────────────────────────────────
def test_verify_success_marks_verified(monkeypatch):
    (ok, err, user), conn = _verify(monkeypatch, _row())
    assert ok and err is None and user
    assert any("SET verified_at=NOW()" in s for s in conn.sql()) and conn.committed


def test_verify_wrong_code_increments_attempts_only(monkeypatch):
    (ok, err, _), conn = _verify(monkeypatch, _row(), code="000000")
    assert not ok and "Incorrect" in err
    assert any("attempts=attempts+1" in s and "attempts < %s" in s for s in conn.sql())
    assert not any("verified_at=NOW()" in s for s in conn.sql())


def test_verify_expired_code_rejected(monkeypatch):
    (ok, err, _), conn = _verify(monkeypatch, _row(expires_at=NOW - timedelta(seconds=1)))
    assert not ok and "expired" in err
    assert not any("verified_at=NOW()" in s for s in conn.sql())


def test_verify_replay_after_success_rejected(monkeypatch):
    (ok, err, _), _ = _verify(monkeypatch, _row(verified_at=NOW))
    assert not ok and "already been used" in err


def test_verify_locked_after_max_attempts_even_with_right_code(monkeypatch):
    (ok, err, _), _ = _verify(monkeypatch, _row(attempts=otp.OTP_MAX_ATTEMPTS))
    assert not ok and "Too many" in err


@pytest.mark.parametrize("bad", ["", "12345", "1234567", "abcdef", "12 456", None])
def test_verify_rejects_malformed_before_db(monkeypatch, bad):
    monkeypatch.setattr(otp, "_ensure_table", lambda: None)
    monkeypatch.setattr(otp, "get_db_connection", lambda: (_ for _ in ()).throw(AssertionError("db")))
    ok, err, _ = otp.verify_parent_email_otp(5, bad)
    assert not ok


# ── parent email OTP resend ──────────────────────────────────────────────────
def _resend(monkeypatch, existing, cooldown=False):
    sent = []

    def handler(q, _p):
        if q.startswith("SELECT sent_at, verified_at, attempts"):
            return existing
        if "sent_at > NOW() - INTERVAL '60 seconds'" in q:
            return {"?column?": 1} if cooldown else None
        return None

    conn = _Conn(handler)
    monkeypatch.setattr(otp, "_ensure_table", lambda: None)
    monkeypatch.setattr(otp, "get_db_connection", lambda: conn)
    monkeypatch.setattr(otp, "fetch_one", lambda *a, **k: {
        "user_id": 5, "email": "p@x.invalid", "full_name": "P", "role": "PARENT",
        "account_status": "PENDING_APPROVAL", "verified_at": None,
    })
    monkeypatch.setattr(otp, "_send_code", lambda *a: sent.append(a) or True)
    return otp.resend_parent_email_otp(5, with_code=True), conn, sent


def test_resend_cooldown_blocks_second_code(monkeypatch):
    (ok, err, _), conn, sent = _resend(monkeypatch, {"sent_at": NOW, "verified_at": None, "attempts": 0, "live": True}, cooldown=True)
    assert not ok and "wait" in err
    assert sent == [] and not conn.committed


def test_resend_carries_attempts_while_previous_code_live(monkeypatch):
    (ok, _e, _c), conn, sent = _resend(monkeypatch, {"sent_at": NOW, "verified_at": None, "attempts": 3, "live": True})
    assert ok and len(sent) == 1
    insert = [(s, p) for s, p in conn.cur.statements if s.startswith("INSERT INTO parent_email_otps")][0]
    assert insert[1][2] == 3  # attempts_carry
    assert "attempts=EXCLUDED.attempts" in insert[0]


def test_resend_refused_when_live_code_budget_burned(monkeypatch):
    (ok, err, _), conn, sent = _resend(monkeypatch, {"sent_at": NOW, "verified_at": None, "attempts": otp.OTP_MAX_ATTEMPTS, "live": True})
    assert not ok and "Too many" in err
    assert sent == [] and not conn.committed


def test_resend_after_expiry_gets_fresh_attempt_budget(monkeypatch):
    (ok, _e, _c), conn, sent = _resend(monkeypatch, {"sent_at": NOW, "verified_at": None, "attempts": otp.OTP_MAX_ATTEMPTS, "live": False})
    assert ok and len(sent) == 1
    insert = [(s, p) for s, p in conn.cur.statements if s.startswith("INSERT INTO parent_email_otps")][0]
    assert insert[1][2] == 0


def test_resend_refused_for_verified_email(monkeypatch):
    (ok, err, _), _, sent = _resend(monkeypatch, {"sent_at": NOW, "verified_at": NOW, "attempts": 0, "live": False})
    assert not ok and "already verified" in err and sent == []


# ── dev OTP never printed / returned in production ───────────────────────────
@pytest.mark.parametrize("production", [True])
def test_dev_otp_never_printed_or_returned_in_production(monkeypatch, capsys, production):
    monkeypatch.setenv("ENABLE_DEV_OTP", "1")
    monkeypatch.setattr(otp.Config, "_PRODUCTION", True, raising=False)
    monkeypatch.setattr(otp, "send_parent_otp_email", lambda *a, **k: True)
    assert otp._dev_otp_enabled() is False
    assert otp._send_code(5, "p@x.invalid", "P", "654321") is True
    out = capsys.readouterr()
    assert "654321" not in out.out + out.err
    assert "PARENT OTP" not in out.out + out.err


def test_dev_otp_only_prints_when_explicit_and_non_production(monkeypatch, capsys):
    monkeypatch.setattr(otp, "send_parent_otp_email", lambda *a, **k: True)
    monkeypatch.setattr(otp.Config, "_PRODUCTION", False, raising=False)
    monkeypatch.delenv("ENABLE_DEV_OTP", raising=False)
    otp._send_code(5, "p@x.invalid", "P", "111111")
    assert "111111" not in capsys.readouterr().out
    monkeypatch.setenv("ENABLE_DEV_OTP", "1")
    otp._send_code(5, "p@x.invalid", "P", "222222")
    assert "222222" in capsys.readouterr().out


def test_otp_code_never_logged_by_password_reset_module():
    import inspect

    src = inspect.getsource(pr)
    assert "print(" not in src
    assert "logger" not in src or "code" not in "".join(
        line for line in src.splitlines() if "logger." in line
    )


# ── password reset verify ────────────────────────────────────────────────────
def _reset(monkeypatch, row, code="123456", acct="ACTIVE"):
    def handler(q, _p):
        if "FROM password_reset_otps" in q:
            return row
        if q.startswith("SELECT NOW()"):
            return {"now": NOW}
        if q.startswith("SELECT account_status"):
            return {"account_status": acct}
        return None

    conn = _Conn(handler)
    monkeypatch.setattr(pr, "_ensure_table", lambda: None)
    monkeypatch.setattr(pr, "get_db_connection", lambda: conn)
    return pr.verify_and_reset_password(5, code, "NewPassword123"), conn


def _prow(**kw):
    base = {"code_hash": pr._otp_hash(5, "123456"), "expires_at": NOW + timedelta(minutes=5), "attempts": 0}
    base.update(kw)
    return base


def test_reset_success_invalidates_code_and_sessions(monkeypatch):
    (ok, _m), conn = _reset(monkeypatch, _prow())
    assert ok
    sql = conn.sql()
    assert any("session_version" in s for s in sql)
    assert any(s.startswith("DELETE FROM password_reset_otps") for s in sql)


def test_reset_replay_after_success_finds_no_code(monkeypatch):
    (ok, msg), _ = _reset(monkeypatch, None)
    assert not ok and "No active password reset" in msg


def test_reset_expired_and_wrong_and_locked(monkeypatch):
    (ok, msg), _ = _reset(monkeypatch, _prow(expires_at=NOW - timedelta(seconds=1)))
    assert not ok and "expired" in msg
    (ok, msg), conn = _reset(monkeypatch, _prow(), code="000000")
    assert not ok and any("attempts = attempts + 1" in s for s in conn.sql())
    (ok, msg), conn = _reset(monkeypatch, _prow(attempts=pr.OTP_MAX_ATTEMPTS))
    assert not ok and "Too many" in msg
    assert not any(s.startswith("UPDATE users") for s in conn.sql())


def test_reset_refuses_suspended_account_even_with_valid_code(monkeypatch):
    (ok, msg), conn = _reset(monkeypatch, _prow(), acct="SUSPENDED")
    assert not ok and "suspended" in msg
    assert not any(s.startswith("UPDATE users") for s in conn.sql())


# ── password reset request: uniform handling / cooldown ─────────────────────
def test_reset_request_unknown_and_suspended_get_no_code(monkeypatch):
    monkeypatch.setattr(pr, "_ensure_table", lambda: None)
    monkeypatch.setattr(pr, "get_db_connection", lambda: (_ for _ in ()).throw(AssertionError("db")))
    monkeypatch.setattr(pr, "send_email", lambda *a, **k: (_ for _ in ()).throw(AssertionError("mail")))
    monkeypatch.setattr(pr, "fetch_one", lambda *a, **k: None)
    assert pr.request_password_reset("nobody") == (True, pr.UNIFORM_RESET_MESSAGE, None)
    monkeypatch.setattr(pr, "fetch_one", lambda *a, **k: {"user_id": 1, "account_status": "SUSPENDED", "email": "a@b.c", "role": "PARENT"})
    assert pr.request_password_reset("susp") == (True, pr.UNIFORM_RESET_MESSAGE, None)


def test_reset_request_within_cooldown_sends_nothing(monkeypatch):
    monkeypatch.setattr(pr, "_ensure_table", lambda: None)
    monkeypatch.setattr(pr, "send_email", lambda *a, **k: (_ for _ in ()).throw(AssertionError("mail")))
    monkeypatch.setattr(pr, "get_db_connection", lambda: (_ for _ in ()).throw(AssertionError("db")))
    calls = []

    def fake_fetch_one(sql, params=None):
        calls.append(sql)
        if "FROM password_reset_otps" in sql:
            return {"attempts": 0, "live": True, "within_cooldown": True}
        return {"user_id": 1, "username": "u", "full_name": "U", "email": "a@b.co", "role": "PARENT", "account_status": "ACTIVE"}

    monkeypatch.setattr(pr, "fetch_one", fake_fetch_one)
    assert pr.request_password_reset("u") == (True, pr.UNIFORM_RESET_MESSAGE, None)


# ── child approval token: single use, expiry, guardian binding ───────────────
def _approval(monkeypatch, row, parent_id=9):
    from auth import service as svc

    class _C:
        def __init__(self):
            self.n = 0

        def execute(self, *a, **k):
            self.n += 1

        def fetchone(self):
            return row if self.n == 1 else None

    class _K:
        def cursor(self):
            return _C()

        def close(self):
            pass

        def commit(self):
            pass

        def rollback(self):
            pass

    monkeypatch.setattr(svc, "get_db_connection", lambda: _K())
    return svc.get_child_approval_details("tok", parent_id)


def _arow(**kw):
    base = {"is_token_used": False, "approved": False, "approval_token_expires_at": NOW,
            "approval_token_expired": False, "verified_parent_id": 9, "parent_id": 9}
    base.update(kw)
    return base


def test_approval_token_unknown_used_expired_and_wrong_parent(monkeypatch):
    assert _approval(monkeypatch, None)["reason"] == "INVALID_TOKEN"
    assert _approval(monkeypatch, _arow(is_token_used=True))["reason"] == "TOKEN_ALREADY_USED"
    assert _approval(monkeypatch, _arow(approved=True))["reason"] == "TOKEN_ALREADY_USED"
    assert _approval(monkeypatch, _arow(approval_token_expired=True))["reason"] == "TOKEN_EXPIRED"
    assert _approval(monkeypatch, _arow(), parent_id=10)["reason"] == "UNAUTHORIZED_PARENT"
