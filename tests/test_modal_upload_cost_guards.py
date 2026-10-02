import io
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch


def test_deterministic_text_gate_catches_obvious_sexual_request_without_ml():
    from safety.policy import decide
    from safety.text_service import check_text_deterministic

    signals = check_text_deterministic("send me nudes")
    decision = decide(signals, "STRICT", 0.40)

    assert signals["deterministic_sexual"] is True
    assert decision.action == "BLOCK"


def test_deterministic_text_gate_leaves_normal_caption_for_full_pipeline():
    from safety.policy import decide
    from safety.text_service import check_text_deterministic

    signals = check_text_deterministic("My science fair project")
    decision = decide(signals, "STRICT", 0.40)

    assert signals["deterministic_only"] is True
    assert signals["adult_score"] == 0.0
    assert decision.action == "ALLOW"


def test_moderation_cache_never_stores_partial_or_total_failures():
    from services import moderation_cache as cache

    with patch.object(cache, "execute") as execute:
        assert cache.store_cached_signals(
            "IMAGE",
            "a" * 64,
            {"total_safety_failure": True, "adult_score": 0.0},
        ) is False
        assert cache.store_cached_signals(
            "IMAGE",
            "b" * 64,
            {"partial_safety_failure": True, "adult_score": 0.0},
        ) is False
        execute.assert_not_called()


def test_moderation_cache_hit_is_versioned_and_counted(monkeypatch):
    from services import moderation_cache as cache

    monkeypatch.setenv("LITTLENET_MODERATION_CACHE_VERSION", "test-v1")
    row = {
        "signals": {
            "adult_score": 0.01,
            "violence_score": 0.0,
            "weapon_score": 0.0,
            "toxicity_score": 0.0,
            "total_safety_failure": False,
            "partial_safety_failure": False,
        }
    }
    with patch.object(cache, "fetch_one", return_value=row), patch.object(cache, "execute") as execute:
        result = cache.get_cached_signals("IMAGE", "c" * 64)

    assert result is not None
    assert result["cache"]["hit"] is True
    assert result["cache"]["version"] == "test-v1"
    execute.assert_called_once()


def test_image_cpu_cost_guard_defaults_off_outside_modal(monkeypatch):
    from services import modal_image_moderation as client

    monkeypatch.delenv("LITTLENET_USE_MODAL_IMAGE_CPU", raising=False)
    monkeypatch.delenv("LITTLENET_ALLOW_IMAGE_GPU_FALLBACK", raising=False)
    assert client.enabled() is False
    assert client.allow_gpu_fallback() is False

    monkeypatch.setenv("LITTLENET_USE_MODAL_IMAGE_CPU", "1")
    assert client.enabled() is True


def test_ai_server_bundles_caption_and_image_in_one_request(monkeypatch):
    prior_server_flag = os.environ.get("LITTLENET_AI_SERVER")
    import ai_server

    monkeypatch.setenv("AI_SHARED_SECRET", "unit-test-secret")
    monkeypatch.setattr(
        ai_server,
        "check_text",
        lambda text: {"category": "TEXT", "toxicity_score": 0.01, "total_safety_failure": False},
    )
    monkeypatch.setattr(
        ai_server,
        "check_image",
        lambda path: {"category": "IMAGE", "adult_score": 0.02, "total_safety_failure": False},
    )

    response = ai_server.app.test_client().post(
        "/ai/moderate-upload",
        data={
            "content_type": "IMAGE",
            "text": "hello",
            "file": (io.BytesIO(b"fake-image-bytes"), "x.jpg"),
        },
        headers={"X-LittleNet-AI-Key": "unit-test-secret"},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["text_signals"]["category"] == "TEXT"
    assert payload["media_signals"]["category"] == "IMAGE"

    if prior_server_flag is None:
        os.environ.pop("LITTLENET_AI_SERVER", None)
    else:
        os.environ["LITTLENET_AI_SERVER"] = prior_server_flag


def test_modal_job_queue_uses_low_cost_worker_for_images(monkeypatch):
    import sys
    import types
    from services.job_queue import ModalJobQueue

    seen = {}

    class Call:
        object_id = "call-1"

    class Fn:
        def spawn(self, *args):
            seen["args"] = args
            return Call()

    class Function:
        @staticmethod
        def from_name(app_name, function_name):
            seen["app_name"] = app_name
            seen["function_name"] = function_name
            return Fn()

    fake_modal = types.SimpleNamespace(Function=Function)
    monkeypatch.setitem(sys.modules, "modal", fake_modal)

    queue = ModalJobQueue()
    result = queue.enqueue(
        "media_processing",
        {
            "post_id": 1,
            "child_id": 2,
            "object_key": "uploads/r2/quarantine/2/x/source.jpg",
            "kind": "post",
        },
    )

    assert result == "call-1"
    assert seen["function_name"] == "process_image_job_background"


def test_remote_upload_bundle_uses_single_http_post(monkeypatch):
    from safety import remote_client

    monkeypatch.setenv("AI_SERVICE_URL", "https://ai.example")
    monkeypatch.setenv("AI_SHARED_SECRET", "secret")

    fake_response = Mock()
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = {
        "ok": True,
        "text_signals": {"category": "TEXT"},
        "media_signals": {"category": "IMAGE", "adult_score": 0.0},
    }

    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    Path(path).write_bytes(b"x")
    try:
        with patch.object(remote_client.requests, "post", return_value=fake_response) as post:
            result = remote_client.moderate_upload("IMAGE", path, "caption")

        assert result["media_signals"]["category"] == "IMAGE"
        assert post.call_count == 1
        assert post.call_args.args[0] == "https://ai.example/ai/moderate-upload"
    finally:
        Path(path).unlink(missing_ok=True)



def test_modal_text_cpu_client_uses_shared_scale_to_zero_function(monkeypatch):
    import sys
    import types
    from services import modal_text_moderation as client

    seen = {}

    class Fn:
        def remote(self, *args):
            seen["args"] = args
            return {
                "ok": True,
                "text_signals": {"category": "TEXT", "toxicity_score": 0.01},
                "media_signals": {},
            }

    class Function:
        @staticmethod
        def from_name(app_name, function_name):
            seen["app_name"] = app_name
            seen["function_name"] = function_name
            return Fn()

    monkeypatch.setitem(sys.modules, "modal", types.SimpleNamespace(Function=Function))
    monkeypatch.setenv("LITTLENET_USE_MODAL_TEXT_CPU", "1")
    monkeypatch.delenv("LITTLENET_AI_SERVER", raising=False)

    result = client.moderate_text("hello world")

    assert result["category"] == "TEXT"
    assert seen["function_name"] == "moderate_image_upload_cpu"
    assert seen["args"][0] == b""
    assert seen["args"][3] is True
    assert seen["args"][4] is False


def test_check_text_prefers_cpu_and_never_calls_gpu_when_enabled(monkeypatch):
    from safety import text_service

    monkeypatch.setenv("LITTLENET_USE_MODAL_TEXT_CPU", "1")
    monkeypatch.setenv("LITTLENET_ALLOW_TEXT_GPU_FALLBACK", "0")
    monkeypatch.delenv("LITTLENET_AI_SERVER", raising=False)

    with patch(
        "services.modal_text_moderation.moderate_text",
        return_value={
            "category": "TEXT",
            "adult_score": 0.01,
            "toxicity_score": 0.02,
            "general_score": 0.02,
            "total_safety_failure": False,
            "partial_safety_failure": False,
        },
    ) as cpu, patch("safety.remote_client.moderate_text") as gpu:
        result = text_service.check_text("A normal science message")

    assert result["compute_tier"] == "modal_cpu"
    cpu.assert_called_once()
    gpu.assert_not_called()


def test_check_text_cpu_failure_does_not_silently_wake_gpu(monkeypatch):
    from safety import text_service

    monkeypatch.setenv("LITTLENET_USE_MODAL_TEXT_CPU", "1")
    monkeypatch.setenv("LITTLENET_ALLOW_TEXT_GPU_FALLBACK", "0")
    monkeypatch.delenv("LITTLENET_AI_SERVER", raising=False)

    with patch(
        "services.modal_text_moderation.moderate_text",
        side_effect=RuntimeError("cpu unavailable"),
    ), patch("safety.remote_client.moderate_text") as gpu:
        result = text_service.check_text("A normal science message")

    assert result["total_safety_failure"] is True
    assert result["compute_tier"] == "modal_cpu_failed_closed"
    gpu.assert_not_called()


def test_check_image_prefers_cpu_and_never_calls_gpu(monkeypatch):
    from safety import visual_service

    monkeypatch.setenv("LITTLENET_USE_MODAL_IMAGE_CPU", "1")
    monkeypatch.setenv("LITTLENET_ALLOW_IMAGE_GPU_FALLBACK", "0")
    monkeypatch.delenv("LITTLENET_AI_SERVER", raising=False)

    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    from PIL import Image
    Image.new("RGB", (32, 32), color="green").save(path, format="JPEG")
    try:
        with patch(
            "services.modal_image_moderation.moderate_image_upload",
            return_value={
                "media_signals": {
                    "category": "IMAGE",
                    "adult_score": 0.01,
                    "general_score": 0.01,
                    "total_safety_failure": False,
                    "partial_safety_failure": False,
                }
            },
        ) as cpu, patch("safety.remote_client.moderate_file") as gpu:
            result = visual_service.check_image(path)

        assert result["compute_tier"] == "modal_cpu"
        cpu.assert_called_once()
        gpu.assert_not_called()
    finally:
        Path(path).unlink(missing_ok=True)


def test_modal_deploy_workflow_migration_order_and_warmup_flag():
    workflow_path = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "deploy-modal.yml"
    assert workflow_path.is_file(), "deploy-modal.yml not found"
    content = workflow_path.read_text(encoding="utf-8")

    # 1. Warmup flag must use --confirm-gpu-warmup to pass modal_ai.py cost guard
    assert "modal run modal_ai.py --confirm-gpu-warmup" in content

    # Retained release DBs must never replay the legacy bootstrap. The release
    # proves migration history, optionally applies reviewed dbmate deltas, then
    # requires zero pending migrations before replacing cloud code.
    assert "modal run modal_web.py --init-db" not in content
    status_idx = content.index("modal run modal_web.py --migration-status-check")
    migrate_idx = content.index("modal run modal_web.py --migrate-db")
    current_idx = content.index("modal run modal_web.py --require-db-current")
    deploy_ai_idx = content.index("modal deploy modal_ai.py")
    deploy_web_idx = content.index("modal deploy modal_web.py")
    assert status_idx < migrate_idx < current_idx < deploy_ai_idx < deploy_web_idx
    assert "LITTLENET_WEB_MODAL_APP: littlemuse-web" in content
    assert "LITTLENET_AI_MODAL_APP: littlemuse-ai" in content
