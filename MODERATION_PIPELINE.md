# Moderation Pipeline — CURRENT release view

Canonical architecture: `docs/FINAL_ARCHITECTURE.md`.
Model-class details: `docs/TRAINED_MODERATION.md`.
Storage keys: `R2_STORAGE_MAP.md`.
Cost/GPU bounds: `MODAL_COST_READINESS.md`.

This file is the current release map. It does not claim live inference was run
from this package.

## Mobile v2 (authoritative new-media path)

```text
POST /api/mobile/v2/uploads/session
        |
        v
PUT bytes to private R2 quarantine (or guarded local mock-PUT in development)
        |
        v
POST /api/mobile/v2/uploads/<upload_id>/complete
  (owner, expiry, exact size, declared MIME)
        |
        v
Background job (local queue in development; Modal spawn in production)
  sanitize + evaluate(media + caption)
        |
        +-- ALLOWED  -> promote sanitized bytes -> eligible feeds
        +-- REVIEW   -> remain private -> Parent/Admin review
        +-- BLOCKED  -> delete/invalidate quarantine -> never public
        +-- retryable -> bounded lease / backoff / FAILED at cap
        |
        v
GET /api/mobile/v2/posts/<post_id>/processing-status
```

The client never publishes. Parent/Admin approval calls the server transition
that sanitizes/promotes and fails closed on processing errors. A terminal
BLOCKED post cannot be resurrected by APPROVE.

## What runs (when real weights are present)

| Content | Models | Fail-closed fallback |
|---|---|---|
| Image 18+ | `littlenet_core_safety_v2.pth` | NudeNet / FalconsAI / CLIP |
| Image weapons/violence | `littlenet_weapons_violence_v3.pth` | same visual stack |
| Dangerous objects | `yolov8n-oiv7.pt` (preferred) or `yolov8n.pt` | policy labels in `config/safety_policy.yaml` |
| Video | same image stack on sampled frames | incomplete coverage -> REVIEW |
| Text / captions / chat | `littlenet_text_safety/` + deterministic rules + Detoxify | outage -> REVIEW / BLOCK, never silent allow |

YOLO files in this tree are **real Ultralytics weights**. They are **not**
custom LittleNet checkpoints.

## Custom model status in THIS package

| File | State |
|---|---|
| `models/littlenet_core_safety_v2.pth` | **GIT LFS POINTER ONLY** (133 bytes) |
| `models/littlenet_weapons_violence_v3.pth` | **GIT LFS POINTER ONLY** (133 bytes) |
| `models/littlenet_text_safety/model.safetensors` | **GIT LFS POINTER ONLY** (134 bytes) |

**ACTUAL TRAINED PAYLOAD MUST BE PULLED BEFORE AI INFERENCE DEPLOYMENT.**
`safety/model_files.py` rejects Git LFS pointer files so they are never treated
as staged weights.

## Parent Review

Parent/Admin review is server-authorized (`owns()` / admin role). REVIEW bytes
stay private. BLOCKED content is not delivered. See
`release_docs/FINAL_FIX_REPORT.md` for the blocked-content republish guard.

## Reel quiz latch

While the child's quiz latch is active, reel playback on
`/api/mobile/v2/media/playback` and `/api/mobile/v2/curated/media` returns
HTTP 428 `quiz_required`. The mobile player hands that off to the Quiz screen
and does not retry as a generic error.
