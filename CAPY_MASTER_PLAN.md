# LittleNet — Capy Completion Master Plan

## Objective
Finish LittleNet as a production-like college major-project app using the existing architecture. Do not replace the backend stack, do not deploy cloud services during implementation, and do not add speculative features outside the locked scope.

Current final architecture:
- Mobile: React Native + Expo (`mobile_app/`)
- Backend/API: existing Flask/Python app
- Database: Neon PostgreSQL
- Media: Cloudflare R2
- Email: Resend
- Background jobs: Modal-native async worker (no QStash)
- Heavy AI: Modal T4, scale-to-zero, used only for image/video/face workloads
- Source of truth: GitHub `main`

## Non-negotiable guardrails
1. NEVER deploy Modal, Vercel, Railway, Replit, Neon, R2, or any production service.
2. NEVER create, rotate, print, commit, or expose secrets.
3. NEVER push directly to `main`; use isolated branches/PRs.
4. NEVER delete working backend features just to simplify the mobile app.
5. NEVER reintroduce Flutter, WebView wrappers, duplicate Android roots, QStash, or legacy mobile source.
6. Preserve existing APIs where practical. Add missing mobile API contracts instead of bypassing backend rules.
7. Keep child-safety gates fail-closed: onboarding quiz, parent controls, quiet hours, moderation, approved-only interaction.
8. Keep GPU usage bounded: no automatic model warm-up; no health/readiness path may wake T4 by default.
9. All changes require tests and must keep `python tools/audit_all.py` passing.
10. Do not claim a feature is complete unless its real mobile flow is implemented and tested end-to-end.

## Known current state
- Backend is substantially implemented.
- `mobile_app/` is still only a React Native foundation/connectivity shell and needs the real app screens/navigation/state.
- Mobile API backend already contains a large number of auth/social/quiz/parent/admin routes.
- Existing source audits currently pass.
- Modal AI scale-to-zero and model cache are already configured; do not modify unless required by a failing contract.

## Completion definition
A fresh user must be able to complete this full path:

Parent signup -> email OTP (device auth gates Parent Mode) -> create child -> child password login -> onboarding quiz -> Kids feed -> stories/reels/discover -> profile -> create image/video post -> moderation -> processing status -> post appears in own profile and eligible feeds -> likes/comments/save/follow -> chat -> recurring quiz -> parent controls/review/screen-time -> admin review.

The app is not complete until this path works from React Native against the real backend contract.

---

# Workstream 1 — React Native application shell

Build the real app in `mobile_app/`.

Required:
- React Navigation or equivalent stable navigation stack.
- Persistent auth/session state.
- Secure token storage using Expo SecureStore or equivalent.
- Role-aware routing: Parent, Child/Kids, Admin.
- Loading/error/empty/offline states.
- Shared API client with bounded timeouts, auth header, standardized errors.
- Query/data caching appropriate for feed/profile/chat refresh.
- No WebView-based primary UI.

Acceptance:
- cold launch routes correctly based on auth state and role.
- logout clears tokens and caches.
- expired/invalid token returns user to login safely.

# Workstream 2 — Parent signup and guardian onboarding

Implement mobile screens and API bindings for:
- Parent registration.
- Email OTP request/verify/resend.
- Login/password reset.
- Child account creation.
- Parent dashboard entry after successful setup.

Acceptance:
- duplicate username/email errors render correctly.
- OTP states are resumable.
- guardian verification fails safely when unavailable/invalid.
- child cannot become usable until required verification is complete.

# Workstream 3 — Child authentication

Implement:
- Child password login UI.
- failed-login and locked-account handling.
- credential entry and password visibility UX.
- clear login-error messaging.

Acceptance:
- successful login creates working mobile auth/session state.
- wrong credentials fail with a generic, non-enumerating error.

# Workstream 4 — Quiz system

Implement complete mobile quiz flows:
- onboarding/age-banded quiz.
- recurring feed quiz gate.
- question rendering.
- answer submission.
- points/result/progress UI.
- automatic return to the intended destination after completion.

Acceptance:
- child cannot bypass a required quiz.
- quiz completion unlocks feed as expected.
- recurring quiz triggers at backend-defined interval.
- refresh/relaunch preserves correct gate state.

# Workstream 5 — Kids social experience

Implement polished mobile screens for:
- Home feed.
- Stories.
- Reels.
- Discover/search.
- Child profile.
- Other-child profile.
- likes/comments/save.
- follow/request/unfollow.
- notifications where backend contract exists.

Feed/profile consistency requirements:
- once a post reaches `ALLOWED`, it must appear in the author's profile.
- it must appear in eligible followers/discover/feed views according to backend visibility rules.
- mutations invalidate/refetch relevant queries immediately.

# Workstream 6 — Posting and media pipeline

Implement end-to-end image/video posting:
1. select/capture media.
2. optional caption/tags/category.
3. optional `location_label` text field only; do not store precise child coordinates.
4. direct/private upload flow using existing R2 upload-session contract.
5. mark upload complete.
6. poll processing status with sane backoff.
7. show PROCESSING/REVIEW/BLOCKED/ALLOWED UI.
8. on ALLOWED refresh profile/feed automatically.

Location rule:
- support manual coarse text such as `Koramangala, Bengaluru`.
- optional future one-time coarse reverse geocode is acceptable only if exact coordinates are discarded and never exposed.
- no live location sharing.

Acceptance:
- unsafe media cannot become publicly visible before moderation.
- failed processing gives actionable retry state.
- allowed media appears in profile/feed without app restart.

# Workstream 7 — Messaging/chat

Implement complete child chat UI against existing interaction rules:
- conversation list.
- one-to-one chat.
- text send.
- supported media send if backend route exists.
- polling/refresh or backend-supported update strategy.
- unread/read state where supported.
- blocked/disabled-by-parent/interaction-not-approved states.
- parent safety review visibility where backend supports it.

Acceptance:
- only backend-approved child relationships can interact.
- unsafe media/text follows moderation policy.
- messages render in correct order after relaunch.

# Workstream 8 — Parent controls

Implement parent mobile UI for:
- child overview.
- safety/review queue.
- screen-time status/limits.
- quiet hours.
- feature toggles (reels, stories, messaging, posting, discover as supported).
- category controls.
- pending follow approvals.
- child activity/behavior summaries where available.

Acceptance:
- child app reflects control changes without requiring reinstall.
- disabled features return correct UX rather than broken navigation.

# Workstream 9 — Admin/moderator

Implement required admin screens/contracts for:
- open moderation events.
- review/resolve action where backend supports it.
- account/content oversight needed for the college demo.

Do not invent an enterprise admin suite outside backend capabilities.

# Workstream 10 — AI and moderation quality

Do not retrain models unless a concrete failing benchmark requires it.

Current policy:
- deterministic rules for obvious grooming/sexual/bullying text.
- CPU-friendly checks where possible.
- Modal T4 only for heavy image/video/face inference.
- image/video moderation must fail closed when total safety inference fails.
- scene-aware video sampling remains bounded.

Improve accuracy through:
- test fixtures for safe/unsafe/borderline examples.
- threshold/regression tests.
- ensemble signal validation.
- better failure handling.
- optional external moderation adapter only behind a clean interface and only if it materially reduces GPU use or improves coverage.

If an external API is recommended, do not add its secret. Instead create `.env.example` names and document exactly what key is needed and why.

# Workstream 11 — Performance

Targets for college demo:
- first useful mobile screen should render quickly after auth.
- feed should paginate and avoid downloading full-resolution video/image unnecessarily.
- use thumbnails/posters for lists.
- lazy-load reels/stories.
- cache signed media URLs only within expiry.
- avoid aggressive polling.
- chat/feed polling must be bounded and paused in background.
- minimize web/backend cold-start work.
- no AI health polling that wakes GPU.

# Workstream 12 — Tests and evidence

Every implementation PR must add/adjust tests.

Mandatory final checks:
- `python tools/audit_all.py`
- `cd mobile_app && npm install`
- `npm run typecheck`
- `npm run export:android`
- backend route tests
- auth tests
- quiz tests
- feed/profile visibility tests
- upload/moderation state tests
- messaging interaction tests
- parent-control enforcement tests
- face error-path tests

Create a final `docs/FINAL_E2E_MATRIX.md` containing every major user journey and PASS/FAIL evidence.

# Captain execution strategy

Do not attempt the whole project in one edit.

Captain should first produce a gap inventory comparing:
- backend route/contracts
- React Native screens/components
- tests
- database schema
- moderation/job flow

Then delegate 3–5 non-overlapping implementation tasks at a time.

Recommended order:
1. mobile shell/auth/API contract
2. parent + child onboarding/face/quiz
3. kids feed/profile/social
4. posting/R2/moderation lifecycle
5. chat
6. parent/admin
7. performance/polish
8. full E2E regression

Merge only after review and CI. Resolve conflicts centrally through Captain.

# Replit handoff criteria

Do NOT hand the repo to Replit for finalization until:
- all Capy implementation PRs are merged to `main`.
- source audits pass.
- React Native Android export passes.
- `docs/FINAL_E2E_MATRIX.md` shows all code-level journeys ready.
- no TODO/FIXME remains on critical paths.

Replit's role is final integration/runtime validation only:
- install dependencies.
- configure provided secrets/environment.
- connect to deployed backend.
- run the app.
- fix environment-specific integration issues.
- produce final Android build/APK through the chosen Expo/EAS/Gradle path.

Replit must not redesign the architecture or replace working services.

# Final cloud deployment rule

Cloud changes happen only after the codebase is complete locally/CI.
Final intended sequence:
1. merge all reviewed PRs.
2. deploy Modal AI once if code changed.
3. deploy Modal web once.
4. apply DB migrations once.
5. seed quizzes once/idempotently.
6. passive readiness checks.
7. build Android APK.
8. run controlled end-to-end test.
9. check Modal billing and ensure idle containers return to zero.

No repeated deployment cycle during feature development.
