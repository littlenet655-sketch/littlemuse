# LittleNet Deployment — Canonical Guide

> **This is the single authoritative deployment guide for LittleNet.**
> The canonical production target is **Modal** (`modal_web.py` + `modal_ai.py`).
> `DEPLOY_GUIDE.md` is a pointer to this document.
> `DEPLOYMENT_FREE.md` documents an optional legacy Railway demo path — it is
> not production.

_Last updated: 2026-09-21_

## Canonical target

**Modal is the production deployment.** Evidence:

- `modal_web.py` defines the `littlenet-web` Modal app: WSGI-serves
  `app:create_app()`, mounts the `littlenet-web-secrets` / `littlenet-email` /
  `littlenet-r2` Modal secrets, attaches the `littlenet-uploads` volume, and
  ships `init_database` (legacy baseline + `dbmate up`) and `web_preflight`
  entrypoints.
- `modal_ai.py` defines the `littlenet-ai` Modal app: heavy moderation/face
  inference on a scale-to-zero T4, invoked by the web app only for real
  moderation/face work.
- `.github/workflows/deploy-modal.yml` (**Deploy & Validate LittleNet Live**)
  is the connected release workflow: AI deploy → web deploy → PostgreSQL
  bootstrap/migrations → quiz seed → preflight → `/healthz` + `/readyz` →
  Playwright smoke → live-backed Android APK artifact.
- `.github/workflows/deploy-web-only.yml` redeploys `modal_web.py` to Modal.
- `.github/workflows/build-local-apk.yml` builds the APK against the Modal web
  URL (`EXPO_PUBLIC_API_BASE_URL=https://netlittle2--littlenet-web-web.modal.run`).
- Recent release commits are tagged `[deploy-web]` / `[build-local-apk]` and
  harden the Modal release flow.

**Legacy / optional adapters (kept, not canonical):** `railway.toml` →
`Dockerfile.web` (Railway demo path, see `DEPLOYMENT_FREE.md`),
`cloudbuild.web.yaml` (Cloud Run experiment), `Dockerfile` (all-in-one legacy),
`Dockerfile.ai` (standalone AI container). Do not use these for production.

## Architecture

- **Web:** `modal_web.py` — Flask/Jinja social app (`littlenet-web`)
- **Heavy AI:** `modal_ai.py` — T4 GPU inference (`littlenet-ai`), scale-to-zero
- **Database:** external PostgreSQL (Neon), migrated with **dbmate**
- **Private media:** Cloudflare R2
- **Android:** React Native + Expo client against the verified API URL

Standalone speech/audio moderation is intentionally outside the locked current
scope. Uploaded child videos are sanitized to remove audio before persistence.

## Prerequisites

1. GitHub repository Actions secrets (used by the release workflow):

```text
MODAL_TOKEN_ID
MODAL_TOKEN_SECRET
```

2. Modal CLI locally for manual diagnosis:

```bash
python -m pip install -r requirements-modal.txt
modal token info
```

## Modal secrets (names only — never commit values)

Create the AI secret with the same shared secret used by the web service:

```bash
modal secret create littlenet-ai-secrets \
  AI_SHARED_SECRET="<long-random-shared-secret>"
```

The web secret must contain the real runtime configuration. The Modal
definition requires these core keys:

```text
DATABASE_URL
SECRET_KEY
AI_SERVICE_URL
AI_SHARED_SECRET
```

The live release preflight additionally requires a real public `BASE_URL`,
working private R2 storage, and working Resend credentials.

Put `BASE_URL` in `littlenet-web-secrets`. Put private media credentials in the
separately mounted `littlenet-r2` secret:

```text
R2_ACCOUNT_ID
R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY
R2_BUCKET
R2_SIGNED_URL_TTL
```

Optional adaptive video settings also belong in `littlenet-r2` because that
secret is mounted only on backend functions:

```text
CLOUDFLARE_STREAM_ENABLED=1
CLOUDFLARE_STREAM_ACCOUNT_ID
CLOUDFLARE_STREAM_API_TOKEN
CLOUDFLARE_STREAM_SUBDOMAIN
CLOUDFLARE_STREAM_API_TIMEOUT_SECONDS
CLOUDFLARE_STREAM_SIGNING_KEY_ID
CLOUDFLARE_STREAM_SIGNING_PRIVATE_KEY_B64
```

Leave `CLOUDFLARE_STREAM_ENABLED` unset/0 until real Stream credentials are
configured — LittleNet then stays on its private sanitized R2 MP4 path
(see "Enabling Cloudflare Stream later" below).

For mail, configure the verified Resend production sender in the
`littlenet-email` Modal secret. `modal_web.py` attaches this secret to the live
web function; updating only a local secret or only `littlenet-web-secrets`
does not refresh the running deployment.

```text
RESEND_API_KEY
RESEND_WEBHOOK_SECRET
RESEND_FROM_EMAIL
RESEND_FROM_NAME
```

The sender must be a domain-verified LittleNet address (the parent OTP path
always sends as `LittleNet <no-reply@littlenet.in>`). Configure a Resend
webhook for `https://<public-littlenet-web-url>/webhooks/resend` subscribed to
delivery, bounce, failed, suppressed and complaint events.
`RESEND_WEBHOOK_SECRET` must be the signing secret for that webhook. LittleNet
deliberately does not fall back to a sandbox sender or demo delivery because
parent OTP success must prove real inbox delivery.

Complete split-secret example:

```bash
modal secret create littlenet-web-secrets --force \
  DATABASE_URL="postgresql://..." \
  SECRET_KEY="<long-random-flask-secret>" \
  AI_SERVICE_URL="https://<modal-ai-web-url>" \
  AI_SHARED_SECRET="<same-shared-secret>" \
  BASE_URL="https://<public-littlenet-web-url>"
```

```bash
modal secret create littlenet-r2 --force \
  R2_ACCOUNT_ID="<cloudflare-account-id>" \
  R2_ACCESS_KEY_ID="<r2-access-key>" \
  R2_SECRET_ACCESS_KEY="<r2-secret-key>" \
  R2_BUCKET="<private-bucket-name>" \
  R2_SIGNED_URL_TTL="600"
```

```bash
modal secret create littlenet-email --force \
  RESEND_API_KEY="<resend-api-key>" \
  RESEND_WEBHOOK_SECRET="<resend-webhook-signing-secret>" \
  RESEND_FROM_EMAIL="no-reply@littlenet.in" \
  RESEND_FROM_NAME="LittleNet"
```

The release preflight validates the database/schema, quiz bank, AI
configuration, Presidio PII detection, MediaPipe liveness assets, public
`BASE_URL`, Resend readiness, R2 bucket access and the configured
video-delivery provider. If Stream is disabled, the private R2 fallback is the
accepted provider; if Stream is enabled, its API configuration must pass.

## Canonical release sequence

Prefer the connected workflow **Deploy & Validate LittleNet Live**
(`.github/workflows/deploy-modal.yml`, manual dispatch). It runs, in order:

```text
Modal auth validation
→ AI deploy (modal_ai.py)
→ web deploy (modal_web.py)
→ PostgreSQL init/migrations          (modal run modal_web.py --init-db)
→ compulsory quiz seed                 (modal run modal_web.py --seed)
→ T4 model warm/validation             (opt-in: modal run modal_ai.py --confirm-gpu-warmup)
→ DB/AI/Presidio/liveness/mail/R2/BASE_URL preflight
→ public /healthz + strict /readyz
→ Playwright browser smoke
→ live-URL Android APK build           (LittleNet-live-verified-apk artifact)
```

The inexpensive runtime/configuration gates deliberately run before the T4
model warm step, so GPU credits are never spent on a release that would later
fail for missing database, mail, R2, or public URL configuration. The release
fails immediately if any dependency is missing or degraded; a final APK is not
produced from a degraded deployment.

### Database migrations — the exact order

**dbmate is the single migration owner** (`db/migrations/`, 22 migrations).
`tools/init_db.py` applies only the blessed legacy baseline
(`database/schema.sql` → `database/upgrade.sql` →
`database/friendship_upgrade.sql`); everything after the 2026-09-06 adoption
boundary lives in dbmate migrations.

On a **fresh** database:

```bash
python tools/init_db.py
dbmate --no-dump-schema --migrations-dir db/migrations up
```

(`modal run modal_web.py --init-db` runs exactly this inside Modal.)

On an **existing** database:

```bash
dbmate --no-dump-schema --migrations-dir db/migrations up
```

Rules:

- Never run `dbmate up` alone on an empty database — migrations are deltas,
  not a full baseline.
- Never apply `database/upgrade.sql` directly (`tools/upgrade_db.py` is
  retired and fails loudly).
- `tools/init_db.py` is idempotent and never destructive; it errors loudly if
  `schema_migrations` records versions with no matching file in
  `db/migrations/` instead of papering over a broken history.
- New schema changes go in `db/migrations/` as timestamped files with both
  `-- migrate:up` and `-- migrate:down`; never edit an applied migration.

## Verify

```bash
curl --fail-with-body "$URL/healthz"   # HTTP 200
curl --fail-with-body "$URL/readyz"    # HTTP 200, {"status":"ready"}
curl --fail-with-body "$URL/api/mobile/v1/health"
```

Or in one shot: `modal run modal_web.py --preflight` (add `--deep-ai-probe`
only when you intentionally want to wake the T4).

## Final APK

The source repository does not contain the canonical final APK. Build it only
after the live workflow is green:

- Connected release: download the `LittleNet-live-verified-apk` Actions
  artifact from the **Deploy & Validate LittleNet Live** run.
- Standalone: `.github/workflows/build-local-apk.yml` (`[build-local-apk]`)
  builds against the Modal web URL and uploads the APK + SHA256 artifact.

Install on a real Android device and test: parent registration/OTP/camera
verification, child account creation, child face enrollment/login, safe and
blocked text/image/video uploads, private media loading, Parent Review and
controls, and camera/file permissions in the Android WebView.

## Enabling Cloudflare Stream later

Stream is optional and off by default. When real Stream credentials exist:

1. Add the `CLOUDFLARE_STREAM_*` keys (above) to the `littlenet-r2` secret with
   `CLOUDFLARE_STREAM_ENABLED=1`.
2. Redeploy the web app (`modal deploy modal_web.py` or the release workflow).
3. Confirm the preflight's `video_delivery` check reports the Stream provider.

Until then, video stays on the private sanitized R2 MP4 path — no code
changes needed either way.

## Manual diagnostic commands

```bash
python -m pip install -r requirements-modal.txt
modal token info
modal deploy modal_ai.py
modal run modal_ai.py --trained-image-preflight-only
modal run modal_ai.py --trained-text-preflight-only
modal deploy modal_web.py
modal run modal_web.py --init-db
modal run modal_web.py --seed
modal run modal_web.py --preflight
```

Cost-guarded AI helpers: `modal run modal_ai.py --prepare-face-cache-only`
(CPU), full T4 validation only via `modal run modal_ai.py --confirm-gpu-warmup`.

A judged demo should be warmed shortly before presentation to avoid GPU
cold-start latency, then allowed to scale down afterward.

## Cost behavior

The heavy AI deployment scales to zero when idle with a short warm tail, so
demo usage does not burn GPU credits. Ordinary image/text moderation runs on
scale-to-zero CPU functions; GPU fallback is deliberately disabled so a
transient CPU issue cannot silently spend T4 credit — the pipeline fails
closed instead.

## Legacy adapters (not production)

- `railway.toml` → `Dockerfile.web`: Railway demo path, see
  `DEPLOYMENT_FREE.md` (optional, legacy).
- `cloudbuild.web.yaml`: Cloud Run build/deploy experiment
  (`asia-southeast1`), not wired to any release workflow.
- `Dockerfile`: all-in-one legacy image.
- `Dockerfile.ai`: standalone AI container (the Modal AI app supersedes it).

These are kept as functional adapters. Do not treat any of them as the
production target.
