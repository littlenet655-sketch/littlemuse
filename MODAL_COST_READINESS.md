# Modal Cost / Resource Readiness

**CURRENT:** source defaults and the Demo Boost restore fix remain in
`f4be262`. Nothing was deployed from this HEAD. Live Modal settings remain
EXTERNAL VERIFICATION REQUIRED. Custom model files in this tree are still
Git LFS pointers — pull real payloads before AI inference deployment.

Scope: static source audit of this workspace (branch `release-candidate`, originally based at `0f425af`).
Nothing was deployed, no Modal/Neon/R2 call was made, no GPU was started.
Every value below is read from source; anything that needs a live Modal workspace is
listed under "Live verification still required" and is **NOT EXECUTED**.

## 1. Modal functions and compute assignment

| Function (file:name) | Compute | min | max | Concurrency | Idle (scaledown) | Timeout |
|---|---|---|---|---|---|---|
| `modal_ai.py:ai_web` (Flask AI server, wsgi) | **GPU T4**, 4 CPU, 8 GiB | 0 | 1 | `max_inputs=1,target_inputs=1` | `MODAL_AI_GPU_SCALEDOWN_WINDOW`, default 30 s | 900 s (startup 900 s) |
| `modal_ai.py:warm_models` | **GPU T4**, 4 CPU, 8 GiB | 0 | 1 | default | n/a (one-shot) | 1800 s |
| `modal_ai.py:moderate_image_upload_cpu` (image + caption/text moderation) | CPU 4, 8 GiB (`LITTLENET_DEVICE=cpu`) | 0 | 1 | `max_inputs=1,target_inputs=1` | `MODAL_AI_IMAGE_CPU_SCALEDOWN_WINDOW`, default 30 s | 600 s (startup 900 s) |
| `modal_ai.py:trained_image_preflight` | CPU 2, 4 GiB | 0 | 1 | default | default | 300 s |
| `modal_ai.py:trained_text_preflight` | CPU 2, 8 GiB | 0 | 1 | default | default | 900 s |
| `modal_ai.py:ai_secret_preflight` | CPU (no models) | 0 | 1 | default | default | 60 s |
| `modal_web.py:web` (Flask app, wsgi) | CPU `MODAL_WEB_CPU`=2.0, `MODAL_WEB_MEMORY`=2048 | `MODAL_WEB_MIN_CONTAINERS` default **0** | `MODAL_WEB_MAX_CONTAINERS` default 3 | **none set** (Modal default, 1 request per container) | `MODAL_WEB_SCALEDOWN_WINDOW` default 60 s | 300 s (startup 120 s) |
| `modal_web.py:process_image_job_background` | CPU 1, 2 GiB | 0 | 1 | default | `MODAL_IMAGE_WORKER_SCALEDOWN_WINDOW` default 20 s | 600 s |
| `modal_web.py:process_media_job_background` (video/reel/story) | CPU 2, 4 GiB | 0 | 1 | default | `MODAL_MEDIA_WORKER_SCALEDOWN_WINDOW` default 30 s | 900 s |
| `modal_web.py:curated_poster_backfill`, `web_secret_preflight`, `web_preflight`, `database_migration_status`, `migrate_retained_database`, `init_database`, `seed_quizzes` | CPU, one-shot operator tools | 0 / 0 / n/a | 1 / 1 / n/a | default | default | 60-1800 s |

Only two functions can allocate a GPU: `ai_web` and `warm_models`. No function in
`modal_web.py` requests a GPU. No function sets `retries=` (no Modal-level automatic
re-execution). No `schedule=` / `modal.Cron` / `modal.Period` exists in any Python file.

## 2. Scale-to-zero status

Source default is scale-to-zero everywhere: every AI function and background worker has
`min_containers=0`; GPU idle window is 30 s; `max_containers=1` caps the T4 and both
CPU AI tiers at one container each. The only non-zero risk is the web function, which is
zero by default but is driven by the environment variable `MODAL_WEB_MIN_CONTAINERS`
(an operator who exports a value >0 before `modal deploy modal_web.py` pays for idle
CPU 24x7; it can never wake a GPU). `.env.example` / deploy workflow do not set it.

## 3. How a GPU wake can (and cannot) happen

Can wake the T4 (all intentional, all authenticated):
- VIDEO moderation (`safety/video_service.py` -> `remote_client.moderate_file`, or the
  bundled `remote_client.moderate_upload` for video + caption) -> `ai_web`.
- Explicit GPU fallbacks, **off** in the deployed web image
  (`LITTLENET_ALLOW_IMAGE_GPU_FALLBACK=0`, `LITTLENET_ALLOW_TEXT_GPU_FALLBACK=0`).
- Admin-only Demo Boost (`services/demo_boost.py`): raises idle window (max 65 min,
  max 1 container, `min_containers` stays 0) and calls `ai_web /warmup` once.
- Operator tools: `modal run modal_ai.py --confirm-gpu-warmup` (workflow input
  `warm_ai_models`, default false) and `modal run modal_web.py --preflight --deep-ai-probe`.

Cannot wake the T4 (verified in source):
- CRUD / auth / profile / feed / chat / comments: text goes to the CPU tier
  (`safety/text_service.py:check_text` -> `services/modal_text_moderation.py`); on CPU
  failure it returns deterministic fail-closed signals, never calls GPU.
- Feed ranking: `safety/remote_client.py:rank_texts` returns `[]` unless
  `AI_ENABLE_REMOTE_RANKING` is truthy (default off); `services/recommendation.py`
  falls back to deterministic ranking.
- `/readyz` (`app.py`) and `web_preflight`: `remote_client.health()` is passive
  ("passive_configured", `gpu_woken: false`) unless `AI_DEEP_HEALTH=1` or `AI_HEALTH_URL`
  is set. `modal_web.py --preflight` uses `deep_ai_probe=False` by default; the deploy
  workflow never passes it.
- Processing-status polling (`/api/mobile/v2/posts/<id>/processing-status`): DB read only.
- Image uploads: sanitised JPEG proxy (<=1600 px) goes to `moderate_image_upload_cpu`
  with caption in the same call; CPU failure marks `modal_cpu_image_moderation_unavailable`
  (fail closed) rather than GPU.

## 4. Duplicate inference, caching, retries

- One bundled request per upload when both caption and media miss cache
  (`services/media_processor.py`: CPU tier for images, `moderate_upload` for video).
- Exact-content cache `services/moderation_cache.py` (`moderation_signal_cache`, SHA-256 +
  cache version `2026-09-20-v2-trained-image` in the web image, TTL 30 d). It refuses to
  store or serve `total_safety_failure` / `partial_safety_failure` evidence, so failed
  moderation is never cached as "clean" and never reused. Policy is re-applied on hits.
- Failure path: an unavailable CPU/GPU tier writes in-memory failure signals only; they
  are not persisted to the cache (checked in `store_cached_signals`).
- Retry bounds: DB lease `claim_media_job_lease` — `max_processing_attempts` default 3,
  backoff `min(300, 5 * 2^(attempts-1))` s, terminal FAILED after the cap, terminal
  ALLOWED/BLOCKED never reclaimed. `redrive_media_job` is user/guardian-triggered;
  `reap_stale_media_jobs` (LIMIT 50) is ADMIN-triggered only — there is no cron.
  Duplicate spawns for the same post are therefore harmless (second one fails the lease
  claim before any model runs). `ModalJobQueue` passes a dedup id but Modal's `spawn`
  does not enforce it; the DB lease is the real guard.
- `modal.Function.from_name(...)` is resolved per call in `job_queue.py`,
  `modal_image_moderation.py`, `modal_text_moderation.py`: extra lookup latency only,
  no compute cost.

## 5. Model initialisation

Models are lazily loaded once per container and kept in module globals with locks
(`safety/littlenet_trained_image.py:_MODELS`, `safety/littlenet_trained_text.py:_PIPELINE`,
`safety/text_service.py:_DETOX/_HF_TEXT`, `safety/visual_service.py:_NSFW/_YOLO/...`).
With `max_inputs=1` and `max_containers=1`, a warm container serves repeated requests
without reloading. Weights are read from the `littlenet-model-cache` volume; volume commit
happens only when cache markers are missing. Git-LFS pointer files are rejected by
`available()` before any load attempt (`safety/model_files.py`).
Watch item (not changed): a load that *raises* (corrupt real file) is not negatively
cached, so each request in that container retries the load. Impact is bounded (1 container,
3 attempts per post, CPU tier) and it is a fail-closed path; documented, not "fixed",
because suppressing retries would change moderation behaviour.

## 6. Cost-risk findings

| # | Finding | Severity | Status |
|---|---|---|---|
| 1 | `services/demo_boost.py`: `status()`/`stop()` marked the singleton row `OFF` *before* restoring the autoscaler and swallowed restore errors; the comment said a later call would retry, but with the row already OFF nothing ever retried. A transient Modal API error would leave `scaledown_window` of up to 3900 s on the T4 and CPU AI functions until the next deploy (each wake then idles up to 65 min instead of 30 s). | Medium (unbounded in time, bounded to 1 container each) | **Fixed** (see §7) |
| 2 | `modal_web.py:web` has no `@modal.concurrent`; each web container serves one request at a time (max 3 containers). Throughput/latency risk under chat polling, not a credit leak. | Low (performance) | Documented; unchanged — needs a measured load test before choosing `max_inputs` |
| 3 | `MODAL_WEB_MIN_CONTAINERS` env can pin idle web CPU. | Low | Default 0; documented in §8 |
| 4 | Each chat/comment/caption text check triggers a CPU-tier call without a text cache in the synchronous path (CPU container, scale-to-zero after 30 s, `max_inputs=1`). | Low | Documented; adding caching changes safety evidence reuse, out of scope |
| 5 | `AI_HEALTH_URL` pointed at `ai_web /healthz`, or `AI_DEEP_HEALTH=1`, makes every `/readyz` hit wake the T4. Defaults are safe. | Operational | Defaults correct; do not set both on an externally-polled `/readyz` |
| 6 | Workflow `deploy-modal.yml` triggers on push only for `.release/deploy-live.txt` and has `warm_ai_models` default false; `deploy-web-only.yml` deploys only for `workflow_dispatch` or a `[deploy-web]` commit message and never touches the AI app; `live-media-probe.yml` only on `.release/probe-live-media.txt`. No `schedule:` anywhere. | None | Already correct |

## 7. Changes made

- `services/demo_boost.py`: `_restore_autoscaler()` now returns `bool`; `status()` flips
  the row to `OFF` only after a successful restore (otherwise the next poll retries);
  `stop()` expires the boost immediately (`expires_at=NOW()`) and lets `status()` do the
  restore/flip. Behaviour visible to clients is unchanged (inactive immediately).
  Never raises `min_containers` above 0; `max_containers` stays 1.
- New regression test `tests/test_demo_boost_autoscaler_restore.py` (mock-only, 4 tests).

No moderation logic, model inference, scaling decorator or env default was changed.

## 8. Already correct (no change needed)

GPU confined to `ai_web` + `warm_models`; `min_containers=0` on all AI/worker functions;
`max_containers=1` on AI/worker functions; short idle windows (20-30 s); GPU/CPU
concurrency 1 (no parallel model memory blow-up); image path on CPU with GPU fallback
disabled; single bundled request per upload; versioned failure-safe moderation cache;
bounded DB-lease retries with backoff; no Modal `retries=`; no crons; passive `/readyz`;
remote ranking opt-in; polling endpoints DB-only; LFS-pointer guard before model load;
deploy workflow warmup gated by an explicit input; Demo Boost capped (60 min start,
65 min window, 1 container, auth-gated, role-scoped).

## 9. Live verification still required — NOT EXECUTED

1. `modal app list` / dashboard: confirm deployed `littlemuse-ai` and `littlemuse-web`
   show min 0, and that `ai_web` is the only GPU function.
2. Confirm no leftover Demo Boost autoscaler override on the deployed functions
   (the pre-fix restore could fail silently) — compare the live `scaledown_window` with 30 s.
3. Confirm `MODAL_WEB_MIN_CONTAINERS`, `AI_DEEP_HEALTH`, `AI_HEALTH_URL`,
   `AI_ENABLE_REMOTE_RANKING` values in the `littlemuse-web-secrets` secret (values not
   readable from source).
4. Cold-start timings and cost per image / per video upload (no measurements exist;
   none are claimed).
5. Trained model payloads must be pulled with Git LFS and staged to the volume before the
   AI app is useful; ACTUAL TRAINED MODEL PAYLOADS MUST BE PULLED WITH GIT LFS BEFORE
   AI INFERENCE DEPLOYMENT.
6. Load test of web concurrency before choosing `@modal.concurrent(max_inputs=N)`.

## 10. Recommended production settings (from this source)

- Keep: `min_containers=0` and `max_containers=1` on `ai_web`, `moderate_image_upload_cpu`,
  both workers; GPU idle window 30 s; `LITTLENET_ALLOW_*_GPU_FALLBACK=0`.
- Web: leave `MODAL_WEB_MIN_CONTAINERS` unset/0 (accept a cold start) or set to 1 only for
  a scheduled demo window, then redeploy with 0. Consider `max_containers` 3 unchanged.
- Leave `AI_DEEP_HEALTH` and `AI_ENABLE_REMOTE_RANKING` unset. Do not set `AI_HEALTH_URL`
  to a GPU endpoint.
- Run `warm_ai_models` only when a demo needs it; prefer Demo Boost (auto-expires) over a
  raised floor.
- Monitor the first 24 h of Modal usage for GPU seconds vs. video upload count.
