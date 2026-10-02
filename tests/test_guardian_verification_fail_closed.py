"""Guardian verification fail-closed contracts (post face-removal).

Parent face/selfie/liveness verification was removed by explicit product
decision. The token guardian flow now fails closed on:
  - missing/invalid verification token,
  - missing guardian consent,
  - missing guardian name,
  - under-18 date-of-birth declaration,
  - missing/short password for a brand-new parent account,
and it never accepts or requires a selfie.
"""
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_token_guardian_flow_requires_consent_name_and_adult_dob():
    src = (ROOT / "auth/service.py").read_text(encoding="utf-8")
    # ensure_token_parent_pending + process_parent_verification share the
    # validator; all three gates must be present.
    assert 'You must confirm that you are the child\'s legal adult parent or guardian.' in src
    assert 'Please provide the parent or guardian full name.' in src
    assert 'Adult verification failed: Parent must be 18 years of age or older.' in src
    assert 'datetime.strptime(dob, "%Y-%m-%d")' in src


def test_token_guardian_flow_has_no_selfie_or_liveness_step():
    service = (ROOT / "auth/service.py").read_text(encoding="utf-8")
    routes = (ROOT / "auth/routes.py").read_text(encoding="utf-8")
    assert 'selfie_bytes' not in service
    assert 'verify_adult_face' not in service
    assert 'verify_liveness' not in service
    assert 'verify_face_match' not in service
    assert 'selfie_data' not in routes
    assert 'LITTLENET_ALLOW_MOCK_IDENTITY' not in service


def test_token_guardian_flow_records_email_otp_audit_row():
    service = (ROOT / "auth/service.py").read_text(encoding="utf-8")
    # The VERIFIED audit row (authoritative for the DB trigger and the admin
    # gate) is still written, with EMAIL_OTP as the provider.
    assert "'EMAIL_OTP', 'VERIFIED'," in service
    assert "verification_status='VERIFIED'" in service
    # Face/liveness evidence columns are gone from the audit insert.
    assert 'liveness_status' not in service
    assert 'face_match_status' not in service


def test_new_token_parent_is_created_pending_and_activated_only_after_otp():
    service = (ROOT / "auth/service.py").read_text(encoding="utf-8")
    # ensure_token_parent_pending must never activate directly.
    pending_fn = service[service.index("def ensure_token_parent_pending"):]
    pending_fn = pending_fn[:pending_fn.index("def process_parent_verification")]
    assert "'PENDING_APPROVAL'" in pending_fn
    assert "account_status='ACTIVE'" not in pending_fn
    # The OTP step route verifies the code before process_parent_verification.
    routes = (ROOT / "auth/routes.py").read_text(encoding="utf-8")
    assert "@auth_bp.route('/verify-parent/<token>/otp/'" in routes
    assert "verify_parent_email_otp(parent_id" in routes
