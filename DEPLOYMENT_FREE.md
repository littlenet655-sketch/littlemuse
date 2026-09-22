# LittleNet  -  Railway Free / Low-RAM Deployment

> **Legacy / optional demo path — not production.** The canonical production
> deployment is Modal; see **[MODAL_DEPLOYMENT.md](./MODAL_DEPLOYMENT.md)**,
> the single authoritative deployment guide. This document is kept for the
> low-RAM Railway demo layout only.

LittleNet supports a split runtime so the social web application does not need to
load PyTorch, TensorFlow and YOLO in the same 512 MB process.

## Recommended college-demo layout

```
Android APK / Browser
        |
        v
Railway web service (Dockerfile.web)
        |
        +--> PostgreSQL DATABASE_URL
        |
        +--> AI_SERVICE_URL (separate inference service)
```

### Railway web service
Use `Dockerfile.web`. It installs only `requirements-core.txt` plus ffmpeg. Set:

- `SECRET_KEY`
- `DATABASE_URL`
- `BASE_URL`
- `COOKIE_SECURE=1`
- `AI_SERVICE_URL`
- `AI_SHARED_SECRET`
- optional mail variables

`/healthz` checks the web process and PostgreSQL only.
`/readyz` additionally verifies the configured AI service.

### AI service
`Dockerfile.ai` exposes:

- `POST /ai/moderate`
- `POST /ai/face/embedding`
- `POST /ai/face/verify`
- `GET /healthz`
- `POST /ai/rank` (safe-candidate semantic personalization)

Set the same `AI_SHARED_SECRET` on both services.

The AI service does not need database credentials and deletes temporary input
files after inference.

## Why the split exists
Railway Free is suitable for small applications, but LittleNet's combined AI
runtime is substantially larger than a small Flask process. Keep heavyweight
inference off the low-RAM web service. The all-in-one `Dockerfile` remains
available for a larger machine/Hobby plan.

## Upload storage
For a short college demo, a small persistent volume can hold uploads. Keep demo
media intentionally small and purge unnecessary files. For longer use, move
media to object storage.

## Before APK build
1. `/healthz` must return HTTP 200.
2. `/readyz` must return HTTP 200.
3. Run the safe/adult/weapon/video/face smoke tests.
4. Put the final HTTPS web URL into the APK build workflow.
