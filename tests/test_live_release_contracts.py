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


def test_release_preflight_rejects_stale_ai_endpoint_or_secret_drift():
    web = (ROOT / "modal_web.py").read_text(encoding="utf-8")
    ai = (ROOT / "modal_ai.py").read_text(encoding="utf-8")
    deploy = (ROOT / ".github/workflows/deploy-modal.yml").read_text(encoding="utf-8")
    assert "ai_service_url_matches_expected" in web
    assert "LittleMuse AI shared secret is missing" in ai
    assert "Verify web/AI release identity and shared secret parity without GPU" in deploy
    assert "AI_SHARED_SECRET mismatch between AI and web release secrets" in deploy


def test_web_only_deploy_cannot_bypass_release_identity_or_database_gates():
    workflow = (ROOT / ".github/workflows/deploy-web-only.yml").read_text(encoding="utf-8")
    secret = "modal run modal_web.py --secret-preflight"
    status = "modal run modal_web.py --migration-status-check"
    current = "modal run modal_web.py --require-db-current"
    deploy = "modal deploy modal_web.py"
    assert secret in workflow
    assert status in workflow and current in workflow
    assert workflow.index(secret) < workflow.index(status) < workflow.index(current) < workflow.index(deploy)
    assert "LITTLENET_AI_SECRET: littlemuse-ai-secrets" in workflow
    assert "LITTLENET_R2_SECRET: littlenet-r2" in workflow


def test_local_apk_build_has_no_legacy_backend_fallback_and_checks_identity():
    workflow = (ROOT / ".github/workflows/build-local-apk.yml").read_text(encoding="utf-8")
    assert "netlittle2--littlenet-web-web.modal.run" not in workflow
    assert "EXPO_PUBLIC_API_BASE_URL: ${{ vars.LITTLENET_LIVE_URL }}" in workflow
    assert "akshu1245s-team" in workflow
    assert "c4ce834d-fd50-4504-a311-820c3372b6dc" in workflow
    assert "Mobile API identity mismatch" in workflow


def test_release_utilities_use_configurable_current_resource_names():
    probe = (ROOT / "tools/live_release_media_probe.py").read_text(encoding="utf-8")
    stage = (ROOT / "tools/stage_model_volume.py").read_text(encoding="utf-8")
    assert 'LITTLENET_WEB_SECRET", "littlemuse-web-secrets"' in probe
    assert 'LITTLENET_MODEL_CACHE_VOLUME", "littlenet-model-cache"' in stage


def test_live_media_probe_requires_explicit_fixture_accounts():
    probe = (ROOT / "tools/live_release_media_probe.py").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/live-media-probe.yml").read_text(encoding="utf-8")
    assert "child_a = 2" not in probe
    assert "child_b = 3" not in probe
    assert "LITTLENET_RELEASE_PROBE_CHILD_A" in probe
    assert "LITTLENET_RELEASE_PROBE_CHILD_B" in probe
    assert "vars.LITTLENET_RELEASE_PROBE_CHILD_A" in workflow
    assert "vars.LITTLENET_RELEASE_PROBE_CHILD_B" in workflow
