> **HISTORICAL VERIFICATION SNAPSHOT — NOT CURRENT RELEASE STATUS.** This file records an earlier tested baseline and is retained for traceability. For the current React Native architecture, parent email-OTP + Android device-auth flow, trained-model release gates, and present validation requirements, use `BUILD_STATUS.md`, `KNOWN_LIMITATIONS.md`, and the latest GitHub Actions run for the current commit.

# LittleNet Final Release Verification

**Purpose:** college-submission verification for the locked LittleNet Phase-II implementation  
**Verification baseline:** `main` commit `304f35052e033726b00e9b7e229141b42d32fd6c`  
**Date:** 08 September 2026

## 1. Scope lock

LittleNet is a child-safe social and learning platform implemented with Flask, PostgreSQL, HTML/CSS/JavaScript, AI-assisted safety checks, Face Login/liveness, Parent Mode, Admin/Moderator Mode, and an Android WebView wrapper.

The current college build intentionally uses this moderation scope:

- image moderation: enabled
- video visual moderation using sampled frames: enabled
- text/caption/comment/message moderation: enabled
- PII/contact-sharing protection: enabled
- contextual chat safety: enabled with fail-safe fallback
- standalone audio/voice uploads: **intentionally disabled**
- story music/audio uploads: **intentionally disabled**
- video audio: **stripped before persistence; not used as an active moderation modality**
- speech-to-text/Whisper runtime: **not part of the locked current build**

Older Phase-I/early Phase-II documents may describe speech transcription. Those references describe an earlier design and must not be presented as a current runtime feature.

## 2. Current automated verification

The `main` CI run for commit `304f35052e033726b00e9b7e229141b42d32fd6c` completed successfully with:

- Python regression suite: **331 passed, 1 skipped**
- preflight: **PASS**
- route audit: **130 routes, 0 errors**
- template audit: **76 templates, 0 errors**
- scope check: **53/53 PASS**
- dynamic SQL audit: **PASS**
- JavaScript syntax checks: **PASS**
- Android XML/source check: **PASS**
- MediaPipe liveness asset integrity: **PASS**
- Python security scan: **PASS**
- Gitleaks secret scan: **PASS**

The intentionally skipped test is the real-PostgreSQL role smoke in the ordinary unit job; that test is executed separately with a disposable PostgreSQL service in its dedicated CI workflow.

## 3. Real PostgreSQL role verification

A dedicated CI workflow creates PostgreSQL 16, applies the real LittleNet schema/upgrades, seeds disposable Child/Parent/Admin users, and verifies authenticated role behavior.

Verified behavior includes:

- Kids Mode protected route access with a valid CHILD session
- Parent Mode child usage access through an approved parent-child mapping
- Admin Mode protected route access with an ADMIN session
- role confusion does not grant Admin access to a child
- changing a parent account to `SUSPENDED` in PostgreSQL invalidates a stale signed Parent session on the next protected request

This gives database-backed authorization evidence in addition to mocked/unit tests.

## 4. Moderation fail-safe verification

The current moderation contract is:

- `ALLOW`: evidence is valid and risk is below configured thresholds
- `REVIEW`: ambiguous content or partial safety failure requires Parent Mode review
- `BLOCK`: hard safety violation or total safety failure

Critical hardening verified in the current build:

- empty or malformed AI envelopes cannot become zero-risk `ALLOW`
- malformed individual scores are routed safely rather than normalized as harmless evidence
- failed sampled video frames remain visible to the policy layer and cause safe review behavior
- required contextual chat evaluation runs even when the contextual provider is unavailable
- contextual `REVIEW` is recorded as the final moderation decision
- adult-content, grooming/secrecy patterns, severe abuse, PII/contact sharing, weapons and toxic text have server-side enforcement paths

## 5. Messaging and relationship authorization

Messaging is limited to currently approved interactions.

Verified hardening:

- an existing conversation does not bypass a later relationship revocation
- message reads re-check current relationship authorization
- sharing a post/media into chat requires an approved connection
- parent-reviewed messages are revalidated before approval is made visible
- blocked/revoked pairs cannot continue through an old conversation identifier

## 6. Parent Mode verification

Parent Mode includes:

- parent-first account flow
- child linkage/approval
- safety level settings
- content review for `REVIEW` decisions
- screen-time limit enforcement
- quiet hours
- activity/usage views
- notifications and safety alerts
- behavior/learning summaries

Canonical parent authorization requires an approved parent-child mapping and an ACTIVE parent account. Private child media access uses the same canonical ownership check.

**Known non-blocking consistency item:** some list views can under-display content for a verified secondary parent because their list query still uses the primary-parent field. The actual sensitive review/media authorization re-checks canonical ownership, so this is a display-consistency issue rather than an authorization bypass.

## 7. Screen-time verification

Server-side usage tracking is not based only on browser-local state.

Current hardening verifies that:

- missing/stale usage sessions are recreated server-side before the lock decision
- short activity segments are accumulated in seconds before conversion to displayed minutes
- the daily limit and strict-mode decision are evaluated server-side
- quiet-hours enforcement is server-side

## 8. Face Login and parent liveness

Current safety rules require positive evidence rather than inference from image dimensions.

Verified behavior:

- exactly one face is required for guardian/adult verification
- explicit positive liveness evidence is required
- missing/empty liveness evidence fails closed
- age values are evaluated without rounding a 17.x estimate into an adult result
- child Face Login/liveness source and pinned MediaPipe assets pass CI integrity checks

## 9. Social and learning features in scope

The scope checker reports PASS for the college features including:

- Kids Mode feed
- posts/upload
- Stories
- Reels/Clips
- messaging/chat
- Discover/recommended users
- likes/comments/sharing
- save/bookmark
- parent controls and safety review
- age-targeted/semantic feed support
- quizzes and learning challenges
- multilingual UI
- behavioral analysis
- Live Safety
- Admin/Moderator tools
- PostgreSQL activity logs
- R2 media adapter/privacy enforcement
- Android APK source

## 10. Android APK verification

The current `main` commit was compiled in GitHub Actions using Java 17, Gradle 8.9 and Android SDK/build-tools 35.

Current artifact:

- artifact name: `LittleNet-debug-apk`
- package: `com.littlenet.app`
- artifact ZIP size: **2,212,589 bytes**
- artifact digest: `sha256:f38cc4e79a14bcf7de405e2d735a5869f11716cf6aab853809ebbfb2c0c43f65`
- source commit: `304f35052e033726b00e9b7e229141b42d32fd6c`

The APK is configured to load the LittleNet HTTPS backend through the Android WebView wrapper and supports the mobile web camera/file flows exposed by that wrapper.

## 11. Submission ZIP verification

The main packaging workflow completed successfully and produced the clean submission artifact:

- artifact: `LittleNet-submission-ready`
- source commit: `304f35052e033726b00e9b7e229141b42d32fd6c`
- previous artifact digest: `sha256:6dc4a130129941a649b4d7a05bd9d50ca23e7679af5f04be33140a76a3b20e95`

A new package must be generated after this documentation-consistency update so the bundled documentation matches the locked audio-free scope.

## 12. Live Modal deployment status

The repository contains an automated deploy-and-validate workflow for Modal Web + Modal AI, database migrations, preflight, `/healthz`, `/readyz`, browser smoke, and a live-backend APK build.

The post-merge deployment for `304f35052e033726b00e9b7e229141b42d32fd6c` did **not** deploy because GitHub Actions has no configured values for:

- `MODAL_TOKEN_ID`
- `MODAL_TOKEN_SECRET`

The workflow stopped at credential verification before any deployment command executed. Therefore:

- source/CI/APK status: **verified**
- current-commit live Modal redeployment: **pending repository credential configuration**
- do not claim that the hosted Modal instance is running commit `304f350...` until the deployment workflow passes

## 13. College demo recommendation

For the final demonstration, use deterministic, pre-checked examples:

1. safe text/image -> `ALLOW`
2. toxic or contact-sharing text -> `BLOCK` or `REVIEW` as designed
3. unsafe visual/weapon sample -> safety decision
4. ambiguous item -> Parent Safety Review
5. approved child-to-child messaging
6. revoke/block relationship -> old conversation can no longer be used
7. screen-time/quiet-hours enforcement
8. Face Login/liveness flow
9. Admin/Moderator review/audit view
10. Android APK loading the same LittleNet backend

Do not demonstrate standalone audio/voice uploads or claim speech transcription is active in this locked build.

## 14. Final decision

### College source and APK: VERIFIED

The repository is suitable for continued final-year submission preparation based on its green source audits, 331-test regression suite, real PostgreSQL role smoke, 53/53 scope check, security scans, and current-commit Android build.

### Live release proof: PENDING ONE EXTERNAL CONFIGURATION

To complete exact hosted-release proof, configure the two Modal GitHub Actions secrets and rerun `Deploy & Validate LittleNet Live`. Only after that workflow passes should `/healthz`, `/readyz`, browser smoke and the live-backend APK be presented as current-commit deployment evidence.
