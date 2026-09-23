# LittleNet / LittleMuse — Canonical Modal Release Guide

_Last synchronized: 2026-09-23._

This is the single operational deployment guide. Historical reports are evidence
only; current source, CI contracts, this guide, and the release ledger control a
release.

## Canonical identities

- Web Modal app: `littlemuse-web`
- AI Modal app: `littlemuse-ai`
- Web secret: `littlemuse-web-secrets`
- AI secret: `littlemuse-ai-secrets`
- Upload volume: `littlemuse-uploads`
- Shared model cache: `littlenet-model-cache`
- Private R2 secret: `littlenet-r2`
- Email secret: `littlenet-email`
- R2 write namespace: `littlemuse/`
- Android package: `com.littlenet.app`
- Expo owner: `akshu1245s-team`
- EAS project: `c4ce834d-fd50-4504-a311-820c3372b6dc`

Modal names are environment-configurable in source, while the release workflow
pins these production values. CI tests prevent silent identity drift.

## Architecture

React Native + Expo Android → Flask API on `littlemuse-web` → PostgreSQL/Neon,
private R2 and Resend. Heavy AI lives in `littlemuse-ai` and scales to zero.
Ordinary image/text moderation uses the CPU tier where configured. Cloudflare
Stream is optional; private sanitized R2 MP4 is the fallback.

Face/liveness authentication is not in the locked product scope. Parent identity
uses email OTP + guardian declaration, Parent Mode uses Android system auth, and
children use password login plus the compulsory quiz gate.

## Required GitHub configuration

Actions secrets:

```text
MODAL_TOKEN_ID
MODAL_TOKEN_SECRET
EXPO_TOKEN
```

Repository variable:

```text
LITTLENET_LIVE_URL
```

The URL must be the current public HTTPS endpoint for `littlemuse-web`.

Before deployment, the workflow runs zero-GPU secret preflights. It requires the
web `AI_SERVICE_URL` to identify `littlemuse-ai` and compares non-disclosing
SHA-256 fingerprints of the web/AI `AI_SHARED_SECRET` values. A stale endpoint
or mismatched secret stops the release before cloud code is replaced.

## Runtime secret contracts

`littlemuse-ai-secrets`:

```text
AI_SHARED_SECRET
```

`littlemuse-web-secrets`:

```text
DATABASE_URL
SECRET_KEY
BASE_URL
AI_SERVICE_URL
AI_SHARED_SECRET
```

`AI_SERVICE_URL` must target `littlemuse-ai`; the shared secret must match
the AI secret.

`littlenet-r2`:

```text
R2_ACCOUNT_ID
R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY
R2_BUCKET
R2_SIGNED_URL_TTL
```

Keep `CLOUDFLARE_STREAM_ENABLED=0` until a real live Stream path is proven.

`littlenet-email`:

```text
RESEND_API_KEY
RESEND_WEBHOOK_SECRET
RESEND_FROM_EMAIL
RESEND_FROM_NAME
```

The release preflight must prove a real verified Resend sender.

## Retained database rule

dbmate owns post-adoption schema changes. A retained release database is never
blindly bootstrapped.

Before mutation:

1. verify a Neon restore point/branch;
2. run `modal run modal_web.py --migration-status-check`;
3. stop if history is untracked, contains unknown applied versions, or misses
   the dbmate adoption marker;
4. review every pending migration file;
5. run `modal run modal_web.py --migrate-db`;
6. rerun the status check and require `pending: []`.

The guarded migration path does not call the legacy baseline. For a genuinely
fresh database only, use `python tools/init_db.py` followed by dbmate.

See `docs/DATABASE_RELEASE_RECONCILIATION.md`.

## Video safety policy

Video moderation uses PySceneDetect plus uniform frame distribution with a hard
cost cap:

- minimum 3 frames;
- maximum 8 frames;
- target sample interval 8 seconds;
- auto-allow maximum temporal gap 12 seconds;
- longer clips that cannot satisfy the coverage contract within 8 frames stay
  private for REVIEW.

This avoids the unsafe single-frame auto-allow behavior without returning to an
unbounded/expensive frame scan.

## Connected release sequence

Use `.github/workflows/deploy-modal.yml`:

```text
validate Modal credentials + HTTPS URL
→ verify Git LFS model binaries
→ stage trained model volume
→ guarded DB history check (when migrate_database=true)
→ apply reviewed dbmate deltas (when migrate_database=true)
→ deploy littlemuse-ai
→ deploy littlemuse-web
→ idempotent quiz seed
→ trained image/text preflights
→ optional GPU warmup
→ strict DB/AI/PII/Resend/R2/video preflight
→ public health/readiness/mobile API checks
→ release evidence artifact
```

Do not repeatedly deploy during feature development.

## Mobile release

`mobile_app/app.json` is the EAS identity source. The workflow validates it
instead of injecting another owner/project at build time.

Required build gates:

```text
npm ci
npm run typecheck
npm test
npx expo install --check
EAS preview build against verified LITTLENET_LIVE_URL
download APK
verify APK integrity + SHA256
```

Then execute `docs/PHYSICAL_DEVICE_CHECKLIST.md` sequentially with one tester.
Only widen the tester base after that first run is clean.

## Evidence states

Use these states independently:

- IMPLEMENTED
- AUTOMATED_TESTED
- LIVE_SERVICE_VERIFIED
- DEVICE_VERIFIED
- BLOCKED
- MISSING

Source/tests never imply live or physical verification.


## Secondary workflow safety

The web-only workflow is an emergency code-only redeploy path. It does not apply
database migrations; it first requires web/AI identity parity, coherent retained
migration history, and zero pending migrations. If a schema change is pending,
use the canonical full release workflow instead.

The local Gradle APK workflow is diagnostic/secondary. It has no historical
backend fallback: `LITTLENET_LIVE_URL` must be explicitly configured, its mobile
health identity must be React Native, and the committed Expo/EAS/package identity
must match the canonical release identity.
