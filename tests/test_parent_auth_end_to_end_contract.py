"""End-to-end contract: auth is email-OTP/password-based (no face/liveness).

All face/biometric verification was removed by explicit product decision on
2026-09-22: the web ``/face-login/`` pages and routes, the mobile face
endpoints, ``safety/face_service.py``, the face tables, and the parent
liveness template/MediaPipe JS are all gone. Children log in with passwords.
"""
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_parent_registration_has_no_arithmetic_guardian_challenge():
    template = (ROOT / 'auth/templates/parent_register_direct.html').read_text(encoding='utf-8')
    otp = (ROOT / 'auth/parent_email_otp.py').read_text(encoding='utf-8')
    routes = (ROOT / 'auth/routes.py').read_text(encoding='utf-8')

    assert 'Guardian Verification Challenge' not in template
    assert 'adult_challenge_expected' not in template
    assert 'adult_challenge_answer' not in template
    assert 'adult_challenge_expected' not in otp
    assert 'adult_challenge_answer' not in otp
    assert 'challenge_q=' not in routes
    assert 'challenge_expected=' not in routes


def test_parent_liveness_assets_are_removed():
    # The parent liveness page, its MediaPipe JS, and the route are deleted.
    assert not (ROOT / 'static/js/parent_liveness_mediapipe.js').exists()
    assert not (ROOT / 'auth/templates/parent_liveness_verify.html').exists()

    routes = (ROOT / 'auth/routes.py').read_text(encoding='utf-8')
    assert 'verify_parent_liveness_page' not in routes
    assert "verify-parent-liveness" not in routes
    assert 'parent_liveness_verify.html' not in routes
    assert 'parent_liveness_mediapipe' not in routes

    service = (ROOT / 'auth/service.py').read_text(encoding='utf-8')
    assert 'verify_adult_face' not in service

    # The shared face_service module is deleted entirely (2026-09-22).
    assert not (ROOT / 'safety/face_service.py').exists()


def test_face_login_is_fully_removed():
    routes = (ROOT / 'auth/routes.py').read_text(encoding='utf-8')
    login = (ROOT / 'auth/templates/login.html').read_text(encoding='utf-8')

    # The face login templates are deleted.
    assert not (ROOT / 'auth/templates/face_login.html').exists()
    assert not (ROOT / 'auth/templates/face_enroll.html').exists()
    # No face routes or links remain.
    assert 'face-login' not in routes
    assert 'face_login' not in routes
    assert 'face-enroll' not in routes
    assert 'Face ID' not in login
    assert 'face_login' not in login


def test_parent_activation_is_email_otp_only():
    routes = (ROOT / 'auth/routes.py').read_text(encoding='utf-8')
    otp = (ROOT / 'auth/parent_email_otp.py').read_text(encoding='utf-8')

    # Standalone registration: OTP success activates the account directly.
    assert "UPDATE users SET account_status='ACTIVE'" in routes
    assert "UPDATE users SET account_status='ACTIVE'" not in otp
    # Token guardian flow: OTP step route exists, selfie step does not.
    assert "@auth_bp.route('/verify-parent/<token>/otp/'" in routes
    assert 'ensure_token_parent_pending' in routes
    assert 'selfie_data' not in routes
    assert 'selfie_bytes' not in (ROOT / 'auth/service.py').read_text(encoding='utf-8')


def test_live_deploy_tracks_auth_changes():
    workflow = (ROOT / '.github/workflows/deploy-modal.yml').read_text(encoding='utf-8')
    for required_path in (
        "- 'auth/**'",
        "- 'mailg/**'",
    ):
        assert required_path in workflow
    # The deleted face_service.py and parent-liveness JS must not be active
    # tracked deploy paths anymore (only stale commented-out lines may remain).
    active_lines = [ln for ln in workflow.splitlines() if not ln.strip().startswith('#')]
    assert not any('face_service' in ln for ln in active_lines)
    assert not any('parent_liveness_mediapipe' in ln for ln in active_lines)
