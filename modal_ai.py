"""Modal deployment for LittleNet's heavy AI inference service.

Deploy from the project root with:
    modal deploy modal_ai.py

Locked scope: text/image/video moderation.
Standalone audio, voice and story-music moderation are intentionally excluded.
"""
from pathlib import Path
import hashlib
import json
import os
import tempfile

import modal

ROOT = Path(__file__).resolve().parent

app = modal.App("littlenet-ai")
model_cache = modal.Volume.from_name("littlenet-model-cache", create_if_missing=True)
ai_secret = modal.Secret.from_name("littlenet-ai-secrets", required_keys=["AI_SHARED_SECRET"])
web_secret = modal.Secret.from_name("littlenet-web-secrets")
r2_secret = modal.Secret.from_name("littlenet-r2")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "libgl1", "libglib2.0-0", "libgomp1")
    .pip_install(
        "numpy==1.26.4",
        "torch>=2.13,<2.14",
        "torchvision>=0.28,<0.29",
        "transformers>=5.0",  # v5 verified end-to-end with littlenet_text_safety
        "detoxify==0.5.2",
        # Declared dep of detoxify==0.5.2 (sentencepiece>=0.1.94); its
        # multilingual toxicity model's tokenizer. Keep in sync with
        # requirements-text.txt.
        "sentencepiece==0.2.2",
        "nudenet>=3.4,<4",
        "ultralytics>=8.3,<9",
        # Non-headless: libgl1 is apt-installed above, and rapidocr-onnxruntime
        # declares opencv-python (not headless) — one cv2 provider avoids a
        # site-packages collision between the two distributions.
        "opencv-python==4.11.0.86",
        # OCR backend for safety/visual_service.py (default-on, fail-closed).
        # Keep in sync with requirements-core.txt.
        "rapidocr-onnxruntime==1.4.4",
        "scenedetect-headless>=0.7,<0.8",
        "Flask==3.1.3",
        "python-dotenv==1.2.2",
        "Pillow==12.3.0",
        "pypdf==6.16.1",
        "requests==2.33.0",
        "psycopg2-binary==2.9.10",
        "boto3==1.40.17",
        # Explicit: safety/policy_config.py does a top-level `import yaml`
        # on the image/video moderation path (via safety/policy.py and
        # safety/yolo_policy.py). It is only satisfied transitively today
        # (transformers/ultralytics); pin it like requirements-core.txt.
        "PyYAML==6.0.3",
    )
    .workdir("/root/littlenet")
    .env(
        {
            "LITTLENET_AI_SERVER": "1",
            "LITTLENET_DEVICE": "cuda",
            "LITTLENET_MODEL_CACHE": "/cache/models",
            "LITTLENET_ENABLE_TRAINED_IMAGE_ENSEMBLE": "1",
            "LITTLENET_TRAINED_IMAGE_V2_PATH": "/cache/models/littlenet_core_safety_v2.pth",
            "LITTLENET_TRAINED_IMAGE_V3_PATH": "/cache/models/littlenet_weapons_violence_v3.pth",
            # Text model resolves the same way as the image ensemble: the volume
            # path is authoritative. tools/sync_modal_volume.py stages the
            # 541MB littlenet_text_safety/ directory into littlenet-model-cache.
            "LITTLENET_TRAINED_TEXT_PATH": "/cache/models/littlenet_text_safety",
            "LITTLENET_ENABLE_TRAINED_TEXT": "1",
            "HF_HOME": "/cache/huggingface",
            "HF_HUB_CACHE": "/cache/huggingface/hub",
            "TORCH_HOME": "/cache/torch",
            "LITTLENET_DETOXIFY_MODEL": "multilingual",
            # Scene-aware sampling protects short scene changes. The bounded
            # uniform fallback prevents long reels from multiplying GPU work.
            # Cost-bounded video scan: short clips retain <=4s temporal spacing.
            # Long clips stop at 24 frames and fail to REVIEW rather than burning
            # unbounded GPU time to auto-allow them.
            "LITTLENET_VIDEO_SAMPLE_INTERVAL_SECONDS": "4",
            "LITTLENET_VIDEO_MAX_FRAMES": "24",
            # Longer videos remain private for review if this temporal coverage
            # cannot be met within the full-model frame budget.
            "LITTLENET_VIDEO_MAX_AUTO_ALLOW_GAP_SECONDS": "4",
            "LITTLENET_ENABLE_SCENEDETECT": "1",
            "LITTLENET_SCENEDETECT_THRESHOLD": "27",
            "LITTLENET_YOLO_WEIGHTS": "/root/littlenet/yolov8n-oiv7.pt",
            "LITTLENET_YOLO_REVIEW_THRESHOLD": "0.20",
            "LITTLENET_YOLO_BLOCK_THRESHOLD": "0.45",
            "LITTLENET_NUDENET_REVIEW_THRESHOLD": "0.20",
            "LITTLENET_NUDENET_BLOCK_THRESHOLD": "0.45",
            "LITTLENET_FALCONSAI_REVIEW_THRESHOLD": "0.40",
            "LITTLENET_FALCONSAI_BLOCK_THRESHOLD": "0.70",
            "LITTLENET_CLIP_REVIEW_THRESHOLD": "0.40",
            "LITTLENET_CLIP_BLOCK_THRESHOLD": "0.65",
            "LITTLENET_DEPLOY_VERSION": "13",
        }
    )
    .add_local_dir(
        str(ROOT),
        remote_path="/root/littlenet",
        ignore=[
            ".git/**", ".pytest_cache/**", "**/__pycache__/**", "uploads/**",
            "android/**", "android-build/**", "mobile_app/**", "mobile_flutter/**", "datasets/**",
            "test-results/**", "playwright-report/**", "tools/gradle-8.9/**",
            "node_modules/**", ".agent/**", ".agents/**", "agent/**",
            ".claude/**", ".cursor/**", "*.db", "*.zip", "*.apk", ".env",
        ],
        copy=True,
    )
)
secret_preflight_image = modal.Image.debian_slim(python_version="3.11")


def _secret_fingerprint(value: str | None) -> dict[str, object]:
    """Return non-disclosing presence and equality data for a shared secret."""
    normalized = str(value or "")
    if not normalized:
        return {"present": False, "fingerprint": None}
    return {
        "present": True,
        "fingerprint": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
    }


@app.function(
    image=image,
    gpu="T4",
    cpu=4.0,
    memory=8192,
    secrets=[ai_secret, web_secret, r2_secret],
    volumes={"/cache": model_cache},
    timeout=900,
    startup_timeout=900,
    # Scale fully to zero. Keep only a short warm tail so a small demo burst is
    # responsive without paying for minutes of idle GPU after every request.
    scaledown_window=int(os.getenv("MODAL_AI_GPU_SCALEDOWN_WINDOW", "30")),
    min_containers=0,
    max_containers=1,
)
@modal.concurrent(max_inputs=1, target_inputs=1)
@modal.wsgi_app()
def ai_web():
    os.chdir("/root/littlenet")
    Path("/cache/models").mkdir(parents=True, exist_ok=True)
    from ai_server import app as flask_ai_app
    return flask_ai_app


@app.function(
    image=image,
    cpu=4.0,
    memory=8192,
    volumes={"/cache": model_cache},
    timeout=600,
    startup_timeout=900,
    # Images are processed asynchronously. Keep a short CPU warm tail for a
    # burst of posts, then return fully to zero.
    scaledown_window=int(os.getenv("MODAL_AI_IMAGE_CPU_SCALEDOWN_WINDOW", "30")),
    min_containers=0,
    max_containers=1,
)
@modal.concurrent(max_inputs=1, target_inputs=1)
def moderate_image_upload_cpu(
    file_bytes: bytes,
    filename: str = "upload.jpg",
    text: str = "",
    run_text: bool = True,
    run_media: bool = True,
):
    """Run upload image moderation on CPU so ordinary photos never require T4 credit."""
    os.chdir("/root/littlenet")
    Path("/cache/models").mkdir(parents=True, exist_ok=True)
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    os.environ["LITTLENET_AI_SERVER"] = "1"
    os.environ["LITTLENET_DEVICE"] = "cpu"

    path = None
    if run_media:
        suffix = Path(filename or "upload.jpg").suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
            suffix = ".jpg"
        fd, path = tempfile.mkstemp(prefix="littlenet_cpu_image_", suffix=suffix)
        os.close(fd)

    def jsonable(value):
        if isinstance(value, dict):
            return {str(k): jsonable(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [jsonable(v) for v in value]
        if hasattr(value, "item"):
            try:
                return value.item()
            except Exception:
                return str(value)
        return value

    try:
        if run_media:
            with open(path, "wb") as fh:
                fh.write(file_bytes or b"")
            if os.path.getsize(path) <= 0:
                raise ValueError("image_payload_empty")

        text_signals = {}
        media_signals = {}
        if run_text and text:
            from safety.text_service import check_text
            text_signals = check_text(text[:4000])
        if run_media:
            from safety.visual_service import check_image
            media_signals = check_image(path)

        # Persist model downloads only when this workload's cache was first
        # populated. Avoid a Volume commit on every moderation request.
        cache_markers = []
        if run_text:
            cache_markers.append(Path("/cache/.cpu_text_models_ready"))
        if run_media:
            cache_markers.append(Path("/cache/.cpu_image_models_ready"))
        missing_markers = [marker for marker in cache_markers if not marker.exists()]
        if missing_markers:
            try:
                for marker in missing_markers:
                    marker.write_text("ready", encoding="utf-8")
                model_cache.commit()
            except Exception:
                for marker in missing_markers:
                    try:
                        marker.unlink(missing_ok=True)
                    except Exception:
                        pass

        return {
            "ok": True,
            "text_signals": jsonable(text_signals),
            "media_signals": jsonable(media_signals),
            "compute_tier": "cpu",
        }
    finally:
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass


@app.function(
    image=image,
    cpu=2.0,
    memory=4096,
    volumes={"/cache": model_cache},
    timeout=300,
    min_containers=0,
    max_containers=1,
)
def trained_image_preflight():
    """CPU-only verification that the private V2/V3 artifacts are staged and loadable."""
    os.chdir("/root/littlenet")
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    os.environ["LITTLENET_DEVICE"] = "cpu"
    os.environ["LITTLENET_AI_SERVER"] = "1"
    from safety import littlenet_trained_image as trained

    v2, v3 = trained.paths()
    report = {
        "available": trained.available(),
        "v2": {"path": str(v2), "exists": v2.is_file(), "bytes": v2.stat().st_size if v2.is_file() else 0},
        "v3": {"path": str(v3), "exists": v3.is_file(), "bytes": v3.stat().st_size if v3.is_file() else 0},
    }
    if report["available"]:
        try:
            _, v2_ckpt, _, v3_ckpt = trained._models()
            report["v2"]["labels"] = list(v2_ckpt.get("labels") or [])
            report["v3"]["labels"] = list(v3_ckpt.get("labels") or [])
            report["loadable"] = True
        except Exception as exc:
            report["loadable"] = False
            report["error"] = f"{type(exc).__name__}: {exc}"
    else:
        report["loadable"] = False
    return report


#: Exact byte size of the verified models/littlenet_text_safety/model.safetensors
#: artifact. A pointer-sized stub (Git LFS pointers are ~130 bytes) must fail
#: the deploy preflight, not warn.
TRAINED_TEXT_SAFETENSORS_BYTES = 541_351_212


@app.function(
    image=image,
    cpu=2.0,
    memory=8192,
    volumes={"/cache": model_cache},
    timeout=900,
    min_containers=0,
    max_containers=1,
)
def trained_text_preflight():
    """CPU-only verification that the private text classifier is staged and loadable.

    Mirrors trained_image_preflight: the 13-label DistilBERT classifier must
    resolve from the littlenet-model-cache volume, carry the expected artifact
    bytes, and load into a real transformers pipeline.
    """
    os.chdir("/root/littlenet")
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    os.environ["LITTLENET_DEVICE"] = "cpu"
    os.environ["LITTLENET_AI_SERVER"] = "1"
    from safety import littlenet_trained_text as trained

    artifact = trained.path()
    weights = artifact / "model.safetensors"
    report = {
        "available": trained.available(),
        "path": str(artifact),
        "is_dir": artifact.is_dir(),
        "weights_bytes": weights.stat().st_size if weights.is_file() else 0,
        "expected_bytes": TRAINED_TEXT_SAFETENSORS_BYTES,
    }
    report["bytes_ok"] = report["weights_bytes"] == TRAINED_TEXT_SAFETENSORS_BYTES
    if report["available"] and report["bytes_ok"]:
        try:
            trained.reset_for_tests()
            pipe = trained._pipeline()
            label_count = len(getattr(pipe.model.config, "id2label", {}) or {})
            report["labels"] = label_count
            report["loadable"] = label_count == 13
            if report["loadable"]:
                report["pipeline_model"] = type(pipe.model).__name__
            else:
                report["error"] = f"expected 13 labels, got {label_count}"
        except Exception as exc:
            report["loadable"] = False
            report["error"] = f"{type(exc).__name__}: {exc}"
    else:
        report["loadable"] = False
        if not report["available"]:
            report["error"] = "trained_text_model_not_staged"
        elif not report["bytes_ok"]:
            report["error"] = (
                "trained_text_bytes_mismatch: pointer-sized or corrupt artifact"
            )
    return report


@app.function(
    image=secret_preflight_image,
    secrets=[ai_secret],
    timeout=60,
    min_containers=0,
    max_containers=1,
)
def ai_secret_preflight():
    """Read only the AI secret for a non-disclosing release comparison."""
    return _secret_fingerprint(os.environ.get("AI_SHARED_SECRET"))


@app.function(
    image=image,
    gpu="T4",
    cpu=4.0,
    memory=8192,
    secrets=[ai_secret],
    volumes={"/cache": model_cache},
    timeout=1800,
    min_containers=0,
    max_containers=1,
)
def warm_models():
    """Explicit full GPU validation gate. Do not use for routine deployment."""
    os.chdir("/root/littlenet")
    Path("/cache/models").mkdir(parents=True, exist_ok=True)
    os.environ["LITTLENET_AI_SERVER"] = "1"
    os.environ["LITTLENET_DEVICE"] = "cuda"
    os.environ["LITTLENET_DETOXIFY_MODEL"] = "multilingual"

    results = {}

    def run(name, fn):
        try:
            detail = fn()
            results[name] = {"ok": True}
            if detail is not None:
                results[name]["detail"] = detail
        except Exception as exc:
            results[name] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    import importlib

    def detoxify_explicit():
        Detoxify = importlib.import_module("detoxify").Detoxify
        model = Detoxify("multilingual")
        scores = model.predict("Hello, this is a normal LittleNet safety warmup sentence.")
        if "sexual_explicit" not in scores:
            raise RuntimeError("Detoxify multilingual model is missing sexual_explicit output")
        return {"labels": sorted(scores.keys())}
    run("detoxify_multilingual_explicit", detoxify_explicit)

    def nudenet_validate():
        NudeDetector = importlib.import_module("nudenet").NudeDetector
        detector = NudeDetector()
        return {"loaded": detector is not None}
    run("nudenet", nudenet_validate)

    def clip():
        transformers = importlib.import_module("transformers")
        CLIPModel = transformers.CLIPModel
        CLIPProcessor = transformers.CLIPProcessor
        CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
        CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
    run("clip", clip)

    def falconsai():
        pipeline = importlib.import_module("transformers").pipeline
        pipeline("image-classification", model="Falconsai/nsfw_image_detection", device=0)
    run("falconsai_nsfw", falconsai)

    def yolo():
        YOLO = importlib.import_module("ultralytics").YOLO
        from safety.yolo_policy import dangerous_label_coverage
        model = YOLO("/root/littlenet/yolov8n-oiv7.pt")
        matched = dangerous_label_coverage(model.names)
        if len(matched) < 3:
            raise RuntimeError(f"YOLO checkpoint exposes insufficient dangerous-object labels: {matched}")
        return {"dangerous_labels": list(matched)}
    run("yolo_oiv7", yolo)

    def scene_detect():
        scenedetect = importlib.import_module("scenedetect")
        detectors = importlib.import_module("scenedetect.detectors")
        SceneManager = scenedetect.SceneManager
        open_video = scenedetect.open_video
        ContentDetector = detectors.ContentDetector
        _ = SceneManager(); _ = ContentDetector(threshold=27)
        return {"available": callable(open_video)}
    run("pyscenedetect", scene_detect)

    # Persist successful downloads even when a later validation fails. This
    # prevents a retry from downloading gigabytes again.
    model_cache.commit()
    failed = {name: value for name, value in results.items() if not value.get("ok")}
    if failed:
        raise RuntimeError(f"LittleNet AI warmup failed: {failed}")
    return results


@app.local_entrypoint()
def main(
    confirm_gpu_warmup: bool = False,
    trained_image_preflight_only: bool = False,
    trained_text_preflight_only: bool = False,
    secret_preflight: bool = False,
):
    """Cost-guarded maintenance entrypoint."""
    if secret_preflight:
        report = ai_secret_preflight.remote()
        print(f"secret-preflight {json.dumps(report, sort_keys=True)}")
        return
    if trained_image_preflight_only:
        report = trained_image_preflight.remote()
        print(f"trained-image-preflight {json.dumps(report, sort_keys=True)}")
        if not report.get("available") or not report.get("loadable"):
            raise RuntimeError(f"LittleNet trained image ensemble is not ready: {report}")
        return
    if trained_text_preflight_only:
        report = trained_text_preflight.remote()
        print(f"trained-text-preflight {json.dumps(report, sort_keys=True)}")
        if not report.get("available") or not report.get("loadable"):
            raise RuntimeError(f"LittleNet trained text model is not ready: {report}")
        return
    if not confirm_gpu_warmup:
        print("GPU warmup skipped. This command is intentionally cost-guarded.")
        print("CPU trained-image check: modal run modal_ai.py --trained-image-preflight-only")
        print("Full GPU validation only when intentional: modal run modal_ai.py --confirm-gpu-warmup")
        return
    report = warm_models.remote()
    for name, result in report.items():
        print(f"{'OK' if result['ok'] else 'FAIL':4} {name}: {result.get('error', '')}")
