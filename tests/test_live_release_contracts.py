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


def test_release_identity_is_single_source_of_truth():
    import json
    app = json.loads((ROOT / "mobile_app/app.json").read_text(encoding="utf-8"))["expo"]
    assert app["owner"] == "akshu1245s-team"
    assert app["extra"]["eas"]["projectId"] == "c4ce834d-fd50-4504-a311-820c3372b6dc"
    assert app["android"]["package"] == "com.littlenet.app"
    workflow = (ROOT / ".github/workflows/release-mobile.yml").read_text(encoding="utf-8")
    assert "akshu1245s-team" in workflow
    assert "c4ce834d-fd50-4504-a311-820c3372b6dc" in workflow


def test_modal_app_names_and_release_workflow_cannot_drift():
    ai = (ROOT / "modal_ai.py").read_text(encoding="utf-8")
    web = (ROOT / "modal_web.py").read_text(encoding="utf-8")
    deploy = (ROOT / ".github/workflows/deploy-modal.yml").read_text(encoding="utf-8")
    assert 'LITTLENET_AI_MODAL_APP", "littlemuse-ai"' in ai
    assert 'LITTLENET_WEB_MODAL_APP", "littlemuse-web"' in web
    assert "LITTLENET_AI_MODAL_APP: littlemuse-ai" in deploy
    assert "LITTLENET_WEB_MODAL_APP: littlemuse-web" in deploy


def test_retained_database_migration_is_guarded_before_web_deploy():
    deploy = (ROOT / ".github/workflows/deploy-modal.yml").read_text(encoding="utf-8")
    status = "modal run modal_web.py --migration-status-check"
    migrate = "modal run modal_web.py --migrate-db"
    current = "modal run modal_web.py --require-db-current"
    web_deploy = "modal deploy modal_web.py"
    assert status in deploy and migrate in deploy and current in deploy
    assert deploy.index(status) < deploy.index(migrate) < deploy.index(current) < deploy.index(web_deploy)
    assert "Refuse automatic migration" not in deploy
    web = (ROOT / "modal_web.py").read_text(encoding="utf-8")
    assert "schema_migrations_empty" in web
    assert "baseline_schema_missing" in web


def test_video_release_policy_is_bounded_and_fail_safe():
    env = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "LITTLENET_VIDEO_MIN_FRAMES=3" in env
    assert "LITTLENET_VIDEO_MAX_FRAMES=8" in env
    assert "LITTLENET_VIDEO_MAX_AUTO_ALLOW_GAP_SECONDS=12" in env
