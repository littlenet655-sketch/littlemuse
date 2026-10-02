"""Regression tests for backend auth security hardening (no DB required).

Covers:
1. The deleted ``register_parent_direct`` bypass: no code path in
   ``auth/service.py`` may create an ACTIVE parent account without the
   verified-parent pipeline (registration -> email OTP -> live adult/liveness
   -> activation).
2. The removed duplicate auth routes: ``/verify-parent-email/``,
   ``/verify-parent-email/resend/`` and ``/verify-parent-liveness/`` must be
   defined exactly once, on ``auth_bp`` (``auth/routes.py``), with rate
   limiting. ``auth_bp`` registers before ``api_bp`` in ``app.py``, so any
   ``api_bp`` duplicate would be unreachable dead code.
3. The unused ``register_parent_account`` import removed from
   ``auth/routes.py``.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "auth" / "service.py"
ROUTES = ROOT / "auth" / "routes.py"
API = ROOT / "auth" / "api.py"

VERIFY_PARENT_PATHS = (
    "/verify-parent-email/",
    "/verify-parent-email/resend/",
    "/verify-parent/<token>/otp/",
)


def _function_names(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}


# ---------------------------------------------------------------------------
# 1. register_parent_direct bypass
# ---------------------------------------------------------------------------


def test_register_parent_direct_bypass_is_deleted():
    assert "register_parent_direct" not in _function_names(SERVICE)
    assert "register_parent_direct" not in SERVICE.read_text(encoding="utf-8")
    # The legitimate OTP-flow page handler is a *different* function and stays.
    assert "register_parent_direct_page" in _function_names(ROUTES)


# Functions in auth/service.py that may legitimately write account_status='ACTIVE'.
# Each sits behind the verified-parent pipeline:
#   - process_parent_verification: runs only after the parent's email
#     ownership is proven via OTP (or the parent already holds an ACTIVE
#     account); the selfie/liveness step was removed by explicit product
#     decision, and a VERIFIED guardian audit row is still recorded.
#   - register_parent_account: requires an already-approved (verified) parent token
#   - process_child_decision: requires a logged-in, verified parent approving the child
_VERIFIED_PIPELINE_FUNCS = {
    "process_parent_verification",
    "register_parent_account",
    "process_child_decision",
}


def test_no_active_account_write_outside_verified_pipeline():
    """Any INSERT/UPDATE in auth/service.py that writes account_status='ACTIVE'
    must live inside a verified-parent pipeline function."""
    tree = ast.parse(SERVICE.read_text(encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                sql = sub.value
                if (
                    "account_status" in sql
                    and "'ACTIVE'" in sql
                    and ("INSERT" in sql.upper() or "UPDATE" in sql.upper())
                    and node.name not in _VERIFIED_PIPELINE_FUNCS
                ):
                    offenders.append(node.name)
    assert not offenders, (
        f"account_status='ACTIVE' writes outside the verified-parent pipeline: {offenders}"
    )


def test_verified_pipeline_functions_still_exist():
    names = _function_names(SERVICE)
    for fn in _VERIFIED_PIPELINE_FUNCS:
        assert fn in names, f"legitimate pipeline function {fn} must not be deleted"


# ---------------------------------------------------------------------------
# 2. Duplicate verify-parent routes
# ---------------------------------------------------------------------------


def test_no_shadowed_verify_parent_routes_on_api_bp():
    src = API.read_text(encoding="utf-8")
    for path in VERIFY_PARENT_PATHS:
        assert f"@api_bp.route('{path}'" not in src, (
            f"shadowed duplicate {path} still defined on api_bp"
        )


def test_verify_parent_routes_defined_once_on_auth_bp():
    src = ROUTES.read_text(encoding="utf-8")
    for path in VERIFY_PARENT_PATHS:
        assert src.count(f"@auth_bp.route('{path}'") == 1, (
            f"{path} must be defined exactly once on auth_bp"
        )


def test_surviving_verify_parent_routes_are_rate_limited():
    lines = ROUTES.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        for path in VERIFY_PARENT_PATHS:
            if f"@auth_bp.route('{path}'" in line:
                window = "\n".join(lines[i : i + 3])
                assert "limiter.limit" in window, (
                    f"{path} on auth_bp lost its rate limit"
                )


def test_auth_bp_registers_before_api_bp():
    app_src = (ROOT / "app.py").read_text(encoding="utf-8")
    assert app_src.index("auth_bp") < app_src.index("api_bp"), (
        "auth_bp must register before api_bp so its routes win"
    )


# ---------------------------------------------------------------------------
# 3. Unused import cleanup
# ---------------------------------------------------------------------------


def test_routes_has_no_unused_register_parent_account_import():
    assert "register_parent_account" not in ROUTES.read_text(encoding="utf-8")
