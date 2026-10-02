# LittleNet — Child-Safe Social & Learning Platform

> Canonical setup and local-development guide for the LittleMuse repository.

LittleNet is a child-safe social and learning platform for children aged 6–16. The project combines a familiar social experience with parent-owned controls, approved relationships, learning/quiz gates, private media handling, and server-side content moderation.

The active native client is React Native + Expo in mobile_app/. The authority for authentication, moderation, parent controls, screen time, quiet hours, relationships, safety review, and publication remains in the Flask backend.

This README is the starting point for a fresh clone. A new developer should be able to bring up the backend, database, web UI, and mobile development client by following the Local Setup section in order.

---

## 1. Current stack

| Layer | Technology |
| --- | --- |
| Mobile | React Native 0.86.x, Expo SDK 57, React 19.2.x, TypeScript |
| Backend | Python 3.11, Flask |
| Database | PostgreSQL 16; pgvector-compatible PostgreSQL is recommended |
| Media | Cloudflare R2 in deployed environments; guarded local mock upload path for development |
| AI / moderation | Server-side deterministic checks + text/image/video moderation; Modal is the production compute tier |
| Email | Resend in deployed environments; console-visible development OTP is available locally |
| Database migrations | Legacy baseline bootstrap + dbmate migrations |
| Android package | com.littlenet.app |

The top-level requirements.txt is retained for compatibility, but the pinned split requirement files are the canonical dependency source for current development:

- requirements-core.txt
- requirements-text.txt
- requirements-safety.txt
- requirements-ai.txt

---

## 2. Architecture

~~~text
React Native / Expo mobile app
          mobile_app/
              |
              | HTTP/HTTPS + bearer auth
              v
       Flask application
      app.py + mobile/
        /api/mobile/v1
        /api/mobile/v2
              |
       +------+-------------------+
       |                          |
 PostgreSQL / Neon          Private media
                           Cloudflare R2
       |                          |
       +----------+---------------+
                  |
          moderation jobs
       local queue in development
        Modal in production
                  |
          Parent/Admin review
~~~

Important boundaries:

- The client never grants itself parent permissions, safety approval, screen-time access, or publication rights.
- Parent controls are re-checked by the server.
- New child media is not treated as published merely because it was uploaded.
- Production secrets never belong in the Expo environment.
- The only public mobile configuration value is EXPO_PUBLIC_API_BASE_URL.

---

# Local Setup

## 3. Prerequisites

Install these before starting:

| Requirement | Recommended version |
| --- | --- |
| Git | Current stable |
| Git LFS | Current stable |
| Python | 3.11 |
| Node.js | 22.13.0 or newer |
| npm | Version bundled with supported Node |
| PostgreSQL | 16 with pgvector support |
| dbmate | 2.34.1 |
| FFmpeg | Current stable |
| Docker | Optional, but recommended for the local PostgreSQL database |

For Android development you will also need either Expo Go / a compatible development runtime, or Android Studio + Android SDK if you want to run a native development build.

Verify the main tools:

~~~bash
git --version
git lfs version
python --version
node --version
npm --version
ffmpeg -version
dbmate --version
~~~

---

## 4. Clone the repository and fetch model files

~~~bash
git clone https://github.com/littlenet655-sketch/littlemuse.git
cd littlemuse

git lfs install
git lfs pull
git lfs ls-files
~~~

Git LFS is required because trained model artifacts are not stored as ordinary Git blobs.

The current CI specifically expects real binaries for model artifacts including:

~~~text
models/littlenet_core_safety_v2.pth
models/littlenet_weapons_violence_v3.pth
models/littlenet_text_safety/model.safetensors
~~~

If one of those files contains text beginning with:

~~~text
version https://git-lfs.github.com/spec/v1
~~~

then you have an LFS pointer instead of the actual model. Run git lfs pull again after confirming Git LFS is installed and authenticated.

---

## 5. Start a local PostgreSQL database

### Recommended: PostgreSQL + pgvector with Docker

Run this once:

~~~bash
docker run --name littlenet-postgres \
  -e POSTGRES_USER=littlenet \
  -e POSTGRES_PASSWORD=littlenet \
  -e POSTGRES_DB=littlenet_dev \
  -p 5432:5432 \
  -v littlenet_pgdata:/var/lib/postgresql/data \
  -d pgvector/pgvector:pg16
~~~

On Windows PowerShell, the same command can be entered on one line:

~~~powershell
docker run --name littlenet-postgres -e POSTGRES_USER=littlenet -e POSTGRES_PASSWORD=littlenet -e POSTGRES_DB=littlenet_dev -p 5432:5432 -v littlenet_pgdata:/var/lib/postgresql/data -d pgvector/pgvector:pg16
~~~

For later sessions:

~~~bash
docker start littlenet-postgres
~~~

Check that PostgreSQL is ready:

~~~bash
docker exec littlenet-postgres pg_isready -U littlenet -d littlenet_dev
~~~

The local connection string used in this README is:

~~~text
postgresql://littlenet:littlenet@127.0.0.1:5432/littlenet_dev?sslmode=disable
~~~

You can use an existing PostgreSQL/Neon database instead, but use a disposable development database. Do not point local bootstrap commands at a retained production database.

---

## 6. Create the Python virtual environment

### Windows PowerShell

~~~powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
~~~

### macOS / Linux

~~~bash
python3.11 -m venv .venv
source .venv/bin/activate
~~~

Upgrade packaging tools:

~~~bash
python -m pip install --upgrade pip setuptools wheel
~~~

---

## 7. Install backend dependencies

### Full local feature set

For the closest local equivalent to the current application, install both the AI/text stack and the safety stack:

~~~bash
python -m pip install -r requirements-ai.txt -r requirements-safety.txt
python -m spacy download en_core_web_sm
~~~

This installs the current pinned core, text, OCR, visual-safety, and media moderation dependencies. It is a large installation because it includes PyTorch/Transformers and computer-vision packages.

### Lightweight backend-only development

If you only need the Flask application, database routes, source work, or API development and do not need complete local ML inference:

~~~bash
python -m pip install -r requirements-core.txt
~~~

For parent onboarding or child-account creation flows, also install the text stack:

~~~bash
python -m pip install -r requirements-text.txt
~~~

Parent onboarding runs server-side text moderation on the child profile. Without the text dependencies, that safety step fails closed rather than silently creating an unchecked child account.

The application is designed to fail closed when required safety evidence is unavailable. Therefore, media/text behavior with only the core dependencies is not equivalent to a fully configured moderation environment.

FFmpeg must still be installed on the system for video sanitization and video-processing tests.

---

## 8. Create the local backend environment

The committed .env.example is a production-oriented configuration reference. Do not copy it unchanged for localhost because it sets production mode, HTTPS expectations, secure cookies, and deployed-service settings.

Create a new file named .env in the repository root with a local configuration like this:

~~~dotenv
LITTLENET_ENV=development
BASE_URL=http://127.0.0.1:5000
COOKIE_SECURE=0

SECRET_KEY=PASTE_A_LOCAL_RANDOM_SECRET_HERE
DATABASE_URL=postgresql://littlenet:littlenet@127.0.0.1:5432/littlenet_dev?sslmode=disable
APP_TIMEZONE=Asia/Kolkata

# Local parent registration:
# the generated OTP is printed in the backend terminal.
ENABLE_DEV_OTP=1

# Allow the v2 upload flow to use a guarded local PUT endpoint when R2
# credentials are not configured. This path is unavailable in production.
ENABLE_MOCK_PUT=1

# Run media work locally instead of spawning Modal.
JOB_QUEUE_PROVIDER=local
LITTLENET_SYNC_JOBS=1

# Keep deployed/paid remote compute disabled for normal local development.
AI_SERVICE_URL=
AI_SHARED_SECRET=
AI_ENABLE_REMOTE_RANKING=0
LITTLENET_ENABLE_LOCAL_RECOMMENDATION_MODEL=0
LITTLENET_USE_MODAL_IMAGE_CPU=0
LITTLENET_ALLOW_IMAGE_GPU_FALLBACK=0
LITTLENET_USE_MODAL_TEXT_CPU=0
LITTLENET_ALLOW_TEXT_GPU_FALLBACK=0

# Keep optional external K2 calls disabled unless deliberately configured.
K2_HORIZON_ENABLED=false
~~~

Generate a local Flask secret with:

~~~bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
~~~

Paste the generated value into SECRET_KEY.

Do not commit .env.

### Optional local external integrations

You do not need Resend, Cloudflare R2, or Modal merely to boot the local backend.

Configure them only when you specifically want to test integration parity:

- Resend: RESEND_API_KEY, RESEND_WEBHOOK_SECRET, RESEND_FROM_EMAIL, RESEND_FROM_NAME
- Cloudflare R2: R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET
- Remote AI: AI_SERVICE_URL and matching AI_SHARED_SECRET
- Cloudflare Stream: keep CLOUDFLARE_STREAM_ENABLED=0 until the complete private playback path is intentionally configured

---

## 9. Install dbmate

LittleNet has two database initialization stages:

1. tools/init_db.py installs the blessed legacy baseline.
2. dbmate applies every post-adoption migration in db/migrations/.

Both stages are required on a fresh database.

The repository and CI currently pin dbmate 2.34.1. Install that release for your operating system and make the dbmate command available in your terminal.

The official v2.34.1 release provides Windows, Linux, and macOS binaries.

Verify:

~~~bash
dbmate --version
~~~

If you keep the Windows binary in the current folder rather than on PATH, replace dbmate in the commands below with:

~~~powershell
.\dbmate.exe
~~~

---

## 10. Initialize the fresh local database

Make sure DATABASE_URL is visible to the dbmate process.

### Windows PowerShell

~~~powershell
$env:DATABASE_URL="postgresql://littlenet:littlenet@127.0.0.1:5432/littlenet_dev?sslmode=disable"

python tools/init_db.py
dbmate --no-dump-schema --migrations-dir db/migrations up
dbmate --no-dump-schema --migrations-dir db/migrations status
~~~

### macOS / Linux

~~~bash
export DATABASE_URL="postgresql://littlenet:littlenet@127.0.0.1:5432/littlenet_dev?sslmode=disable"

python tools/init_db.py
dbmate --no-dump-schema --migrations-dir db/migrations up
dbmate --no-dump-schema --migrations-dir db/migrations status
~~~

A successful fresh setup requires both the baseline bootstrap and the dbmate migration step.

Do not run dbmate up alone on an empty database. The dbmate migrations are deltas and do not recreate the entire legacy baseline.

### Optional academic/demo seed

For the baseline demo quiz seed:

~~~bash
python tools/init_db.py --seed
~~~

The baseline bootstrap is designed to be idempotent, but local development should still use a disposable database.

---

## 11. Start the Flask backend

From the repository root, with the virtual environment active:

~~~bash
python app.py
~~~

The development server binds to:

~~~text
0.0.0.0:5000
~~~

Open the web application on the same computer:

~~~text
http://127.0.0.1:5000/
~~~

The server-side web UI is useful for checking Parent, Child, Admin, authentication, and database flows even before starting the React Native client.

---

## 12. Verify the backend

Primary local health check:

~~~bash
curl http://127.0.0.1:5000/healthz
~~~

Expected shape:

~~~json
{
  "status": "ok",
  "database": true
}
~~~

If the database is healthy, the endpoint should return HTTP 200.

The /readyz endpoint is intentionally stricter:

~~~bash
curl http://127.0.0.1:5000/readyz
~~~

A local /readyz response can be degraded when production-only services such as Resend or a configured remote AI service are intentionally absent. Do not confuse that with a failed Flask/PostgreSQL boot. For ordinary localhost work, /healthz is the first check.

---

## 13. Local parent OTP flow

With:

~~~dotenv
LITTLENET_ENV=development
ENABLE_DEV_OTP=1
~~~

parent registration still generates the OTP in the backend, stores only its verification state/hash as designed, and prints the development OTP in the Flask terminal.

This allows local registration without a Resend account.

Development OTP is hard-disabled in production mode.

---

## 14. Run the React Native / Expo client

Open a second terminal:

~~~bash
cd mobile_app
npm ci
~~~

Create mobile_app/.env containing only the public backend URL.

### Android emulator

A common Android-emulator mapping for the host computer is:

~~~dotenv
EXPO_PUBLIC_API_BASE_URL=http://10.0.2.2:5000
~~~

### Physical phone on the same Wi-Fi

Use the development computer's LAN address, for example:

~~~dotenv
EXPO_PUBLIC_API_BASE_URL=http://192.168.1.50:5000
~~~

Replace the example IP with your actual computer IP and allow Python/port 5000 through the local firewall.

The Flask application already listens on 0.0.0.0, so another device can reach it when the network/firewall allows the connection.

The React Native client permits local/private HTTP only in development runtime. Android network policy can still reject cleartext traffic depending on the runtime/build being used. If that happens, expose the Flask server through a trusted HTTPS development tunnel and use that HTTPS URL instead.

### Production/release builds

Production mobile builds must use a public HTTPS backend. Localhost, private IP addresses, and cleartext HTTP are deliberately rejected by the production API configuration check.

### Start Expo

~~~bash
npm run typecheck
npm test
npx expo install --check
npm run start
~~~

Useful alternatives:

~~~bash
npm run android
npm run export:android
~~~

npm run android requires the Android native development toolchain.

---

## 15. Local media upload behavior

The current mobile media contract is the v2 direct-upload flow:

~~~text
POST /api/mobile/v2/uploads/session
        |
        v
PUT media to the returned upload URL
        |
        v
POST /api/mobile/v2/uploads/<upload_id>/complete
        |
        v
GET /api/mobile/v2/posts/<post_id>/processing-status
        |
        v
ALLOWED / REVIEW / BLOCKED
~~~

In deployed environments, the upload URL is a private Cloudflare R2 signed URL.

In non-production local development, when R2 is not configured and ENABLE_MOCK_PUT=1, the backend can return its guarded local mock-PUT endpoint instead. This lets the real v2 workflow be exercised without making a development R2 bucket mandatory.

With:

~~~dotenv
JOB_QUEUE_PROVIDER=local
LITTLENET_SYNC_JOBS=1
~~~

media-processing work runs locally and synchronously, which makes localhost debugging predictable.

Production never silently falls back to this local path.

---

## 16. Optional demo accounts

The repository contains tools/seed_demo_accounts.py for an isolated demonstration database.

It is deliberately guarded. To use it, set both:

~~~dotenv
LITTLENET_ENABLE_DEMO_SEED=1
LITTLENET_DEMO_PASSWORD=USE_A_NON_COMMITTED_PASSWORD_OF_AT_LEAST_12_CHARACTERS
~~~

Then run:

~~~bash
python tools/seed_demo_accounts.py
~~~

Use this only against a disposable/local demo database. The script creates or updates repository-defined demonstration identities and relationships and is not a production provisioning mechanism.

---

## 17. Environment-variable guide

### Local essentials

| Variable | Local value / purpose |
| --- | --- |
| LITTLENET_ENV | development |
| BASE_URL | http://127.0.0.1:5000 |
| DATABASE_URL | PostgreSQL development database |
| SECRET_KEY | Random local secret |
| COOKIE_SECURE | 0 for plain localhost HTTP |
| APP_TIMEZONE | Asia/Kolkata unless deliberately testing another timezone |

### Local development helpers

| Variable | Purpose |
| --- | --- |
| ENABLE_DEV_OTP=1 | Prints development parent OTP to backend terminal |
| ENABLE_MOCK_PUT=1 | Enables guarded local v2 upload PUT route |
| JOB_QUEUE_PROVIDER=local | Uses the local job queue |
| LITTLENET_SYNC_JOBS=1 | Runs local processing synchronously |

### Deployment-only / optional integrations

| Area | Variables |
| --- | --- |
| Resend | RESEND_API_KEY, RESEND_WEBHOOK_SECRET, RESEND_FROM_EMAIL, RESEND_FROM_NAME |
| Cloudflare R2 | R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET, R2_SIGNED_URL_TTL |
| AI service | AI_SERVICE_URL, AI_SHARED_SECRET |
| Cloudflare Stream | CLOUDFLARE_STREAM_* |
| K2 Horizon | K2_HORIZON_* |

Never put database credentials, R2 credentials, mail credentials, Modal credentials, Flask secrets, or AI shared secrets into mobile_app/.env.

---

## 18. Mobile API contract

The client uses two API generations intentionally.

### /api/mobile/v1

Used for authentication and remaining stable application capabilities such as:

- login/session
- parent registration and verification
- profile/account data
- parent controls and time limits
- safety queues and review
- relationships
- chat and social actions where no v2 replacement exists

### /api/mobile/v2

Used for current feed/reels/discover behavior and the direct media workflow, including:

- feed and reels
- discover
- impressions/recommendation signals
- direct post/reel/story upload sessions
- processing status/redrive
- chat media upload sessions
- device registration

The legacy synchronous mobile post upload endpoint is retired. New media must use the v2 quarantine/processing contract.

---

## 19. Important directories

~~~text
mobile_app/       React Native / Expo / TypeScript native client
mobile/           Bearer-authenticated mobile API routes
auth/             Authentication, parent OTP, account provisioning
child/            Child feed, search, discovery and profile logic
childMessage/     Approved-only child messaging
parent/           Parent dashboard, controls and review flows
admin/            Admin/moderator services and routes
quiz/             Onboarding and recurring learning/quiz gates
safety/           Text, visual, PII and moderation services
services/         Media, storage, queue, controls, usage and shared services
database/         Legacy PostgreSQL baseline schema
db/migrations/    dbmate-owned post-adoption migrations
models/           Git-LFS-managed trained model artifacts
tools/            Bootstrap, audit, seed and release utilities
tests/            Backend and contract regression suites
docs/             Architecture, demo, release and operational documentation
uploadPost/       Existing web post/story/reel pipeline
~~~

---

# Validation

## 20. Backend validation

For the full test suite, install test-only dependencies if they are not already available:

~~~bash
python -m pip install "pydantic>=2,<3" pytest
~~~

Then run:

~~~bash
python -m pytest tests/ -q
python tools/audit_all.py
python tools/audit_dynamic_sql.py
python tools/scope_check.py
python tools/readiness.py
~~~

The current readiness script is invoked as python tools/readiness.py. It does not use a --source-only argument.

For database-backed tests, keep DATABASE_URL pointed at a disposable development/test database.

---

## 21. Mobile validation

~~~bash
cd mobile_app

npm ci
npm run typecheck
npm test
npm run export:android
npx expo install --check
~~~

These match the core React Native gates used by the repository CI.

---

## 22. Common local problems

### PostgreSQL connection refused

Confirm the local container/service is running:

~~~bash
docker start littlenet-postgres
docker exec littlenet-postgres pg_isready -U littlenet -d littlenet_dev
~~~

Also confirm DATABASE_URL uses the correct host, port, username, password, and database.

### "relation does not exist" / a newer table is missing

A fresh database needs both stages:

~~~bash
python tools/init_db.py
dbmate --no-dump-schema --migrations-dir db/migrations up
~~~

Running only tools/init_db.py is not a complete current schema installation.

### dbmate cannot connect

Make sure DATABASE_URL is exported into the shell that runs dbmate. Python loads .env through python-dotenv, but command-line programs must also be given the database URL in their environment.

### Model file looks like a tiny text file

Git LFS did not materialize the binary:

~~~bash
git lfs install
git lfs pull
git lfs ls-files
~~~

### Parent OTP email is not arriving locally

For localhost, do not require Resend. Set:

~~~dotenv
LITTLENET_ENV=development
ENABLE_DEV_OTP=1
~~~

Register again and read the generated OTP from the Flask terminal.

### Mobile app cannot reach localhost

127.0.0.1 inside a phone/emulator refers to that device, not the development computer.

Use:

- Android emulator: typically http://10.0.2.2:5000
- Physical phone: the computer's LAN IP on the same network
- If cleartext HTTP is blocked: a trusted HTTPS development tunnel

### Upload returns a storage-configuration error

For local no-R2 development, confirm:

~~~dotenv
LITTLENET_ENV=development
ENABLE_MOCK_PUT=1
JOB_QUEUE_PROVIDER=local
~~~

For deployed environments, configure real private R2 credentials instead. Production does not allow the mock storage path.

### /readyz returns 503 but /healthz is healthy

/readyz includes stricter dependency readiness, including configured mail/AI behavior. A minimal local environment may intentionally omit those deployed services.

Use /healthz first to prove Flask + PostgreSQL are running, then configure the additional service you specifically want to test.

### Video processing fails

Confirm FFmpeg is on PATH:

~~~bash
ffmpeg -version
~~~

Video sanitization is fail-closed.

---

# Production and deployment

## 23. Local setup is not the production release procedure

For a fresh local database, this README intentionally uses:

~~~text
tools/init_db.py
then
dbmate ... up
~~~

For an existing data-bearing production/retained Neon database, do not blindly rerun the legacy baseline as a migration shortcut.

The canonical production target is Modal and the production release procedure is documented in:

- MODAL_DEPLOYMENT.md
- docs/DATABASE_RELEASE_RECONCILIATION.md
- FINAL_DEPLOYMENT_CHECKLIST.md
- docs/PHYSICAL_DEVICE_CHECKLIST.md

The retained-database workflow performs migration-history checks before applying reviewed dbmate deltas.

---

## 24. Additional project documentation

Start here after the local environment is working:

- docs/FINAL_ARCHITECTURE.md — runtime boundaries and authoritative architecture
- docs/DEMO_RUNBOOK.md — predictable demo sequence and recovery steps
- docs/KNOWN_LIMITATIONS.md — current verified limitations
- docs/FINAL_E2E_MATRIX.md — execution/evidence matrix
- MODAL_DEPLOYMENT.md — canonical cloud release procedure
- STACK.md — locked technology stack

---

## 25. Safety and security principles

LittleNet intentionally follows these rules:

- Fail closed when required safety evidence is unavailable.
- Keep parent controls server-enforced.
- Keep child media private until the backend reaches an allowed publication state.
- Require approved relationships for restricted child interaction.
- Keep production credentials out of the mobile bundle.
- Never enable development OTP or mock upload behavior in production.
- Never make the R2 bucket public to simplify media delivery.
- Never treat a source-code test as proof of a live cloud or physical-device result.
- Use disposable databases for local/demo mutation and tests.
- Keep secrets in uncommitted .env files or deployment secret stores.

---

## Quick-start command map

After prerequisites are installed, the normal first localhost run is:

~~~text
1. git clone + git lfs pull
2. start PostgreSQL/pgvector
3. create and activate Python 3.11 virtual environment
4. pip install -r requirements-ai.txt -r requirements-safety.txt
5. python -m spacy download en_core_web_sm
6. create the development .env shown above
7. python tools/init_db.py
8. dbmate --no-dump-schema --migrations-dir db/migrations up
9. python app.py
10. open http://127.0.0.1:5000/
11. cd mobile_app && npm ci
12. set mobile_app/.env with EXPO_PUBLIC_API_BASE_URL
13. npm run start
~~~

If step 8 is skipped, the database is not fully current. If Git LFS is skipped, trained model files may be pointer stubs. If the mobile API URL is 127.0.0.1 on a physical phone, the phone will not reach the computer.

That is why the order above is the canonical local setup sequence.
