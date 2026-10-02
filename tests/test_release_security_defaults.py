from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_parent_otp_is_never_exposed_by_default_or_in_production():
    config = source("config.py")
    otp = source("auth/parent_email_otp.py")
    assert 'os.getenv("ENABLE_DEV_OTP", "0")' in config
    assert "ENABLE_DEV_OTP must never be enabled in production" in config
    assert "Config.ENABLE_DEV_OTP and not Config._PRODUCTION" in otp
    assert "os.getenv('ENABLE_DEV_OTP', '1')" not in otp


def test_release_client_does_not_consume_server_returned_otp():
    screen = source("mobile_app/src/screens/ParentOnboarding.tsx")
    assert "devCode: __DEV__ ? response.dev_code : undefined" in screen
    assert "if (__DEV__ && response.dev_code)" in screen


def test_guardian_certification_requires_affirmative_action():
    screen = source("mobile_app/src/screens/ParentOnboarding.tsx")
    assert "useState(false)" in screen
    assert "if (!guardianAgreed)" in screen

def test_production_mode_and_base_url_fail_closed_in_source():
    config = source("config.py")
    modal_web = source("modal_web.py")
    assert 'os.getenv("LITTLENET_ENV", "")' in config
    assert '_ENVIRONMENT in {"production", "prod"}' in config
    assert "Production BASE_URL must be an explicit public HTTPS URL" in config
    assert '"BASE_URL"' in modal_web
    assert '"LITTLENET_ENV": "production"' in modal_web


def test_browser_policy_does_not_allow_eval_or_microphone():
    app = source("app.py")
    assert "'unsafe-eval'" not in app
    assert "'wasm-unsafe-eval'" not in app
    assert "microphone=()" in app
    assert "object-src 'none'" in app


def test_release_builds_bind_to_validated_backend_instead_of_eas_hardcode():
    eas = source("mobile_app/eas.json")
    remote = source(".github/workflows/release-mobile.yml")
    local = source(".github/workflows/build-local-apk.yml")
    assert "EXPO_PUBLIC_API_BASE_URL" not in eas
    assert "LITTLENET_LIVE_URL" in remote
    assert "EXPO_PUBLIC_API_BASE_URL: process.env.LIVE_URL" in remote
    assert "/api/mobile/v1/health" in remote
    assert "LITTLENET_LIVE_URL" in local
    assert "/api/mobile/v1/health" in local


def test_mobile_camera_copy_contains_no_face_auth_claim():
    app_json = source("mobile_app/app.json").lower()
    assert "face check" not in app_json
    assert "face authentication" not in app_json
    assert "microphonepermission" in app_json

