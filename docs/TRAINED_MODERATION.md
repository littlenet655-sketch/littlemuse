# Trained moderation — integration report

LittleNet's user-trained safety models (18+/adult, violence, weapons, 18+ text)
are enforced **server-side**. No upload path relies on client-side hiding.

## What runs live (code)

| Content | Trained model | Entry point | Enforcement |
|---|---|---|---|
| Image 18+ (nudity/sexy) | `littlenet_core_safety_v2.pth` (EfficientNet-B0) | `safety/visual_service.py::check_image` → `safety/littlenet_trained_image.py` | `policy.decide`: triggered class → `adult_score ≥ 0.80` → **BLOCK** (threshold 0.40) |
| Image weapons/violence | `littlenet_weapons_violence_v3.pth` (EfficientNet-B0) | same as above | triggered weapons → `weapon_score ≥ 0.80` → **BLOCK** (threshold 0.45); near-threshold violence → **REVIEW** |
| Dangerous objects | `yolov8n-oiv7.pt` / `yolov8n.pt` (repo root) | same as above, merged via `_merge_yolo_into_trained` (runs even when the ensemble runs) | per-family BLOCK/REVIEW from `config/safety_policy.yaml` |
| Video 18+/weapons/violence | same image stack, per sampled frame | `safety/video_service.py::check_video` (scene-aware + uniform sampling, early BLOCK) | max-over-frames; incomplete coverage → REVIEW |
| Text 18+ | `littlenet_text_safety/` (HF text-classification dir) | `safety/text_service.py::check_text` → `safety/littlenet_trained_text.py` | merged by max into `sexual_score`; ≥ 0.40 → **BLOCK** |
| Burned-in image text/PII | OCR → same text policy | `_apply_ocr_stage` (runs on trained AND legacy paths) | PII/contact → hard **BLOCK** |

Fallbacks (fail closed, never silent allow): deterministic 18+ keyword/regex
rules + Detoxify multilingual for text; NudeNet + FalconsAI + CLIP for images
when the private checkpoints are absent. `total_safety_failure` → BLOCK,
`partial_safety_failure` → REVIEW.

## Model files

**Already in repo:** `yolov8n.pt`, `yolov8n-oiv7.pt` (repo root; oiv7 preferred
for weapon labels).

**Needed from the user** (training is done; stage the artifacts):

1. `littlenet_core_safety_v2.pth` — torch checkpoint dict with keys
   `state_dict`, `labels` (must include `nudity`, `sexy`), optional
   `thresholds` dict. Architecture: EfficientNet-B0 with final linear layer
   sized to `len(labels)` (see `safety/littlenet_trained_image.py::_load_one`).
2. `littlenet_weapons_violence_v3.pth` — same format; `labels` must include
   `weapons`, `violence`.
3. `littlenet_text_safety/` — **directory** in Hugging Face format:
   `config.json` + `tokenizer.json` (or `tokenizer_config.json` + vocab) +
   `model.safetensors` (or `pytorch_model.bin`). Load via
   `transformers.pipeline("text-classification")`; labels are bucketed by
   keyword (`sexual/explicit/porn/nsfw/adult/erotic/nudity` → 18+ score,
   `violence/violent/threat/kill` → violence, `toxic/hate/harass/bully/abuse/self-harm`
   → toxicity). See `safety/littlenet_trained_text.py`.

**Where to place them** (first existing location wins):
- Modal: `/cache/models/` on the `littlenet-model-cache` volume
  (`/cache/models/littlenet_core_safety_v2.pth`,
  `/cache/models/littlenet_weapons_violence_v3.pth`,
  `/cache/models/littlenet_text_safety/`), or
- Local dev: `<repo>/models/` (same filenames), or
- Anywhere: set `LITTLENET_TRAINED_IMAGE_V2_PATH`,
  `LITTLENET_TRAINED_IMAGE_V3_PATH`, `LITTLENET_TRAINED_TEXT_PATH`.

## Key env flags

- `LITTLENET_ENABLE_TRAINED_IMAGE_ENSEMBLE=1` (default on)
- `LITTLENET_ENABLE_TRAINED_TEXT=1` (default on)
- `LITTLENET_YOLO_WEIGHTS` (default: repo-root `yolov8n-oiv7.pt`, else `yolov8n.pt`)
- `LITTLENET_ENABLE_OCR=1` for burned-in text screening (off by default)
- `LITTLENET_USE_MODAL_IMAGE_CPU=1` to route image moderation to the
  `littlenet-ai` CPU function (default 0; the media worker below is preferred)

## Upload-path coverage

- **Mobile v2** (`/api/mobile/v2/uploads/*`): R2 quarantine → Modal background
  worker (`process_media_job_background` / `process_image_job_background` in
  `modal_web.py`, now mounting the `littlenet-model-cache` volume) →
  `services/media_processor.py::process_media_job` → `evaluate()` on media +
  caption/tags → BLOCK (quarantine deleted, never published) / REVIEW (held,
  owner-only, parent notified) / ALLOW (promoted to published namespace).
  Status via `GET /api/mobile/v2/posts/<id>/processing-status` + push
  notifications.
- **Web** (`/child/upload-post/`, `/upload-story/`, `/send-media/`,
  `/child/upload-profile-picture/`): synchronous server-side `evaluate()` in
  the request — BLOCK → 400 + file deleted, REVIEW → stored held. (Pre-existing
  deviation from AGENTS.md rule 7's quarantine pipeline; moderation itself is
  server-enforced, not stubbed.)
- **Text** (comments, chat, profile text, captions): synchronous server-side
  `evaluate('TEXT')` everywhere; captions also re-checked in the media worker.

## Deployment checklist (not done — needs the user's deploy step)

1. Stage the three artifacts above onto the `littlenet-model-cache` Modal
   volume with `python tools/stage_model_volume.py` (refuses pointer stubs /
   size mismatches). Verify with the `trained_image_preflight` and
   `trained_text_preflight` functions in `modal_ai.py`:
   `modal run modal_ai.py --trained-image-preflight-only` and
   `modal run modal_ai.py --trained-text-preflight-only`.
2. Redeploy `littlenet-web` so the media workers pick up the volume mount
   (prepared in `modal_web.py`; no code deploy performed here).
3. Optional: set `LITTLENET_ENABLE_OCR=1` for burned-in text screening.

## Tests

`tests/test_trained_moderation_enforcement.py` (11 tests): flagged image →
BLOCK, clean image → ALLOW (both through `moderation_service.evaluate`);
YOLO weapon detection merges on the trained path; YOLO failure → REVIEW;
OCR stage runs on the trained path; `nsfw_policy` recognises the ensemble;
flagged 18+ text via the trained text model → BLOCK, clean → ALLOW;
artifact gating (missing dir / missing `config.json` / disabled flag).
Existing `tests/test_trained_image_ensemble.py` still passes.
