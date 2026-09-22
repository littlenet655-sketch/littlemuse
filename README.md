# LittleNet — Child-Safe Social & Learning Platform

LittleNet is a college major project for children aged 6–16. It combines a familiar social experience with parent-owned controls, age-banded learning breaks, approved-only interaction and server-side AI content safety.

## Canonical architecture

```text
React Native / Expo mobile app (`mobile_app/`)
                 |
                 | HTTPS + bearer auth
                 v
        Flask mobile APIs (v1 + v2)
                 |
      +----------+-----------+
      |                      |
PostgreSQL / Neon      Private R2 media
      |                      |
      +------ async ----------+
          durable outbox -> Modal AI
                    |
             Parent/Admin review
```

The Python backend is the authority for moderation, parent controls, screen time, quiet hours, relationship approval, safety review and media publication state.

## Mobile client

The only mobile application root is `mobile_app/`.

```bash
cd mobile_app
cp .env.example .env
npm install
npm run typecheck
npm test
npm run export:android
npx expo install --check
npm run start
```

Set:

```text
EXPO_PUBLIC_API_BASE_URL=https://YOUR-LITTLENET-BACKEND
```

Do not put database, R2, mail, AI or queue secrets in the mobile environment.

### Mobile API rules

- Authentication and remaining legacy-compatible endpoints: `/api/mobile/v1/*`
- Feed/reels/discover and direct media workflow: `/api/mobile/v2/*`
- New image/video upload flow:
  1. `POST /api/mobile/v2/uploads/session`
  2. upload directly to the returned R2 URL
  3. `POST /api/mobile/v2/uploads/<upload_id>/complete`
  4. poll `GET /api/mobile/v2/posts/<post_id>/processing-status`
  5. publish only after server-side moderation reaches an allowed state

## Backend development

```bash
python -m venv venv
# Windows: venv\Scripts\activate
# Linux/macOS: source venv/bin/activate
pip install -r requirements-core.txt
python tools/init_db.py
python app.py
```

Use `.env.example` as the backend configuration reference.

## Important directories

```text
mobile_app/       React Native / Expo / TypeScript client
mobile/           Bearer-auth mobile API
admin/            Admin/moderator services and web routes
auth/             Authentication and verification
child/            Child feed/discovery/profile logic
childMessage/     Approved-only messaging
parent/           Parent dashboard and controls
quiz/             Learning and quiz gates
safety/           AI safety and moderation services
services/         Media, controls, usage, queue and shared services
database/         PostgreSQL schema and migrations
uploadPost/       Existing post/reel/story web pipeline
```

## Validation

Backend/source checks:

```bash
python tools/audit_all.py
python tools/scope_check.py
python tools/readiness.py --source-only
```

Mobile checks:

```bash
cd mobile_app
npm install
npm run typecheck
npm run export:android
```

GitHub Actions contains separate backend/security and React Native validation workflows. A manual mobile release workflow is included for EAS once the repository variables/secrets for the Expo project are configured.

See [docs/FINAL_ARCHITECTURE.md](docs/FINAL_ARCHITECTURE.md), [docs/DEMO_RUNBOOK.md](docs/DEMO_RUNBOOK.md), [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md), and [docs/FINAL_E2E_MATRIX.md](docs/FINAL_E2E_MATRIX.md) for the submission architecture, predictable demo, recovery steps, limitations, and executed evidence.

## Safety principles

- Fail closed when safety evidence is unavailable.
- Keep parent controls server-enforced.
- Keep child media private until approved.
- Require approved relationships for restricted interaction.
- Never embed production credentials in the mobile client.
