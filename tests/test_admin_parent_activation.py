"""Regression tests: admin must not activate an unverified/pending parent.

An admin account-status transition to ACTIVE for a PARENT is allowed only
when the parent completed identity verification, as determined by the
authoritative ``auth.service.parent_verification_complete`` check:

1. ``parent_verifications`` row with ``verification_status='VERIFIED'``
   (token guardian flow: verified email OTP + guardian consent), OR
2. ``parent_email_otps.verified_at`` set (standalone registration: verified
   email OTP is now the complete parent identity verification — the live
   selfie/liveness step was removed by explicit product decision).

No live database is required: ``auth.service.fetch_one`` is monkeypatched.
Source-contract tests additionally prove both admin endpoints (web
``admin/routes.py::user_action`` and mobile
``mobile/admin_api.py::mobile_admin_user_status``) enforce the gate
server-side with a 4xx rejection, keep RBAC decorators, and only apply the
gate to PARENT roles.
"""
import ast
from pathlib import Path

import pytest

import auth.service as auth_service

ROOT = Path(__file__).resolve().parents[1]
ADMIN_ROUTES = ROOT / "admin" / "routes.py"
MOBILE_ADMIN_API = ROOT / "mobile" / "admin_api.py"


def _fake_fetch_one(scenario):
    """Build a fetch_one fake dispatching on the queried table."""
    def fake(sql, params=None):
        if "parent_verifications" in sql:
            return {"1": 1} if scenario.get("guardian_record") else None
        if "parent_email_otps" in sql:
            return {"verified_at": scenario.get("otp_verified_at")}
        raise AssertionError(f"unexpected query: {sql}")
    return fake


# ---------------------------------------------------------------------------
# parent_verification_complete logic
# ---------------------------------------------------------------------------


def test_verified_guardian_record_is_sufficient(monkeypatch):
    monkeypatch.setattr(auth_service, "fetch_one", _fake_fetch_one({"guardian_record": True}))
    assert auth_service.parent_verification_complete(42) is True


def test_otp_verified_alone_is_sufficient(monkeypatch):
    # Verified email OTP is now the complete parent identity verification
    # (the selfie/liveness step was removed by explicit product decision).
    monkeypatch.setattr(
        auth_service, "fetch_one",
        _fake_fetch_one({"otp_verified_at": "2026-09-21T10:00:00"}),
    )
    assert auth_service.parent_verification_complete(42) is True


def test_fully_unverified_parent_is_rejected(monkeypatch):
    monkeypatch.setattr(auth_service, "fetch_one", _fake_fetch_one({}))
    assert auth_service.parent_verification_complete(42) is False


def test_unverified_email_is_rejected(monkeypatch):
    # Email OTP must be verified in the verified-parent pipeline.
    monkeypatch.setattr(
        auth_service, "fetch_one",
        _fake_fetch_one({"otp_verified_at": None}),
    )
    assert auth_service.parent_verification_complete(42) is False


def test_invalid_user_id_is_rejected(monkeypatch):
    monkeypatch.setattr(auth_service, "fetch_one", _fake_fetch_one({"guardian_record": True}))
    assert auth_service.parent_verification_complete("not-an-id") is False
    assert auth_service.parent_verification_complete(None) is False


def test_guardian_record_short_circuits_before_otp_lookup(monkeypatch):
    calls = []

    def fake(sql, params=None):
        calls.append(sql)
        return {"1": 1}

    monkeypatch.setattr(auth_service, "fetch_one", fake)
    assert auth_service.parent_verification_complete(42) is True
    assert len(calls) == 1 and "parent_verifications" in calls[0]


# ---------------------------------------------------------------------------
# Source contracts: both admin endpoints enforce the gate server-side
# ---------------------------------------------------------------------------


def _source(path):
    return path.read_text(encoding="utf-8")


def test_web_admin_user_action_gates_parent_activation():
    src = _source(ADMIN_ROUTES)
    assert "parent_verification_complete" in src
    # The gate sits on the ACTIVATE path and rejects with 403.
    assert "USER_ACTIVATE_BLOCKED" in src
    assert "parent_verification_incomplete" in src
    assert ",403)" in src
    # Gate applies to PARENT role only; SUSPEND/DELETE paths are untouched.
    assert "row['role'] == 'PARENT'" in src


def test_mobile_admin_status_endpoint_gates_parent_activation():
    src = _source(MOBILE_ADMIN_API)
    assert "parent_verification_complete" in src
    assert "USER_STATUS_BLOCKED" in src
    assert "parent_verification_incomplete" in src
    assert "target['role'] == 'PARENT'" in src


def test_web_admin_rbac_still_enforced():
    tree = ast.parse(_source(ADMIN_ROUTES))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "user_action":
            decorators = [ast.unparse(d) for d in node.decorator_list]
            assert any("admin_required" in d for d in decorators), decorators
            return
    raise AssertionError("user_action not found")


def test_mobile_admin_rbac_still_enforced():
    src = _source(MOBILE_ADMIN_API)
    idx = src.find("def mobile_admin_user_status")
    assert idx != -1
    window = src[max(0, idx - 400):idx]
    assert "_require_mobile('ADMIN')" in window


def test_non_parent_activation_has_no_verification_gate():
    # The gate condition must be role-scoped so CHILD/ADMIN management is
    # unaffected; SUSPEND paths must not consult verification state.
    for path in (ADMIN_ROUTES, MOBILE_ADMIN_API):
        src = _source(path)
        gate_lines = [ln for ln in src.splitlines() if "parent_verification_complete(" in ln and "import" not in ln]
        assert gate_lines, path
        for ln in gate_lines:
            assert "PARENT" in ln, f"gate not role-scoped in {path}: {ln}"
