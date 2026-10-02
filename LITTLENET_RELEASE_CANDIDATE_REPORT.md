# LittleNet College Submission Candidate Report

> **Historical snapshot.** This report predates the 2026-09-23 release-coherence
> hardening. Current release authority is `docs/ASTRA_RELEASE_LEDGER.md`,
> `docs/LITTLENET_MASTER_SPEC.md`, and `MODAL_DEPLOYMENT.md`.

**Date:** 08 September 2026  
**Scope:** final-year college project qualification  
**Baseline:** `main` commit `304f35052e033726b00e9b7e229141b42d32fd6c`

## Status

### SOURCE / DATABASE-BACKED ROLE TEST / APK: VERIFIED

### EXACT CURRENT-COMMIT LIVE MODAL DEPLOYMENT: PENDING CREDENTIAL CONFIGURATION

This distinction is intentional. LittleNet should be presented using evidence that has actually passed, not as “100% production verified.”

## 1. Verified evidence

The merged baseline has passed:

- 331 Python tests, with 1 database-service test intentionally skipped in the ordinary unit job
- dedicated real PostgreSQL Child/Parent/Admin role E2E
- preflight
- 130-route audit with 0 errors
- 76-template audit with 0 errors
- 53/53 scope check
- dynamic SQL audit
- Python dependency/application security checks
- Gitleaks secret scan
- (MediaPipe liveness asset check retired: face path removed 2026-09-22)
- Android APK compilation and package verification
- submission ZIP packaging

## 2. Current Android artifact

The current main commit was compiled by CI rather than relying on an old copied APK.

- workflow artifact: `LittleNet-debug-apk`
- package: `com.littlenet.app`
- artifact ZIP size: **2,212,589 bytes**
- digest: `sha256:f38cc4e79a14bcf7de405e2d735a5869f11716cf6aab853809ebbfb2c0c43f65`
- source commit: `304f35052e033726b00e9b7e229141b42d32fd6c`

## 3. Locked moderation scope

Current active safety paths:

- image moderation
- sampled video-frame moderation
- text moderation
- PII/contact-sharing protection
- contextual chat safety with deterministic/fail-safe fallback
- Parent Mode review
- moderation/audit records

Current intentionally disabled paths:

- standalone audio/voice upload
- story music/audio upload
- speech-to-text moderation

Video audio is stripped before persistence. Speech transcription belongs to an earlier design and is not a current release dependency.

## 4. Critical safety hardening completed

The final submission branch corrected reproduced issues including:

1. empty/malformed moderation output becoming harmless zero scores
2. sampled video frame failure disappearing during aggregation
3. contextual chat review not being recorded as the final decision
4. contextual safety being skipped when the optional provider was unavailable
5. old conversations being reusable after relationship revocation
8. short usage sessions losing time through per-session minute rounding
9. stale/missing server usage sessions weakening screen-time checks
10. inconsistent private parent-media authorization
11. moderator state and audit writes occurring outside one transaction

Regression tests now cover these paths.

## 5. Real PostgreSQL role test

The dedicated E2E workflow creates PostgreSQL 16 and applies the actual LittleNet database schema/upgrades.

It verifies:

- CHILD protected route behavior
- PARENT protected route behavior for an approved child
- ADMIN protected route behavior
- cross-role denial
- live account-status enforcement after a parent is suspended in the database

This test complements the unit suite with real database-backed authorization evidence.

## 6. Screen-time and parent controls

Current server-side behavior includes:

- usage session creation/heartbeat
- daily usage aggregation
- daily limit enforcement
- strict-mode lock
- quiet hours
- feature/category controls
- parent safety review
- parent notifications

Elapsed usage is accumulated in seconds before display-minute conversion so repeated short sessions do not disappear.

## 7. Identity verification (2026-09-22: face removed)

All face/biometric artifacts were removed from LittleNet. Parents are verified by
email OTP ownership plus an 18+ date-of-birth declaration and explicit guardian
consent, and Parent Mode is additionally gated by Android system authentication.
Children log in with a password, and a compulsory age quiz gates Kids Mode.

## 8. Current live-deployment blocker

The `Deploy & Validate LittleNet Live` workflow is configured to:

1. validate Modal credentials and the HTTPS URL
2. deploy Modal AI
3. deploy Modal Web
4. apply database schema/upgrades
5. seed quiz data
6. run cloud preflight
7. validate AI readiness
8. require public `/healthz` and `/readyz`
9. run Playwright browser smoke
10. compile an APK using the same verified live URL

The post-merge run stopped at step 1 because GitHub Actions received empty values for:

- `MODAL_TOKEN_ID`
- `MODAL_TOKEN_SECRET`

The exact error was `Missing MODAL_TOKEN_ID secret`.

No Modal deployment command ran, so the failure did not push a broken release. Configure the two repository secrets and rerun this workflow to complete hosted-current-commit proof.

## 9. Submission artifact status

The existing main packaging workflow successfully produced `LittleNet-submission-ready`. This documentation update exists because that earlier package still bundled stale speech/audio claims in a few Markdown verification files.

After this branch is merged, regenerate the package and use the newer artifact so code, README, viva material and verification documents all describe the same locked scope.

## 10. What to demonstrate to examiners

Recommended deterministic sequence:

- open Kids Mode
- show safe feed/profile/posting
- submit benign content and explain `ALLOW`
- submit a prepared unsafe visual/text example and explain `BLOCK`
- show an ambiguous `REVIEW` item in Parent Mode
- demonstrate parent controls, screen time and quiet hours
- show approved messaging
- show relationship revocation preventing further chat use
- show child password login + onboarding quiz gate
- show Admin/Moderator audit/moderation view
- run/install the current CI-built Android APK

Do not present standalone voice/audio moderation or speech transcription as active functionality.

## 11. Known non-blocking limitations

- video moderation samples frames rather than scanning every frame
- optional contextual AI behavior depends on runtime provider configuration
- a few secondary-parent list views can under-display records, although sensitive actions re-check canonical ownership
- the current main commit has not yet been redeployed to Modal because GitHub Actions lacks the Modal credentials

## 12. Final classification

**COLLEGE SUBMISSION CANDIDATE — VERIFIED SOURCE + APK, LIVE REDEPLOY PENDING**

This classification is stronger and more defensible than an unsupported “100% production ready” claim. The codebase has substantial automated proof and a current-commit APK; the final hosted proof becomes complete when the Modal credential configuration is restored and the deploy workflow passes end-to-end.
