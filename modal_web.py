"""Modal deployment for LittleNet's Flask/Jinja web application.

PostgreSQL remains external (Neon/etc.). Private media is stored in R2. Heavy
AI stays in littlenet-ai and is invoked only for real moderation work.
"""
from pathlib import Path
import hashlib
import json
import os
import subprocess

import modal

ROOT = Path(__file__).resolve().parent
app = modal.App("littlenet-web")
uploads = modal.Volume.from_name("littlenet-uploads", create_if_missing=True)
# Private trained-moderation checkpoints (littlenet_core_safety_v2.pth,
# littlenet_weapons_violence_v3.pth, littlenet_text_safety/). Mounted on the
# media workers so the trained 18+/weapons/violence ensemble runs inside the
# quarantine worker instead of only the legacy detector stack. When the
# checkpoints are absent, safety.littlenet_trained_image.available() stays
# False and moderation fails closed to the legacy stack — mounting the
# volume never weakens moderation.
model_cache = modal.Volume.from_name("littlenet-model-cache", create_if_missing=True)
web_secret = modal.Secret.from_name(
    "littlenet-web-secrets",
    required_keys=["DATABASE_URL", "SECRET_KEY", "AI_SERVICE_URL", "AI_SHARED_SECRET"],
)
email_secret = modal.Secret.from_name("littlenet-email")
r2_secret = modal.Secret.from_name(
    "littlenet-r2",
    required_keys=["R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"],
)

web_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "curl", "ca-certificates")
    .run_commands(
        "curl -fsSL -o /usr/local/bin/dbmate https://github.com/amacneil/dbmate/releases/download/v2.34.1/dbmate-linux-amd64",
        "chmod +x /usr/local/bin/dbmate",
        "dbmate --version",
    )
    .pip_install_from_requirements(str(ROOT / "requirements-core.txt"))
    .pip_install("presidio-analyzer>=2.2,<3", "spacy>=3.8,<4")
    .run_commands("python -m spacy download en_core_web_sm")
    .workdir("/root/littlenet")
    .env(
        {
            "COOKIE_SECURE": "1",
            "LITTLENET_DEVICE": "cpu",
            "LITTLENET_ENABLE_PRESIDIO": "1",
            "LITTLENET_PRESIDIO_SPACY_MODEL": "en_core_web_sm",
            "LITTLENET_RESEND_FROM_EMAIL": "no-reply@littlenet.in",
            "LITTLENET_RESEND_DOMAIN_VERIFIED": "1",
            "ENABLE_DEV_OTP": "0",
            "STRICT_PRODUCTION_PREFLIGHT": "1",
            # LITTLENET_USE_MODAL_QUEUE was a legacy name. The job queue reads
            # JOB_QUEUE_PROVIDER (see services/job_queue.py); nothing reads the
            # old name, so it is intentionally not set here.
            # Ordinary image moderation runs on a scale-to-zero CPU function.
            # GPU fallback is deliberately off so a transient CPU issue cannot
            # silently burn T4 credit; the moderation pipeline fails closed.
            "LITTLENET_USE_MODAL_IMAGE_CPU": "1",
            "LITTLENET_ALLOW_IMAGE_GPU_FALLBACK": "0",
            "LITTLENET_USE_MODAL_TEXT_CPU": "1",
            "LITTLENET_ALLOW_TEXT_GPU_FALLBACK": "0",
            "LITTLENET_IMAGE_MODERATION_MAX_PX": "1600",
            # Bumped because the trained V2/V3 image ensemble changes image evidence.
            "LITTLENET_MODERATION_CACHE_VERSION": "2026-09-20-v2-trained-image",
            "LITTLENET_MODERATION_CACHE_TTL_DAYS": "30",
            "DBMATE_MIGRATIONS_DIR": "/root/littlenet/db/migrations",
            "DBMATE_NO_DUMP_SCHEMA": "true",
            "DBMATE_STRICT": "true",
            "LITTLENET_DEPLOY_VERSION": "14",
        }
    )
    .add_local_dir(
        str(ROOT),
        remote_path="/root/littlenet",
        ignore=[
            ".git/**", ".pytest_cache/**", "**/__pycache__/**", "uploads/**",
            "android/**", "tools/gradle-8.9/**", "node_modules/**", "mobile_app/**",
            ".agent/**", ".agents/**", "agent/**", ".claude/**", ".cursor/**",
            "*.db", "*.zip", "*.apk", ".env",
        ],
        copy=True,
    )
)
secret_preflight_image = modal.Image.debian_slim(python_version="3.11")


WEB_MIN_CONTAINERS = int(os.getenv("MODAL_WEB_MIN_CONTAINERS", "0"))
WEB_MAX_CONTAINERS = int(os.getenv("MODAL_WEB_MAX_CONTAINERS", "1"))
WEB_CPU = float(os.getenv("MODAL_WEB_CPU", "2.0"))
WEB_MEMORY = int(os.getenv("MODAL_WEB_MEMORY", "2048"))
WEB_SCALEDOWN_WINDOW = int(os.getenv("MODAL_WEB_SCALEDOWN_WINDOW", "120"))


@app.function(
    image=web_image,
    cpu=WEB_CPU,
    memory=WEB_MEMORY,
    secrets=[web_secret, email_secret, r2_secret],
    volumes={"/root/littlenet/uploads": uploads},
    timeout=300,
    startup_timeout=120,
    scaledown_window=WEB_SCALEDOWN_WINDOW,
    min_containers=WEB_MIN_CONTAINERS,
    max_containers=WEB_MAX_CONTAINERS,
)
@modal.wsgi_app()
def web():
    """Expose the complete LittleNet Flask app on Modal."""
    os.chdir("/root/littlenet")
    Path("uploads").mkdir(parents=True, exist_ok=True)
    from flask import request
    from app import create_app

    flask_app = create_app()

    try:
        from services.media_outbox import reconcile_pending_deletes
        cleanup = reconcile_pending_deletes(100)
        if cleanup.get("failed"):
            flask_app.logger.warning("Pending R2 delete reconciliation: %s", cleanup)
    except Exception:
        flask_app.logger.info("Media delete outbox is not ready during web startup", exc_info=True)

    @flask_app.after_request
    def persist_upload_changes(response):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.files:
            try:
                uploads.commit()
            except Exception:
                flask_app.logger.exception("Modal uploads Volume commit failed")
        return response

    return flask_app


@app.function(
    image=secret_preflight_image,
    secrets=[web_secret],
    timeout=60,
    min_containers=0,
    max_containers=1,
)
def web_secret_preflight():
    """Read only the web secret for a non-disclosing release comparison."""
    value = str(os.environ.get("AI_SHARED_SECRET") or "")
    if not value:
        return {"present": False, "fingerprint": None}
    return {
        "present": True,
        "fingerprint": hashlib.sha256(value.encode("utf-8")).hexdigest(),
    }


@app.function(
    image=web_image,
    cpu=1.0,
    memory=2048,
    secrets=[web_secret, email_secret, r2_secret],
    volumes={"/cache": model_cache},
    timeout=600,
    scaledown_window=int(os.getenv("MODAL_IMAGE_WORKER_SCALEDOWN_WINDOW", "20")),
    min_containers=0,
    max_containers=1,
)
def process_image_job_background(
    post_id: int,
    child_id: int,
    object_key: str,
    kind: str = "post",
    lease_token: str | None = None,
):
    """Lower-cost orchestration worker dedicated to image uploads."""
    os.chdir("/root/littlenet")
    from services.media_processor import process_media_job
    return process_media_job(
        int(post_id),
        int(child_id),
        str(object_key),
        str(kind),
        lease_token=lease_token,
    )


@app.function(
    image=web_image,
    cpu=2.0,
    memory=4096,
    secrets=[web_secret, email_secret, r2_secret],
    volumes={"/cache": model_cache},
    timeout=900,
    scaledown_window=int(os.getenv("MODAL_MEDIA_WORKER_SCALEDOWN_WINDOW", "30")),
    min_containers=0,
    max_containers=1,
)
def process_media_job_background(post_id: int, child_id: int, object_key: str, kind: str = "post", lease_token: str | None = None):
    """CPU orchestration worker for asynchronous media processing.

    The worker downloads/sanitizes media and updates Neon/R2. Ordinary images
    are delegated to the scale-to-zero CPU moderation function. GPU inference is
    reserved for workloads that still require it (for example video paths).
    """
    os.chdir("/root/littlenet")
    from services.media_processor import process_media_job
    return process_media_job(int(post_id), int(child_id), str(object_key), str(kind), lease_token=lease_token)


@app.function(
    image=web_image,
    secrets=[web_secret, r2_secret],
    timeout=1800,
    min_containers=0,
    max_containers=1,
)
def curated_poster_backfill(apply: bool = False, limit: int = 250):
    """Run the curated poster repair inside Modal with production DB/R2 secrets.

    Dry-run is the default. The apply path modifies only poster/thumbnail
    references after a successful poster upload.
    """
    os.chdir("/root/littlenet")
    from tools.backfill_curated_video_posters import run
    return run(apply=bool(apply), limit=int(limit))


@app.function(image=web_image, secrets=[web_secret], timeout=300)
def init_database():
    os.chdir("/root/littlenet")
    subprocess.run(["python", "tools/init_db.py"], check=True)
    subprocess.run(
        ["dbmate", "--no-dump-schema", "--migrations-dir", "db/migrations", "up"],
        check=True,
        env=os.environ.copy(),
    )
    return {"ok": True, "migration_engine": "dbmate", "legacy_bootstrap": True}


@app.function(image=web_image, secrets=[web_secret], timeout=120)
def seed_quizzes():
    os.chdir("/root/littlenet")
    subprocess.run(["python", "tools/seed_quizzes.py"], check=True)
    return {"ok": True}


def _mail_healthcheck(strict_production: bool = False):
    from mailg.send_email import get_mail_status, validate_resend_production
    if strict_production:
        return validate_resend_production()

    status = get_mail_status()
    if status.get("provider") == "resend":
        return {
            "ok": True,
            "configured": True,
            "provider": "resend",
            "mail_mode": status.get("mail_mode"),
            "from": status.get("from_email"),
            "is_production_ready": status.get("is_production_ready", False),
        }
    return {"ok": False, "configured": False, "mail_mode": "not_configured", "is_production_ready": False}


@app.function(image=web_image, secrets=[web_secret, email_secret, r2_secret], timeout=180)
def web_preflight(deep_ai_probe: bool = False):
    """Validate live dependencies without waking the GPU unless explicitly requested."""
    os.chdir("/root/littlenet")
    from config import Config
    from database.connection import fetch_one
    from safety.presidio_adapter import analyze_pii
    from services.object_storage import healthcheck as r2_healthcheck
    from services.media_outbox import reconcile_pending_deletes
    from services.job_queue import validate_job_queue_config
    from services.video_delivery import video_delivery_healthcheck

    db = fetch_one("SELECT 1 ok")
    schema = dict(fetch_one("""
        SELECT
          to_regclass('public.users')::text AS users,
          to_regclass('public.child_profiles')::text AS child_profiles,
          to_regclass('public.posts')::text AS posts,
          to_regclass('public.comments')::text AS comments,
          to_regclass('public.followers')::text AS followers,
          to_regclass('public.quizzes')::text AS quizzes,
          to_regclass('public.media_delete_outbox')::text AS media_delete_outbox,
          to_regclass('public.moderation_signal_cache')::text AS moderation_signal_cache,
          to_regclass('public.recommendation_signals')::text AS recommendation_signals,
          to_regclass('public.feed_sessions')::text AS feed_sessions
    """) or {})
    required_tables = (
        "users", "child_profiles", "posts", "comments", "followers", "quizzes",
        "media_delete_outbox", "moderation_signal_cache", "recommendation_signals", "feed_sessions",
    )
    schema_ok = all(schema.get(name) for name in required_tables)
    quiz_count = 0
    if schema_ok:
        quiz_row = fetch_one("SELECT COUNT(*)::int n FROM quizzes") or {}
        quiz_count = int(quiz_row.get("n") or 0)

    ai_configured = bool(str(Config.AI_SERVICE_URL or "").startswith("https://") and str(Config.AI_SHARED_SECRET or ""))
    ai = {"ok": ai_configured, "mode": "configured_not_probed"}
    if deep_ai_probe and ai_configured:
        from safety.remote_client import health
        ai = health()
        ai["mode"] = "deep_probe"

    try:
        queue_provider = validate_job_queue_config(is_production=True)
        queue = {"ok": queue_provider == "modal", "provider": queue_provider}
    except Exception as exc:
        queue = {"ok": False, "provider": None, "error": f"{type(exc).__name__}: {exc}"}

    pii = analyze_pii("test@example.com")
    pii_ok = bool(pii.get("available") and "EMAIL_ADDRESS" in pii.get("categories", []))

    base_url = str(Config.BASE_URL or "").rstrip("/")
    public_base_url = bool(
        base_url.startswith("https://")
        and "127.0.0.1" not in base_url
        and "localhost" not in base_url
        and "YOUR-LITTLENET-BACKEND" not in base_url
        and "placeholder.invalid" not in base_url
    )
    # Release validation must prove the real Resend credential and verified
    # LittleNet sender. It must never pass through SMTP or a sandbox sender.
    mail = _mail_healthcheck(strict_production=True)
    r2 = r2_healthcheck()
    video_delivery = video_delivery_healthcheck()
    if r2.get("ok") and schema.get("media_delete_outbox"):
        try:
            media_outbox = reconcile_pending_deletes(100)
            media_outbox["ok"] = media_outbox.get("failed", 0) == 0
        except Exception as exc:
            media_outbox = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    else:
        media_outbox = {"ok": False, "error": "R2 or media_delete_outbox unavailable"}

    report = {
        "database": bool(db and db["ok"] == 1),
        "database_schema": {"ok": schema_ok, "tables": schema, "quiz_count": quiz_count},
        "ai": ai,
        "job_queue": queue,
        "presidio": pii_ok,
        "base_url": {"ok": public_base_url, "value": base_url},
        "mail": mail,
        "r2": r2,
        "video_delivery": video_delivery,
        "media_delete_outbox": media_outbox,
    }
    strict_mail = os.getenv("STRICT_PRODUCTION_PREFLIGHT", "").strip().lower() in {"1", "true", "yes"}
    mail_passes = mail.get("is_production_ready") if strict_mail else mail.get("ok")

    report["ok"] = bool(
        report["database"] and schema_ok and quiz_count > 0 and ai.get("ok")
        and queue.get("ok") and pii_ok and public_base_url
        and mail_passes and r2.get("ok") and video_delivery.get("ok") and media_outbox.get("ok")
    )
    return json.loads(json.dumps(report, default=str))


@app.local_entrypoint()
def main(
    init_db: bool = False,
    seed: bool = False,
    preflight: bool = False,
    reconcile_media: bool = False,
    backfill_curated_posters: bool = False,
    apply_curated_posters: bool = False,
    curated_poster_limit: int = 250,
    deep_ai_probe: bool = False,
    secret_preflight: bool = False,
):
    """Release helper. Deep AI probing is opt-in because it wakes the T4."""
    if secret_preflight:
        report = web_secret_preflight.remote()
        print(f"secret-preflight {json.dumps(report, sort_keys=True)}")
        return
    if init_db:
        print("database", init_database.remote())
    if seed:
        print("quizzes", seed_quizzes.remote())
    if reconcile_media:
        report = web_preflight.remote(deep_ai_probe=False)
        print("media reconciliation", report.get("media_delete_outbox"))
        if not report.get("media_delete_outbox", {}).get("ok"):
            raise RuntimeError(f"LittleNet media reconciliation failed: {report}")
    if backfill_curated_posters or apply_curated_posters:
        report = curated_poster_backfill.remote(
            apply=bool(apply_curated_posters),
            limit=int(curated_poster_limit),
        )
        print("curated poster backfill", json.dumps(report, default=str))
        if report.get("failures"):
            raise RuntimeError(f"Curated poster backfill reported failures: {report}")
    if preflight:
        report = web_preflight.remote(deep_ai_probe=deep_ai_probe)
        print("preflight", report)
        if not report.get("ok"):
            raise RuntimeError(f"LittleNet web preflight failed: {report}")
