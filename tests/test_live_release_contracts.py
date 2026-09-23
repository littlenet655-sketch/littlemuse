from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_live_release_warms_gpu_models_before_strict_preflight():
    workflow = (ROOT / ".github/workflows/deploy-modal.yml").read_text(encoding="utf-8")
    preflight = "Run DB, AI, Presidio, mail, R2 and BASE_URL preflight"
    warmup = "Warm and validate every locked-scope AI model"
    assert preflight in workflow
    assert warmup in workflow
    # Modal GPU cold starts can legitimately exceed the web health probe's first
    # attempt. Validate/warm the complete model set first, then require the full
    # dependency preflight to pass fail-closed.
    assert workflow.index(warmup) < workflow.index(preflight)


def test_modal_docs_name_every_live_web_dependency_key():
    docs = (ROOT / "MODAL_DEPLOYMENT.md").read_text(encoding="utf-8")
    required = [
        "MODAL_TOKEN_ID",
        "MODAL_TOKEN_SECRET",
        "DATABASE_URL",
        "SECRET_KEY",
        "AI_SERVICE_URL",
        "AI_SHARED_SECRET",
        "BASE_URL",
        "R2_ACCOUNT_ID",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "R2_BUCKET",
        "RESEND_API_KEY",
        "RESEND_FROM_EMAIL",
        "RESEND_FROM_NAME",
    ]
    for key in required:
        assert key in docs, key


def test_modal_docs_require_verified_resend_without_legacy_fallbacks():
    docs = (ROOT / "MODAL_DEPLOYMENT.md").read_text(encoding="utf-8")
    assert "RESEND_API_KEY" in docs
    assert "RESEND_FROM_EMAIL" in docs
    assert "RESEND_FROM_NAME" in docs
    assert "SMTP_USER" not in docs
    assert "MAIL_EMAIL" not in docs
