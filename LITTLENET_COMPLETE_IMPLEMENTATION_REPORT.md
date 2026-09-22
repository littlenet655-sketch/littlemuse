# LittleNet Complete Implementation Report

**Project:** LittleNet — Child-Centric Social Platform with AI-Based Content Filtering  
**Project type:** Major/final-year college project  
**Current implementation:** React Native / Expo mobile client + Flask API + PostgreSQL  
**Verification date:** 08 September 2026

## 1. Project purpose

LittleNet is designed as a supervised social and learning environment for children. It combines familiar social features with server-side safety rules, parental controls, moderation decisions, learning activities, Face Login/liveness, and an Admin/Moderator console.

The current implementation is intentionally focused on the college-project scope rather than production-scale social-network infrastructure.

## 2. Current architecture

```text
Child / Parent / Admin React Native client
                     |
                     v
              Flask application
                     |
       +-------------+-------------+
       |             |             |
       v             v             v
 PostgreSQL      Safety layer   AI adapters
 users/posts/    policy +       visual/text/
 messages/etc.   moderation     contextual checks
       |
       v
 private media adapter / storage references
```

Main architectural principles:

- role-aware sessions for CHILD, PARENT and ADMIN
- PostgreSQL as the source of truth for account/relationship/control state
- moderation before unsafe content becomes normally visible
- `ALLOW`, `REVIEW`, `BLOCK` decision model
- Parent Mode for ambiguous review and child controls
- Android uses the same HTTPS Flask backend rather than a separate mobile backend

## 3. Authentication and account supervision

LittleNet separates the three roles and protects role-specific routes.

Implemented account protections include:

- parent registration/email verification flow
- parent-first child management/approval
- approved parent-child mapping
- child Face Login/liveness flow
- parent email-OTP activation plus Android system device authentication for Parent Mode
- live account-status validation on protected routes

A parent must have an ACTIVE account and an approved mapping to access protected child information through the canonical ownership check.

## 4. Kids Mode social features

The current Kids Mode includes:

- home/feed
- child profiles
- image/video/text posts
- Stories
- Reels/Clips
- likes and comments
- save/bookmark
- Discover/recommended children within restricted context
- approved child-to-child messaging
- post sharing in chat when relationship/content rules permit it
- notifications
- learning and quiz entry points

Discover is not intended to be a global stranger directory. Relationship and visibility checks are applied server-side.

## 5. Moderation system

### 5.1 Current active modalities

The locked college build supports:

- image moderation
- sampled video-frame moderation
- text/caption/comment/message moderation
- deterministic PII/contact-sharing detection
- contextual chat safety
- moderation event/audit storage

### 5.2 Audio scope decision

Standalone audio/voice uploads are intentionally disabled in the current build. Story music/audio uploads are also disabled. Video audio is stripped before persistence and is not an active safety modality.

Speech transcription/Whisper belongs to an earlier project design and is **not** required by the current locked implementation.

This decision keeps the final demo consistent with the code and avoids claiming a partially working speech pipeline.

### 5.3 Decision policy

LittleNet combines available safety evidence into three decisions:

- **ALLOW** — content can be published/shown normally
- **REVIEW** — parent review is required before normal visibility
- **BLOCK** — content is rejected/hidden under hard safety rules

The current policy is fail-safe:

- malformed or empty moderation evidence cannot silently become safe
- total safety failure routes to a hard safe outcome
- partial safety failure routes to review
- invalid score shapes are treated as safety errors rather than zero-risk values

## 6. Visual and video safety

Image safety uses the configured visual moderation pipeline to detect inappropriate visual content and harmful-object/weapon signals.

Video safety samples frames across the permitted short-video duration and aggregates the frame evidence. A failed sampled frame is preserved as a partial safety failure so it cannot disappear from the final policy decision.

This is a sampling-based college implementation, not a claim of frame-perfect inspection of every millisecond of arbitrary long-form video.

## 7. Text, PII and contextual chat safety

Text moderation is used for posts, captions, comments and messages.

Additional deterministic rules detect attempts to share personal/contact information such as phone numbers and off-platform contact details. Context-sensitive message patterns such as secrecy/contact requests can invoke contextual safety evaluation.

Important chat hardening:

- the current relationship is checked before using an existing conversation
- blocked/revoked relationships cannot keep communicating through an old conversation ID
- a contextual `REVIEW` result is recorded as the final moderation decision
- when contextual AI is unavailable, the safety fallback still executes instead of bypassing evaluation

## 8. Parent Mode

Parent Mode provides:

- child management
- safety review
- daily screen-time limits
- quiet hours
- feature/category controls
- activity and usage information
- notifications/safety alerts
- learning/quiz summaries
- behavior summaries

Screen-time enforcement is server-side. Missing usage sessions are recreated before the lock decision, and elapsed seconds are accumulated before conversion into displayed minutes.

## 9. Face Login and liveness

The face/liveness flow has been hardened so image dimensions alone cannot act as proof.

Current requirements include:

- exactly one detected face for adult verification
- explicit positive liveness evidence
- fail-closed behavior when liveness is missing
- age boundary checked without rounding a 17.x estimate to 18
- pinned MediaPipe liveness assets verified by CI integrity hashes

## 10. Learning features

The project includes age-group learning support such as:

- quizzes
- mandatory/onboarding quiz gates where configured
- learning challenges
- educational Reels/content entry points
- age-targeted content/feed logic
- multilingual UI/data support

These features use PostgreSQL-backed quiz/challenge data and the project’s configured AI/fallback services where applicable.

## 11. Admin / Moderator Mode

The Admin/Moderator console provides:

- user overview
- reports
- moderation-event review
- forced block of open REVIEW items
- post removal
- administrative audit logs

Moderator content-state changes and their audit evidence are committed together for the critical block/removal paths, reducing the chance of a state change occurring without matching audit evidence.

## 12. Database and authorization

PostgreSQL stores the main application state including:

- users and roles
- parent-child mappings
- posts/comments/likes/saves
- child relationships and blocks
- conversations/messages
- moderation events/reviews
- usage sessions/logs and time limits
- quizzes/learning data
- notifications and audit data

Database calls use parameterized values. Dynamic SQL usage is covered by a dedicated audit.

## 13. Android application

The Android client is the React Native / Expo project under `mobile_app/`. It calls the same HTTPS Flask APIs while keeping moderation, relationships, parent controls, and database authority server-side.

The current `main` commit `304f35052e033726b00e9b7e229141b42d32fd6c` was successfully compiled in GitHub Actions.

Verified artifact:

- package: `com.littlenet.app`
- release workflow: `.github/workflows/release-mobile.yml` (EAS preview APK, credential-gated)
- artifact ZIP size: 2,212,589 bytes
- digest: `sha256:f38cc4e79a14bcf7de405e2d735a5869f11716cf6aab853809ebbfb2c0c43f65`

## 14. Verification results

For the current merged baseline:

- backend regression count is taken from the current GitHub Actions run; do not reuse historical counts
- preflight: **PASS**
- route audit: **130 routes, 0 errors**
- template audit: **76 templates, 0 errors**
- route/source/security audits are enforced by CI; use only the current run as evidence
- dynamic SQL audit: **PASS**
- Python security scan: **PASS**
- secret scan: **PASS**
- MediaPipe asset integrity: **PASS**
- Android Expo export is CI-validated; final APK evidence must come from the current EAS release workflow
- clean submission-package workflow: **PASS**
- disposable PostgreSQL Child/Parent/Admin role smoke: **PASS**

The ordinary test job skips the real-PostgreSQL smoke because it needs a database service; the dedicated E2E workflow runs it separately.

## 15. Deployment status

The repository includes a Modal deployment workflow that can deploy web + AI services, apply database upgrades, run preflight, verify `/healthz` and `/readyz`, run a browser smoke test, and validate the live APIs; the separate EAS release workflow builds an APK against the configured HTTPS URL.

The latest post-merge deployment did not execute because the GitHub repository currently lacks:

- `MODAL_TOKEN_ID`
- `MODAL_TOKEN_SECRET`

The workflow failed at credential verification before any deployment command ran. Therefore the repository/source are verified, but the exact current `main` commit must not be claimed as live until the Modal workflow is rerun successfully after those secrets are configured.

## 16. Known limitations and honest viva framing

- video moderation uses sampled frames rather than every frame
- standalone audio/voice and story music uploads are outside the locked current build
- the project does not claim production-scale infrastructure or millions of concurrent users
- optional contextual AI depends on deployment configuration; deterministic/fail-safe rules remain in place
- a verified secondary parent can under-display items in a small number of list views even though sensitive media/review authorization uses the canonical ownership check

## 17. Final college-project status

LittleNet now has a coherent college-submission implementation with working social features, parental supervision, moderation policy, role authorization, Face Login/liveness, learning features, database persistence, Admin/Moderator controls, automated tests, security audits and a credential-gated current-commit Android release workflow.

For final submission, the remaining external release step is to configure the Modal GitHub Actions credentials and obtain a fully green live-deployment evidence run. The academic report/PPT should use the same locked scope described here and should not present speech transcription as an active feature.
