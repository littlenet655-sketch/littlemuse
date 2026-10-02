# Astra Changed File Inventory

Baseline PR #43 `f48aafa1bce0fb1344dfc8aec57f70770d8dfc0b` versus `origin/main` `3b5f3e5bad6781b9af5113c395e4750357c42c31`. Exactly 79 changed files. New Astra documents and the subsequent Agent A patch are outside this frozen baseline inventory and tracked in ASTRA_RELEASE_LEDGER.md.

Status describes verification, not completion. PARTIAL means change responsibility/source identified but complete transitive/runtime audit remains pending. UNVERIFIED means evidence/document/dependency assertions have not been rerun. KNOWN FAILURE is the reported capture path, not a claim that every participating module is faulty. Related tests below are direct source references where found, otherwise candidate domain suites; their presence does not mean they pass. Runtime dependencies are direct imported modules, not a complete deployment bill of materials.

## Subsystem inventory

| Path | Responsibility | Tracked files |
|---|---|---|
| `mobile_app/` | Only Expo Android client | 86 |
| `mobile/` | Flask bearer v1/v2 APIs | 4 |
| `auth/` | Identity, registration, OTP, sessions | 24 |
| `child/` | Child social/search and face flows | 19 |
| `parent/` | Guardian ownership, controls and review | 22 |
| `admin/` | Privileged moderation and auditing | 8 |
| `safety/` | Inference and policy | 18 |
| `services/` | Shared media, controls, storage, ranking and usage | 28 |
| `database/` | PostgreSQL connections/schema/upgrades | 8 |
| `db/migrations/` | Ordered migration chain | 14 |
| `mailg/` | Resend delivery | 3 |
| `tests/` | Backend regression and acceptance | 53 |
| `.github/workflows/` | CI, release, deployment and role validation | 7 |
| `docs/` | Architecture, evidence and release references | 19 |
| `modal_web.py` | Existing Modal Flask deployment | 1 |
| `modal_ai.py` | Existing Modal AI deployment | 1 |
| `app.py` | Flask bootstrap and route registration | 1 |
| `config.py` | Server configuration | 1 |

## Every changed file

### `MODAL_DEPLOYMENT.md`
- **Domain:** MODAL_DEPLOYMENT.md
- **Why it changed:** Document strict Resend sender/preflight and secret comparison release operations.
- **Current responsibility:** Document strict Resend sender/preflight and secret comparison release operations; exact source is the pinned baseline file.
- **Related tests:** tests/test_live_release_contracts.py; tests/test_release_package_contract.py.
- **Runtime dependencies:** Documentation only; named evidence/services not freshly verified.
- **Security/safety impact:** Evidence integrity, dependency reproducibility or regression detection; no direct authorization grant.
- **Status:** UNVERIFIED.

### `audit/reports/06_ai_safety.md`
- **Domain:** audit
- **Why it changed:** Reconcile safety audit evidence and bounded benchmark claims.
- **Current responsibility:** Reconcile safety audit evidence and bounded benchmark claims; exact source is the pinned baseline file.
- **Related tests:** Relevant domain suites in release ledger; direct coverage not established.
- **Runtime dependencies:** Documentation only; named evidence/services not freshly verified.
- **Security/safety impact:** Evidence integrity, dependency reproducibility or regression detection; no direct authorization grant.
- **Status:** UNVERIFIED.

### `auth/parent_email_otp.py`
- **Domain:** auth
- **Why it changed:** Route parent verification codes through dedicated fixed-sender mail function.
- **Current responsibility:** Route parent verification codes through dedicated fixed-sender mail function; exact source is the pinned baseline file.
- **Related tests:** tests/test_continuation_security.py; tests/test_final_hardening.py; tests/test_parent_auth_end_to_end_contract.py.
- **Runtime dependencies:** hashlib; hmac; os; secrets; datetime; auth.service; config; database.connection; mailg.send_email; services.identity.
- **Security/safety impact:** Child privacy, eligibility, moderation or privileged server behavior must remain authoritative.
- **Status:** PARTIAL.

### `child/routes.py`
- **Domain:** child
- **Why it changed:** Record follow, block, mute, report and share recommendation feedback after existing actions.
- **Current responsibility:** Record follow, block, mute, report and share recommendation feedback after existing actions; exact source is the pinned baseline file.
- **Related tests:** tests/test_adult_content_hardening.py; tests/test_agent_d_parent_admin.py; tests/test_audio_retirement_runtime.py; tests/test_college_submission_critical_regressions.py; tests/test_content_search.py; tests/test_discovery_privacy.py; tests/test_guardian_verification_fail_closed.py; tests/test_parent_auth_end_to_end_contract.py; tests/test_password_reset.py; tests/test_quiz_server_persistence.py; tests/test_real_postgres_role_smoke.py; tests/test_two_parent_friendship.py; tests/test_usage_heartbeat_visibility.py; tests/test_wave2_security_contract.py; mobile_app/tests/agentC.test.ts; mobile_app/tests/flows.test.ts; mobile_app/tests/onboarding.test.ts.
- **Runtime dependencies:** os; uuid; flask; extensions; decorators; child.service; services.social; services.usage; quiz.service; database.connection; safety.moderation_service; services.audit; services.controls; safety.pii_service; services.recommendation_signals; datetime; childMessage.service; PIL; time.
- **Security/safety impact:** Child privacy, eligibility, moderation or privileged server behavior must remain authoritative.
- **Status:** PARTIAL.

### `child/search_routes.py`
- **Domain:** child
- **Why it changed:** Use whole-hashtag matching, indexed tags, processing eligibility and scoped discoverable authors.
- **Current responsibility:** Use whole-hashtag matching, indexed tags, processing eligibility and scoped discoverable authors; exact source is the pinned baseline file.
- **Related tests:** tests/test_content_search.py.
- **Runtime dependencies:** re; urllib.parse; flask; child.service; database.connection; decorators; extensions; safety.pii_service; services.controls; services.social.
- **Security/safety impact:** Child privacy, eligibility, moderation or privileged server behavior must remain authoritative.
- **Status:** PARTIAL.

### `database/connection.py`
- **Domain:** database
- **Why it changed:** Cache connection validation and record pool timing/counter diagnostics.
- **Current responsibility:** Cache connection validation and record pool timing/counter diagnostics; exact source is the pinned baseline file.
- **Related tests:** tests/test_agent_a_disposable_postgres.py; tests/test_agent_a_state_machine_and_face.py; tests/test_agent_c_notifications_read.py; tests/test_agent_d_parent_admin.py; tests/test_curated_feed.py; tests/test_database_connection_pool.py; tests/test_echo_attack_prevention.py; tests/test_final_hardening.py; tests/test_master_release_features.py; tests/test_modules_11_15_contract_cleanup.py; tests/test_password_reset.py; tests/test_phase25_production_hardening.py; tests/test_phase2_upload_and_tags.py; tests/test_real_app_acceptance_e2e.py; tests/test_story_music_e2e.py.
- **Runtime dependencies:** threading; os; time; collections; dotenv; config; psycopg2; psycopg2.extras; psycopg2.pool.
- **Security/safety impact:** Child privacy, eligibility, moderation or privileged server behavior must remain authoritative.
- **Status:** PARTIAL.

### `database/schema.sql`
- **Domain:** database
- **Why it changed:** Include recommendation signal schema in fresh database bootstrap.
- **Current responsibility:** Include recommendation signal schema in fresh database bootstrap; exact source is the pinned baseline file.
- **Related tests:** tests/test_k2_ai_safety.py; tests/test_quiz_server_persistence.py; tests/test_real_postgres_role_smoke.py.
- **Runtime dependencies:** PostgreSQL; preceding schema/migrations.
- **Security/safety impact:** Child privacy, eligibility, moderation or privileged server behavior must remain authoritative.
- **Status:** PARTIAL.

### `database/upgrade.sql`
- **Domain:** database
- **Why it changed:** Reconcile upgrade chain with guarded schema changes and release compatibility.
- **Current responsibility:** Reconcile upgrade chain with guarded schema changes and release compatibility; exact source is the pinned baseline file.
- **Related tests:** tests/test_quiz_server_persistence.py; tests/test_two_parent_friendship.py; tests/test_wave2_security_contract.py.
- **Runtime dependencies:** PostgreSQL; preceding schema/migrations.
- **Security/safety impact:** Child privacy, eligibility, moderation or privileged server behavior must remain authoritative.
- **Status:** PARTIAL.

### `db/migrations/20260909120000_recommendation_publication_contract.sql`
- **Domain:** db
- **Why it changed:** Create durable recommendation signal schema and indexes for existing databases.
- **Current responsibility:** Create durable recommendation signal schema and indexes for existing databases; exact source is the pinned baseline file.
- **Related tests:** Relevant domain suites in release ledger; direct coverage not established.
- **Runtime dependencies:** PostgreSQL; preceding schema/migrations.
- **Security/safety impact:** Child privacy, eligibility, moderation or privileged server behavior must remain authoritative.
- **Status:** PARTIAL.

### `docs/FINAL_E2E_MATRIX.md`
- **Domain:** docs
- **Why it changed:** Record historical automated, service and device verification boundaries.
- **Current responsibility:** Record historical automated, service and device verification boundaries; exact source is the pinned baseline file.
- **Related tests:** Relevant domain suites in release ledger; direct coverage not established.
- **Runtime dependencies:** Documentation only; named evidence/services not freshly verified.
- **Security/safety impact:** Evidence integrity, dependency reproducibility or regression detection; no direct authorization grant.
- **Status:** UNVERIFIED.

### `docs/KNOWN_LIMITATIONS.md`
- **Domain:** docs
- **Why it changed:** Disclose native, service, content, benchmark and dependency limitations.
- **Current responsibility:** Disclose native, service, content, benchmark and dependency limitations; exact source is the pinned baseline file.
- **Related tests:** Relevant domain suites in release ledger; direct coverage not established.
- **Runtime dependencies:** Documentation only; named evidence/services not freshly verified.
- **Security/safety impact:** Evidence integrity, dependency reproducibility or regression detection; no direct authorization grant.
- **Status:** UNVERIFIED.

### `docs/MODERATION_BENCHMARK_EVIDENCE_TEMPLATE.md`
- **Domain:** docs
- **Why it changed:** Define reproducible benchmark evidence fields and nonclaims.
- **Current responsibility:** Define reproducible benchmark evidence fields and nonclaims; exact source is the pinned baseline file.
- **Related tests:** Relevant domain suites in release ledger; direct coverage not established.
- **Runtime dependencies:** Documentation only; named evidence/services not freshly verified.
- **Security/safety impact:** Evidence integrity, dependency reproducibility or regression detection; no direct authorization grant.
- **Status:** UNVERIFIED.

### `docs/MODERATION_BENCHMARK_PROTOCOL.md`
- **Domain:** docs
- **Why it changed:** Define frozen moderation evaluation, metrics and review gates.
- **Current responsibility:** Define frozen moderation evaluation, metrics and review gates; exact source is the pinned baseline file.
- **Related tests:** Relevant domain suites in release ledger; direct coverage not established.
- **Runtime dependencies:** Documentation only; named evidence/services not freshly verified.
- **Security/safety impact:** Evidence integrity, dependency reproducibility or regression detection; no direct authorization grant.
- **Status:** UNVERIFIED.

### `docs/PHYSICAL_DEVICE_CHECKLIST.md`
- **Domain:** docs
- **Why it changed:** Enumerate required Android journeys and historical missing-device blockers.
- **Current responsibility:** Enumerate required Android journeys and historical missing-device blockers; exact source is the pinned baseline file.
- **Related tests:** Relevant domain suites in release ledger; direct coverage not established.
- **Runtime dependencies:** Documentation only; named evidence/services not freshly verified.
- **Security/safety impact:** Evidence integrity, dependency reproducibility or regression detection; no direct authorization grant.
- **Status:** UNVERIFIED.

### `docs/UI_PARITY_RESTORE_MATRIX.md`
- **Domain:** docs
- **Why it changed:** Map 61 Stitch visual states to existing Expo screens and gaps.
- **Current responsibility:** Map 61 Stitch visual states to existing Expo screens and gaps; exact source is the pinned baseline file.
- **Related tests:** Relevant domain suites in release ledger; direct coverage not established.
- **Runtime dependencies:** Documentation only; named evidence/services not freshly verified.
- **Security/safety impact:** Evidence integrity, dependency reproducibility or regression detection; no direct authorization grant.
- **Status:** UNVERIFIED.

### `evaluate_toxicity.py`
- **Domain:** evaluate_toxicity.py
- **Why it changed:** Evaluate frozen ALLOW/REVIEW/BLOCK predictions with validation and reproducible metrics.
- **Current responsibility:** Evaluate frozen ALLOW/REVIEW/BLOCK predictions with validation and reproducible metrics; exact source is the pinned baseline file.
- **Related tests:** tests/test_moderation_benchmark_readiness.py.
- **Runtime dependencies:** __future__; argparse; csv; json; pathlib; typing.
- **Security/safety impact:** Child privacy, eligibility, moderation or privileged server behavior must remain authoritative.
- **Status:** PARTIAL.

### `mailg/send_email.py`
- **Domain:** mailg
- **Why it changed:** Require verified Resend production delivery and fixed parent OTP sender; remove fallback success paths.
- **Current responsibility:** Require verified Resend production delivery and fixed parent OTP sender; remove fallback success paths; exact source is the pinned baseline file.
- **Related tests:** tests/test_final_hardening.py; tests/test_smtp_readiness.py.
- **Runtime dependencies:** json; os; urllib.error; urllib.request.
- **Security/safety impact:** Child privacy, eligibility, moderation or privileged server behavior must remain authoritative.
- **Status:** PARTIAL.

### `mobile/api.py`
- **Domain:** mobile
- **Why it changed:** Wire feedback, publication refresh, exact eligible discovery and quiz bank contracts into existing bearer routes.
- **Current responsibility:** Wire feedback, publication refresh, exact eligible discovery and quiz bank contracts into existing bearer routes; exact source is the pinned baseline file.
- **Related tests:** tests/test_content_search.py; tests/test_react_native_contract.py.
- **Runtime dependencies:** __future__; base64; json; os; random; secrets; tempfile; uuid; pathlib; datetime; decimal; functools; urllib.parse; flask; itsdangerous; werkzeug.datastructures; auth.child_provisioning; auth.parent_email_otp; auth.password_reset; auth.service; child.service; childMessage.service; config; database.connection; extensions; parent.service; quiz.service; safety.moderation_service; safety.pii_service; safety.policy; services.behavior; services.recommendation_signals; services.controls; services.curated_feed; services.social; child.search_routes; services.audit; services.usage; services.media_delivery; services.tag_service; hashlib; hmac; services; services.job_queue; services.media_processor; services.publication_lifecycle; services.object_storage; services.ai; services.media_persistence; logging; safety.visual_service; services.media_sanitizer.
- **Security/safety impact:** Child privacy, eligibility, moderation or privileged server behavior must remain authoritative.
- **Status:** PARTIAL.

### `mobile/stitch_api.py`
- **Domain:** mobile
- **Why it changed:** Record approved shared-post recommendation feedback.
- **Current responsibility:** Record approved shared-post recommendation feedback; exact source is the pinned baseline file.
- **Related tests:** Relevant domain suites in release ledger; direct coverage not established.
- **Runtime dependencies:** __future__; flask; child.service; childMessage.service; database.connection; extensions; mobile.api; services.social; services.recommendation_signals.
- **Security/safety impact:** Child privacy, eligibility, moderation or privileged server behavior must remain authoritative.
- **Status:** PARTIAL.

### `mobile_app/app.json`
- **Domain:** Mobile UI/API/navigation
- **Why it changed:** Configure native camera permission and link existing EAS owner/project.
- **Current responsibility:** Configure native camera permission and link existing EAS owner/project; exact source is the pinned baseline file.
- **Related tests:** tests/test_react_native_contract.py.
- **Runtime dependencies:** npm/Expo native build toolchain.
- **Security/safety impact:** Evidence integrity, dependency reproducibility or regression detection; no direct authorization grant.
- **Status:** UNVERIFIED.

### `mobile_app/package-lock.json`
- **Domain:** Mobile UI/API/navigation
- **Why it changed:** Lock native capture dependencies and public registry artifacts.
- **Current responsibility:** Lock native capture dependencies and public registry artifacts; exact source is the pinned baseline file.
- **Related tests:** mobile_app: npm test/typecheck/export; physical checklist (coverage pending).
- **Runtime dependencies:** npm/Expo native build toolchain.
- **Security/safety impact:** Evidence integrity, dependency reproducibility or regression detection; no direct authorization grant.
- **Status:** UNVERIFIED.

### `mobile_app/package.json`
- **Domain:** Mobile UI/API/navigation
- **Why it changed:** Install native ML Kit face detection and Expo Camera dependencies.
- **Current responsibility:** Install native ML Kit face detection and Expo Camera dependencies; exact source is the pinned baseline file.
- **Related tests:** tests/test_react_native_contract.py.
- **Runtime dependencies:** npm/Expo native build toolchain.
- **Security/safety impact:** Evidence integrity, dependency reproducibility or regression detection; no direct authorization grant.
- **Status:** UNVERIFIED.

### `mobile_app/src/api/client.ts`
- **Domain:** Mobile UI/API/navigation
- **Why it changed:** Add v2 recommendation-actions route to shared API contract.
- **Current responsibility:** Add v2 recommendation-actions route to shared API contract; exact source is the pinned baseline file.
- **Related tests:** tests/test_agent_a_disposable_postgres.py; tests/test_agent_a_state_machine_and_face.py; tests/test_agent_c_notifications_read.py; tests/test_agent_d_parent_admin.py; tests/test_college_submission_critical_regressions.py; tests/test_echo_attack_prevention.py; tests/test_final_hardening.py; tests/test_k2_ai_safety.py; tests/test_master_release_features.py; tests/test_me_onboarding_gates.py; tests/test_modules_11_15_contract_cleanup.py; tests/test_phase25_production_hardening.py; tests/test_phase2_upload_and_tags.py; tests/test_r2_media_delivery.py; tests/test_react_native_contract.py; tests/test_real_app_acceptance_e2e.py; tests/test_real_postgres_role_smoke.py; tests/test_story_music_e2e.py; tests/test_video_audio_stripping.py; mobile_app/tests/agentC.test.ts; mobile_app/tests/agentC2.test.ts; mobile_app/tests/cancellation.test.ts; mobile_app/tests/contracts.test.ts; mobile_app/tests/controller.test.ts; mobile_app/tests/onboarding.test.ts.
- **Runtime dependencies:** ./errors.
- **Security/safety impact:** Presentation/accessibility and real API state; cannot grant server access.
- **Status:** PARTIAL.

### `mobile_app/src/api/errors.ts`
- **Domain:** Mobile UI/API/navigation
- **Why it changed:** Explain offline verification and timeout errors.
- **Current responsibility:** Explain offline verification and timeout errors; exact source is the pinned baseline file.
- **Related tests:** tests/test_ai_hardening.py; tests/test_ai_safety_contract.py; tests/test_audio_retirement_runtime.py; tests/test_college_submission_critical_regressions.py; mobile_app/tests/contracts.test.ts; mobile_app/tests/errors.test.ts.
- **Runtime dependencies:** No explicit imports; standard language runtime.
- **Security/safety impact:** Presentation/accessibility and real API state; cannot grant server access.
- **Status:** PARTIAL.

### `mobile_app/src/api/kidsSocial.ts`
- **Domain:** Mobile UI/API/navigation
- **Why it changed:** Type and fetch report-history API responses.
- **Current responsibility:** Type and fetch report-history API responses; exact source is the pinned baseline file.
- **Related tests:** mobile_app/tests/agentC.test.ts; mobile_app/tests/agentC2.test.ts.
- **Runtime dependencies:** ./client.
- **Security/safety impact:** Presentation/accessibility and real API state; cannot grant server access.
- **Status:** PARTIAL.

### `mobile_app/src/api/recommendation.ts`
- **Domain:** Mobile UI/API/navigation
- **Why it changed:** Send typed NOT_INTERESTED feedback to v2 endpoint.
- **Current responsibility:** Send typed NOT_INTERESTED feedback to v2 endpoint; exact source is the pinned baseline file.
- **Related tests:** tests/test_audit_p0_p1_regressions.py; tests/test_curated_feed.py; tests/test_submission_publication_recommendations.py.
- **Runtime dependencies:** ./client.
- **Security/safety impact:** Presentation/accessibility and real API state; cannot grant server access.
- **Status:** PARTIAL.

### `mobile_app/src/camera/CameraCapture.tsx`
- **Domain:** Mobile native capture
- **Why it changed:** Embed front camera, local quality gate and safe checked-photo network retry.
- **Current responsibility:** Embed front camera, local quality gate and safe checked-photo network retry; exact source is the pinned baseline file.
- **Related tests:** mobile_app: npm test/typecheck/export; physical checklist (coverage pending).
- **Runtime dependencies:** react; expo-camera; react-native; @react-native-community/netinfo; ../api/client; ./capture; ./facePrecheck; ../ui/components; ../ui/nativeViews; ../ui/tokens.
- **Security/safety impact:** Capture permission, local quality gating and identity-image boundary; reported P0 investigation.
- **Status:** KNOWN FAILURE.

### `mobile_app/src/camera/capture.ts`
- **Domain:** Mobile native capture
- **Why it changed:** Carry temporary URI through testable live-photo capture contract.
- **Current responsibility:** Carry temporary URI through testable live-photo capture contract; exact source is the pinned baseline file.
- **Related tests:** tests/test_agent_a_disposable_postgres.py; tests/test_continuation_security.py; tests/test_r2_media_delivery.py; mobile_app/tests/flows.test.ts.
- **Runtime dependencies:** No explicit imports; standard language runtime.
- **Security/safety impact:** Capture permission, local quality gating and identity-image boundary; reported P0 investigation.
- **Status:** PARTIAL.

### `mobile_app/src/camera/facePrecheck.ts`
- **Domain:** Mobile native capture
- **Why it changed:** Invoke native ML Kit and translate face-quality/native failures before upload.
- **Current responsibility:** Invoke native ML Kit and translate face-quality/native failures before upload; exact source is the pinned baseline file.
- **Related tests:** mobile_app: npm test/typecheck/export; physical checklist (coverage pending).
- **Runtime dependencies:** react-native; @react-native-ml-kit/face-detection; ./capture; ./faceQuality.
- **Security/safety impact:** Capture permission, local quality gating and identity-image boundary; reported P0 investigation.
- **Status:** PARTIAL.

### `mobile_app/src/camera/faceQuality.ts`
- **Domain:** Mobile native capture
- **Why it changed:** Evaluate one-face size, centering and pose against image dimensions.
- **Current responsibility:** Evaluate one-face size, centering and pose against image dimensions; exact source is the pinned baseline file.
- **Related tests:** mobile_app/tests/faceQuality.test.ts.
- **Runtime dependencies:** No explicit imports; standard language runtime.
- **Security/safety impact:** Capture permission, local quality gating and identity-image boundary; reported P0 investigation.
- **Status:** PARTIAL.

### `mobile_app/src/camera/livePhoto.ts`
- **Domain:** Mobile native capture
- **Why it changed:** Preserve native image URI in system-camera adapter.
- **Current responsibility:** Preserve native image URI in system-camera adapter; exact source is the pinned baseline file.
- **Related tests:** mobile_app: npm test/typecheck/export; physical checklist (coverage pending).
- **Runtime dependencies:** expo-image-picker; ./capture.
- **Security/safety impact:** Capture permission, local quality gating and identity-image boundary; reported P0 investigation.
- **Status:** PARTIAL.

### `mobile_app/src/kids/PostCard.tsx`
- **Domain:** Mobile UI/API/navigation
- **Why it changed:** Restore compact media-first social card/actions styling.
- **Current responsibility:** Restore compact media-first social card/actions styling; exact source is the pinned baseline file.
- **Related tests:** mobile_app: npm test/typecheck/export; physical checklist (coverage pending).
- **Runtime dependencies:** react-native; @tanstack/react-query; ../api/kidsFeed; ../auth/AuthProvider; ../query/client; ../query/keys; ../api/kidsSocial; ./social; ../ui/social; ../ui/tokens.
- **Security/safety impact:** Presentation/accessibility and real API state; cannot grant server access.
- **Status:** PARTIAL.

### `mobile_app/src/kids/VideoMedia.tsx`
- **Domain:** Mobile UI/API/navigation
- **Why it changed:** Render Expo video through shared native-view type adapter.
- **Current responsibility:** Render Expo video through shared native-view type adapter; exact source is the pinned baseline file.
- **Related tests:** mobile_app: npm test/typecheck/export; physical checklist (coverage pending).
- **Runtime dependencies:** react; react-native; expo-video; ../query/client; ../ui/components; ../ui/nativeViews; ../ui/tokens.
- **Security/safety impact:** Presentation/accessibility and real API state; cannot grant server access.
- **Status:** PARTIAL.

### `mobile_app/src/kids/useKidsHydration.ts`
- **Domain:** Mobile UI/API/navigation
- **Why it changed:** Prefetch six initial Kids queries including home/story state and first feed/reel pages.
- **Current responsibility:** Prefetch six initial Kids queries including home/story state and first feed/reel pages; exact source is the pinned baseline file.
- **Related tests:** mobile_app: npm test/typecheck/export; physical checklist (coverage pending).
- **Runtime dependencies:** react; @tanstack/react-query; ../api/kidsFeed; ../api/kidsProfiles; ../api/kidsChat; ../auth/AuthProvider; ../query/keys; ../query/client.
- **Security/safety impact:** Presentation/accessibility and real API state; cannot grant server access.
- **Status:** PARTIAL.

### `mobile_app/src/navigation/RootNavigator.tsx`
- **Domain:** Mobile UI/API/navigation
- **Why it changed:** Register gated social/safety/profile utility screens.
- **Current responsibility:** Register gated social/safety/profile utility screens; exact source is the pinned baseline file.
- **Related tests:** mobile_app: npm test/typecheck/export; physical checklist (coverage pending).
- **Runtime dependencies:** react; @react-navigation/native; @react-navigation/native-stack; ../auth/AuthProvider; ../screens/ChildFace; ../screens/KidsHome; ../screens/kids/KidsTabsHost; ../screens/kids/FeedScreen; ../screens/kids/StoriesScreen; ../screens/kids/ReelsScreen; ../screens/kids/DiscoverScreen; ../screens/kids/OwnProfileScreen; ../screens/kids/OtherProfileScreen; ../screens/kids/PostDetailScreen; ../screens/kids/NotificationsScreen; ../screens/kids/ConversationsScreen; ../screens/kids/ChatScreen; ../screens/kids/SocialStates; ../screens/kids/CreateScreen; ../screens/kids/ProcessingScreen; ../screens/kids/SafetyScreens; ../screens/Parent; ../screens/parent/ParentScreens; ../screens/admin/AdminScreens; ../screens/ParentOnboarding; ../screens/PasswordReset; ../screens/Quiz; ../screens/WelcomeLogin; ../ui/components; ./gates; ./types.
- **Security/safety impact:** Presentation/accessibility and real API state; cannot grant server access.
- **Status:** PARTIAL.

### `mobile_app/src/navigation/gates.ts`
- **Domain:** Mobile UI/API/navigation
- **Why it changed:** Extend valid gated destination names for new social screens.
- **Current responsibility:** Extend valid gated destination names for new social screens; exact source is the pinned baseline file.
- **Related tests:** mobile_app: npm test/typecheck/export; physical checklist (coverage pending).
- **Runtime dependencies:** ../api/errors; ../api/auth.
- **Security/safety impact:** Presentation/accessibility and real API state; cannot grant server access.
- **Status:** PARTIAL.

### `mobile_app/src/navigation/types.ts`
- **Domain:** Mobile UI/API/navigation
- **Why it changed:** Type new social/safety stack parameters.
- **Current responsibility:** Type new social/safety stack parameters; exact source is the pinned baseline file.
- **Related tests:** mobile_app: npm test/typecheck/export; physical checklist (coverage pending).
- **Runtime dependencies:** @react-navigation/native-stack.
- **Security/safety impact:** Presentation/accessibility and real API state; cannot grant server access.
- **Status:** PARTIAL.

### `mobile_app/src/screens/Quiz.tsx`
- **Domain:** Mobile UI/API/navigation
- **Why it changed:** Present live practice bank, answer progress/XP and results while retaining authoritative gate refresh.
- **Current responsibility:** Present live practice bank, answer progress/XP and results while retaining authoritative gate refresh; exact source is the pinned baseline file.
- **Related tests:** mobile_app: npm test/typecheck/export; physical checklist (coverage pending).
- **Runtime dependencies:** react; react-native; ../api/auth; ../api/client; ../auth/AuthProvider; ../auth/session; ../auth/storage; ../navigation/types; ../quiz/decision; ../ui/components; ../ui/tokens.
- **Security/safety impact:** Presentation/accessibility and real API state; cannot grant server access.
- **Status:** PARTIAL.

### `mobile_app/src/screens/WelcomeLogin.tsx`
- **Domain:** Mobile UI/API/navigation
- **Why it changed:** Restore LittleNet branded compact role/login presentation.
- **Current responsibility:** Restore LittleNet branded compact role/login presentation; exact source is the pinned baseline file.
- **Related tests:** mobile_app: npm test/typecheck/export; physical checklist (coverage pending).
- **Runtime dependencies:** react; react-native; ../api/auth; ../api/client; ../auth/AuthProvider; ../ui/components; ../navigation/types; ../ui/tokens.
- **Security/safety impact:** Presentation/accessibility and real API state; cannot grant server access.
- **Status:** PARTIAL.

### `mobile_app/src/screens/admin/AdminScreens.tsx`
- **Domain:** Mobile UI/API/navigation
- **Why it changed:** Polish dashboard/queue/review evidence presentation and risk labels.
- **Current responsibility:** Polish dashboard/queue/review evidence presentation and risk labels; exact source is the pinned baseline file.
- **Related tests:** mobile_app: npm test/typecheck/export; physical checklist (coverage pending).
- **Runtime dependencies:** react; react-native; @tanstack/react-query; ../../api/parentAdmin; ../../auth/AuthProvider; ../../navigation/types; ../../query/client; ../../query/keys; ../../ui/components; ../../ui/social; ../../ui/tokens.
- **Security/safety impact:** Presentation/accessibility and real API state; cannot grant server access.
- **Status:** PARTIAL.

### `mobile_app/src/screens/kids/ChatScreen.tsx`
- **Domain:** Mobile UI/API/navigation
- **Why it changed:** Add chat-details navigation and compact conversation presentation.
- **Current responsibility:** Add chat-details navigation and compact conversation presentation; exact source is the pinned baseline file.
- **Related tests:** mobile_app: npm test/typecheck/export; physical checklist (coverage pending).
- **Runtime dependencies:** react; react-native; ../../api/kidsChat; ../../api/client; ../../auth/AuthProvider; ../../kids/social; ../../navigation/types; ../../query/client; ../../ui/components; ../../ui/tokens.
- **Security/safety impact:** Presentation/accessibility and real API state; cannot grant server access.
- **Status:** PARTIAL.

### `mobile_app/src/screens/kids/ConversationsScreen.tsx`
- **Domain:** Mobile UI/API/navigation
- **Why it changed:** Wire new-message entry and compact inbox presentation.
- **Current responsibility:** Wire new-message entry and compact inbox presentation; exact source is the pinned baseline file.
- **Related tests:** mobile_app: npm test/typecheck/export; physical checklist (coverage pending).
- **Runtime dependencies:** react; react-native; @react-navigation/native; ../../api/kidsChat; ../../auth/AuthProvider; ../../kids/social; ../../navigation/types; ../../query/client; ../../ui/social; ../../ui/components; ../../api/client; ../../ui/tokens.
- **Security/safety impact:** Presentation/accessibility and real API state; cannot grant server access.
- **Status:** PARTIAL.

### `mobile_app/src/screens/kids/CreateScreen.tsx`
- **Domain:** Mobile UI/API/navigation
- **Why it changed:** Refine upload composer styling around existing direct-upload workflow.
- **Current responsibility:** Refine upload composer styling around existing direct-upload workflow; exact source is the pinned baseline file.
- **Related tests:** mobile_app: npm test/typecheck/export; physical checklist (coverage pending).
- **Runtime dependencies:** react; react-native; ../../api/kidsUpload; ../../auth/AuthProvider; ../../kids/directUpload; ../../kids/postMedia; ../../navigation/types; ../../ui/components; ../../ui/tokens.
- **Security/safety impact:** Presentation/accessibility and real API state; cannot grant server access.
- **Status:** PARTIAL.

### `mobile_app/src/screens/kids/DiscoverScreen.tsx`
- **Domain:** Mobile UI/API/navigation
- **Why it changed:** Present categorized discovery/search and recent searches with media results.
- **Current responsibility:** Present categorized discovery/search and recent searches with media results; exact source is the pinned baseline file.
- **Related tests:** mobile_app: npm test/typecheck/export; physical checklist (coverage pending).
- **Runtime dependencies:** react; react-native; ../../api/kidsProfiles; ../../auth/AuthProvider; ../../api/kidsSocial; ../../navigation/types; ../../ui/social; ../../ui/components; ../../api/client; ../../query/client; ../../kids/useSearch; ../../ui/tokens.
- **Security/safety impact:** Presentation/accessibility and real API state; cannot grant server access.
- **Status:** PARTIAL.

### `mobile_app/src/screens/kids/FeedScreen.tsx`
- **Domain:** Mobile UI/API/navigation
- **Why it changed:** Restore compact feed heading/tabs and learning selection.
- **Current responsibility:** Restore compact feed heading/tabs and learning selection; exact source is the pinned baseline file.
- **Related tests:** mobile_app: npm test/typecheck/export; physical checklist (coverage pending).
- **Runtime dependencies:** react-native; react; ../../api/client; ../../kids/PostCard; ../../kids/useFeed; ../../kids/social; ../../navigation/types; ../../query/client; ../../ui/components.
- **Security/safety impact:** Presentation/accessibility and real API state; cannot grant server access.
- **Status:** PARTIAL.

### `mobile_app/src/screens/kids/KidsTabs.tsx`
- **Domain:** Mobile UI/API/navigation
- **Why it changed:** Restore five-tab navigation chrome and initial hydration.
- **Current responsibility:** Restore five-tab navigation chrome and initial hydration; exact source is the pinned baseline file.
- **Related tests:** mobile_app/tests/flows.test.ts.
- **Runtime dependencies:** react-native; ../../navigation/types; ../../ui/components; ../../ui/tokens.
- **Security/safety impact:** Presentation/accessibility and real API state; cannot grant server access.
- **Status:** PARTIAL.

### `mobile_app/src/screens/kids/KidsTabsHost.tsx`
- **Domain:** Mobile UI/API/navigation
- **Why it changed:** Connect initial Kids hydration at host boundary.
- **Current responsibility:** Connect initial Kids hydration at host boundary; exact source is the pinned baseline file.
- **Related tests:** mobile_app: npm test/typecheck/export; physical checklist (coverage pending).
- **Runtime dependencies:** ../../auth/AuthProvider; ../../navigation/types; ./KidsTabs; ../../kids/useKidsHydration; ./FeedScreen; ./DiscoverScreen; ./CreateScreen; ./ReelsScreen; ./OwnProfileScreen; ../../ui/components.
- **Security/safety impact:** Presentation/accessibility and real API state; cannot grant server access.
- **Status:** PARTIAL.

### `mobile_app/src/screens/kids/NotificationsScreen.tsx`
- **Domain:** Mobile UI/API/navigation
- **Why it changed:** Refine notification rows and unread presentation.
- **Current responsibility:** Refine notification rows and unread presentation; exact source is the pinned baseline file.
- **Related tests:** mobile_app: npm test/typecheck/export; physical checklist (coverage pending).
- **Runtime dependencies:** react; react-native; ../../api/kidsChat; ../../auth/AuthProvider; ../../navigation/types; ../../query/client; ../../ui/social; ../../ui/components; ../../ui/tokens.
- **Security/safety impact:** Presentation/accessibility and real API state; cannot grant server access.
- **Status:** PARTIAL.

### `mobile_app/src/screens/kids/OtherProfileScreen.tsx`
- **Domain:** Mobile UI/API/navigation
- **Why it changed:** Refine other-profile presentation and existing actions.
- **Current responsibility:** Refine other-profile presentation and existing actions; exact source is the pinned baseline file.
- **Related tests:** mobile_app: npm test/typecheck/export; physical checklist (coverage pending).
- **Runtime dependencies:** react; react-native; ../../api/client; ../../api/kidsProfiles; ../../api/kidsSocial; ../../auth/AuthProvider; ../../kids/social; ../../navigation/types; ../../query/keys; ../../ui/social; ../../ui/components; ../../ui/tokens.
- **Security/safety impact:** Presentation/accessibility and real API state; cannot grant server access.
- **Status:** PARTIAL.

### `mobile_app/src/screens/kids/OwnProfileScreen.tsx`
- **Domain:** Mobile UI/API/navigation
- **Why it changed:** Link edit/connections/saved screens and restore profile header/grid styling.
- **Current responsibility:** Link edit/connections/saved screens and restore profile header/grid styling; exact source is the pinned baseline file.
- **Related tests:** mobile_app: npm test/typecheck/export; physical checklist (coverage pending).
- **Runtime dependencies:** react; react-native; @tanstack/react-query; ../../api/kidsProfiles; ../../api/kidsSocial; ../../auth/AuthProvider; ../../navigation/types; ../../query/client; ../../query/keys; ../../ui/social; ../../ui/components; ../../ui/tokens.
- **Security/safety impact:** Presentation/accessibility and real API state; cannot grant server access.
- **Status:** PARTIAL.

### `mobile_app/src/screens/kids/PostDetailScreen.tsx`
- **Domain:** Mobile UI/API/navigation
- **Why it changed:** Add approved-recipient share sheet, profile safety actions and preserve report target across async work.
- **Current responsibility:** Add approved-recipient share sheet, profile safety actions and preserve report target across async work; exact source is the pinned baseline file.
- **Related tests:** mobile_app: npm test/typecheck/export; physical checklist (coverage pending).
- **Runtime dependencies:** react; react-native; ../../api/kidsSocial; ../../api/kidsChat; ../../auth/AuthProvider; ../../kids/VideoMedia; ../../navigation/types; ../../query/keys; ../../ui/social; ../../ui/components; ../../ui/tokens.
- **Security/safety impact:** Presentation/accessibility and real API state; cannot grant server access.
- **Status:** PARTIAL.

### `mobile_app/src/screens/kids/ProcessingScreen.tsx`
- **Domain:** Mobile UI/API/navigation
- **Why it changed:** Refresh publication-dependent queries after terminal processing changes.
- **Current responsibility:** Refresh publication-dependent queries after terminal processing changes; exact source is the pinned baseline file.
- **Related tests:** mobile_app: npm test/typecheck/export; physical checklist (coverage pending).
- **Runtime dependencies:** react; react-native; ../../api/kidsUpload; ../../auth/AuthProvider; ../../kids/social; ../../kids/useProcessing; ../../navigation/types; ../../query/client; ../../query/keys; ../../ui/components; ../../ui/tokens.
- **Security/safety impact:** Presentation/accessibility and real API state; cannot grant server access.
- **Status:** PARTIAL.

### `mobile_app/src/screens/kids/ReelsScreen.tsx`
- **Domain:** Mobile UI/API/navigation
- **Why it changed:** Add recommendation feedback and refine full-screen playback/actions.
- **Current responsibility:** Add recommendation feedback and refine full-screen playback/actions; exact source is the pinned baseline file.
- **Related tests:** mobile_app: npm test/typecheck/export; physical checklist (coverage pending).
- **Runtime dependencies:** react; react-native; expo-video; @react-navigation/native; ../../api/kidsFeed; ../../api/client; ../../api/recommendation; ../../api/kidsSocial; ../../auth/AuthProvider; ../../kids/PostCard; ../../kids/social; ../../kids/useFeed; ../../navigation/types; ../../query/client; ../../ui/components; ../../ui/nativeViews; ../../ui/tokens.
- **Security/safety impact:** Presentation/accessibility and real API state; cannot grant server access.
- **Status:** PARTIAL.

### `mobile_app/src/screens/kids/SafetyScreens.tsx`
- **Domain:** Mobile UI/API/navigation
- **Why it changed:** Implement server-backed safety centre and report history states.
- **Current responsibility:** Implement server-backed safety centre and report history states; exact source is the pinned baseline file.
- **Related tests:** mobile_app: npm test/typecheck/export; physical checklist (coverage pending).
- **Runtime dependencies:** react; react-native; @tanstack/react-query; ../../api/kidsSocial; ../../auth/AuthProvider; ../../navigation/types; ../../ui/social; ../../ui/components; ../../ui/tokens.
- **Security/safety impact:** Presentation/accessibility and real API state; cannot grant server access.
- **Status:** PARTIAL.

### `mobile_app/src/screens/kids/SocialStates.tsx`
- **Domain:** Mobile UI/API/navigation
- **Why it changed:** Implement new-message picker, chat details, saved content, profile editing and connection directory.
- **Current responsibility:** Implement new-message picker, chat details, saved content, profile editing and connection directory; exact source is the pinned baseline file.
- **Related tests:** mobile_app: npm test/typecheck/export; physical checklist (coverage pending).
- **Runtime dependencies:** react; react-native; ../../api/kidsProfiles; ../../api/kidsSocial; ../../auth/AuthProvider; ../../navigation/types; ../../ui/social; ../../ui/components; ../../ui/tokens.
- **Security/safety impact:** Presentation/accessibility and real API state; cannot grant server access.
- **Status:** PARTIAL.

### `mobile_app/src/screens/kids/StoriesScreen.tsx`
- **Domain:** Mobile UI/API/navigation
- **Why it changed:** Implement timed story progress, paging and pause/resume presentation.
- **Current responsibility:** Implement timed story progress, paging and pause/resume presentation; exact source is the pinned baseline file.
- **Related tests:** mobile_app: npm test/typecheck/export; physical checklist (coverage pending).
- **Runtime dependencies:** react; react-native; @react-navigation/native; ../../api/kidsFeed; ../../auth/AuthProvider; ../../kids/VideoMedia; ../../navigation/types; ../../ui/social; ../../ui/components; ../../ui/tokens.
- **Security/safety impact:** Presentation/accessibility and real API state; cannot grant server access.
- **Status:** PARTIAL.

### `mobile_app/src/screens/parent/ParentScreens.tsx`
- **Domain:** Mobile UI/API/navigation
- **Why it changed:** Refine child usage, review risks and grouped authoritative controls presentation.
- **Current responsibility:** Refine child usage, review risks and grouped authoritative controls presentation; exact source is the pinned baseline file.
- **Related tests:** mobile_app: npm test/typecheck/export; physical checklist (coverage pending).
- **Runtime dependencies:** react; react-native; @tanstack/react-query; ../../api/parentAdmin; ../../auth/AuthProvider; ../../navigation/types; ../../query/client; ../../query/keys; ../../ui/components; ../../ui/social; ../../ui/tokens.
- **Security/safety impact:** Presentation/accessibility and real API state; cannot grant server access.
- **Status:** PARTIAL.

### `mobile_app/src/ui/components.tsx`
- **Domain:** Mobile UI/API/navigation
- **Why it changed:** Restore shared compact layout and distinguish connection failures from safety gates.
- **Current responsibility:** Restore shared compact layout and distinguish connection failures from safety gates; exact source is the pinned baseline file.
- **Related tests:** mobile_app: npm test/typecheck/export; physical checklist (coverage pending).
- **Runtime dependencies:** react; react-native; ../api/client; ./tokens.
- **Security/safety impact:** Presentation/accessibility and real API state; cannot grant server access.
- **Status:** PARTIAL.

### `mobile_app/src/ui/nativeViews.tsx`
- **Domain:** Mobile native capture
- **Why it changed:** Adapt Expo camera/video JSX types without runtime wrapping.
- **Current responsibility:** Adapt Expo camera/video JSX types without runtime wrapping; exact source is the pinned baseline file.
- **Related tests:** mobile_app: npm test/typecheck/export; physical checklist (coverage pending).
- **Runtime dependencies:** expo-camera; expo-video; react.
- **Security/safety impact:** Capture permission, local quality gating and identity-image boundary; reported P0 investigation.
- **Status:** PARTIAL.

### `mobile_app/src/ui/social.tsx`
- **Domain:** Mobile UI/API/navigation
- **Why it changed:** Align fallback avatar color and border with brand.
- **Current responsibility:** Align fallback avatar color and border with brand; exact source is the pinned baseline file.
- **Related tests:** tests/test_content_search.py; tests/test_curated_feed.py; tests/test_k2_ai_safety.py; tests/test_phase25_production_hardening.py; tests/test_phase2_upload_and_tags.py; tests/test_r2_media_delivery.py; tests/test_real_app_acceptance_e2e.py; tests/test_submission_publication_recommendations.py; tests/test_two_parent_friendship.py; tests/test_wave2_security_contract.py; mobile_app/tests/agentC.test.ts; mobile_app/tests/agentC2.test.ts.
- **Runtime dependencies:** react-native; ./tokens.
- **Security/safety impact:** Presentation/accessibility and real API state; cannot grant server access.
- **Status:** PARTIAL.

### `mobile_app/src/ui/tokens.ts`
- **Domain:** Mobile UI/API/navigation
- **Why it changed:** Centralize blue/violet palette, compact spacing, radii and typography.
- **Current responsibility:** Centralize blue/violet palette, compact spacing, radii and typography; exact source is the pinned baseline file.
- **Related tests:** tests/test_agent_a_state_machine_and_face.py; mobile_app/tests/session.test.ts.
- **Runtime dependencies:** No explicit imports; standard language runtime.
- **Security/safety impact:** Presentation/accessibility and real API state; cannot grant server access.
- **Status:** PARTIAL.

### `mobile_app/tests/faceQuality.test.ts`
- **Domain:** Mobile UI/API/navigation
- **Why it changed:** Add deterministic single-face/pose/size quality cases.
- **Current responsibility:** Add deterministic single-face/pose/size quality cases; exact source is the pinned baseline file.
- **Related tests:** mobile_app/tests/faceQuality.test.ts.
- **Runtime dependencies:** node:assert/strict; node:test; ../src/camera/faceQuality.
- **Security/safety impact:** Evidence integrity, dependency reproducibility or regression detection; no direct authorization grant.
- **Status:** PARTIAL.

### `modal_ai.py`
- **Domain:** modal_ai.py
- **Why it changed:** Add lightweight shared-secret fingerprint preflight without heavy model warmup.
- **Current responsibility:** Add lightweight shared-secret fingerprint preflight without heavy model warmup; exact source is the pinned baseline file.
- **Related tests:** tests/test_continuation_security.py.
- **Runtime dependencies:** pathlib; hashlib; json; os; modal; ai_server; importlib; safety.yolo_policy.
- **Security/safety impact:** Child privacy, eligibility, moderation or privileged server behavior must remain authoritative.
- **Status:** PARTIAL.

### `modal_web.py`
- **Domain:** modal_web.py
- **Why it changed:** Add lightweight secret comparison and require production Resend readiness.
- **Current responsibility:** Add lightweight secret comparison and require production Resend readiness; exact source is the pinned baseline file.
- **Related tests:** tests/test_wave2_security_contract.py.
- **Runtime dependencies:** pathlib; hashlib; json; os; subprocess; modal; flask; app; services.media_processor; mailg.send_email; config; database.connection; safety.presidio_adapter; services.object_storage; services.media_outbox; services.job_queue; safety.remote_client.
- **Security/safety impact:** Child privacy, eligibility, moderation or privileged server behavior must remain authoritative.
- **Status:** PARTIAL.

### `services/curated_feed.py`
- **Domain:** services
- **Why it changed:** Tighten publication/discovery eligibility and recommendation candidate handling.
- **Current responsibility:** Tighten publication/discovery eligibility and recommendation candidate handling; exact source is the pinned baseline file.
- **Related tests:** tests/test_curated_feed.py; tests/test_submission_publication_recommendations.py.
- **Runtime dependencies:** __future__; os; uuid; datetime; typing; database.connection; services.controls; services.social; child.service; services.media_delivery; services.recommendation_signals; psycopg2.extras.
- **Security/safety impact:** Child privacy, eligibility, moderation or privileged server behavior must remain authoritative.
- **Status:** PARTIAL.

### `services/media_processor.py`
- **Domain:** services
- **Why it changed:** Refresh materialized feed visibility after worker ALLOW publication.
- **Current responsibility:** Refresh materialized feed visibility after worker ALLOW publication; exact source is the pinned baseline file.
- **Related tests:** tests/test_agent_a_disposable_postgres.py; tests/test_agent_a_state_machine_and_face.py; tests/test_phase2_upload_and_tags.py.
- **Runtime dependencies:** __future__; os; shutil; subprocess; tempfile; uuid; pathlib; typing; config; database.connection; safety.moderation_service; safety.policy; services; services.media_sanitizer; services.social; services.job_queue; datetime; safety.visual_service; services.media_outbox; services.publication_lifecycle; PIL.
- **Security/safety impact:** Child privacy, eligibility, moderation or privileged server behavior must remain authoritative.
- **Status:** PARTIAL.

### `services/media_sanitizer.py`
- **Domain:** services
- **Why it changed:** Strip image metadata and replace bytes atomically before publication.
- **Current responsibility:** Strip image metadata and replace bytes atomically before publication; exact source is the pinned baseline file.
- **Related tests:** tests/test_video_audio_stripping.py.
- **Runtime dependencies:** __future__; os; subprocess; tempfile; pathlib; PIL.
- **Security/safety impact:** Child privacy, eligibility, moderation or privileged server behavior must remain authoritative.
- **Status:** PARTIAL.

### `services/publication_lifecycle.py`
- **Domain:** services
- **Why it changed:** Invalidate materialized Feed/Reels sessions after ALLOW transitions.
- **Current responsibility:** Invalidate materialized Feed/Reels sessions after ALLOW transitions; exact source is the pinned baseline file.
- **Related tests:** tests/test_submission_publication_recommendations.py.
- **Runtime dependencies:** __future__; database.connection.
- **Security/safety impact:** Child privacy, eligibility, moderation or privileged server behavior must remain authoritative.
- **Status:** PARTIAL.

### `services/recommendation.py`
- **Domain:** services
- **Why it changed:** Filter candidate safety/age/control eligibility and rank using negative/positive feedback.
- **Current responsibility:** Filter candidate safety/age/control eligibility and rank using negative/positive feedback; exact source is the pinned baseline file.
- **Related tests:** tests/test_audit_p0_p1_regressions.py; tests/test_curated_feed.py; tests/test_submission_publication_recommendations.py.
- **Runtime dependencies:** __future__; typing; database.connection; services.controls; services.curated_feed; services.social; services.recommendation_signals; child.service; safety; safety.semantic_service.
- **Security/safety impact:** Child privacy, eligibility, moderation or privileged server behavior must remain authoritative.
- **Status:** PARTIAL.

### `services/recommendation_signals.py`
- **Domain:** services
- **Why it changed:** Persist bounded weighted feedback and aggregate item/creator scores.
- **Current responsibility:** Persist bounded weighted feedback and aggregate item/creator scores; exact source is the pinned baseline file.
- **Related tests:** Relevant domain suites in release ledger; direct coverage not established.
- **Runtime dependencies:** __future__; collections; database.connection.
- **Security/safety impact:** Child privacy, eligibility, moderation or privileged server behavior must remain authoritative.
- **Status:** PARTIAL.

### `services/social.py`
- **Domain:** services
- **Why it changed:** Restrict discoverable posts to the shared discoverable-child boundary.
- **Current responsibility:** Restrict discoverable posts to the shared discoverable-child boundary; exact source is the pinned baseline file.
- **Related tests:** tests/test_content_search.py; tests/test_curated_feed.py; tests/test_k2_ai_safety.py; tests/test_phase25_production_hardening.py; tests/test_phase2_upload_and_tags.py; tests/test_r2_media_delivery.py; tests/test_real_app_acceptance_e2e.py; tests/test_submission_publication_recommendations.py; tests/test_two_parent_friendship.py; tests/test_wave2_security_contract.py; mobile_app/tests/agentC.test.ts; mobile_app/tests/agentC2.test.ts.
- **Runtime dependencies:** database.connection; services.controls; child.service; datetime; flask; services.usage; quiz.service; mailg.send_email; config.
- **Security/safety impact:** Child privacy, eligibility, moderation or privileged server behavior must remain authoritative.
- **Status:** PARTIAL.

### `tests/test_content_search.py`
- **Domain:** tests
- **Why it changed:** Extend regression coverage for content search.
- **Current responsibility:** Extend regression coverage for content search; exact source is the pinned baseline file.
- **Related tests:** tests/test_content_search.py.
- **Runtime dependencies:** pathlib.
- **Security/safety impact:** Evidence integrity, dependency reproducibility or regression detection; no direct authorization grant.
- **Status:** UNVERIFIED.

### `tests/test_database_connection_pool.py`
- **Domain:** tests
- **Why it changed:** Extend regression coverage for database connection pool.
- **Current responsibility:** Extend regression coverage for database connection pool; exact source is the pinned baseline file.
- **Related tests:** tests/test_database_connection_pool.py.
- **Runtime dependencies:** unittest.mock; pytest; psycopg2; database.
- **Security/safety impact:** Evidence integrity, dependency reproducibility or regression detection; no direct authorization grant.
- **Status:** UNVERIFIED.

### `tests/test_final_hardening.py`
- **Domain:** tests
- **Why it changed:** Extend regression coverage for final hardening.
- **Current responsibility:** Extend regression coverage for final hardening; exact source is the pinned baseline file.
- **Related tests:** tests/test_final_hardening.py.
- **Runtime dependencies:** os; tempfile; urllib.error; unittest.mock; pathlib; PIL; pytest; mailg.send_email; app; auth.parent_email_otp.
- **Security/safety impact:** Evidence integrity, dependency reproducibility or regression detection; no direct authorization grant.
- **Status:** UNVERIFIED.

### `tests/test_live_release_contracts.py`
- **Domain:** tests
- **Why it changed:** Extend regression coverage for live release contracts.
- **Current responsibility:** Extend regression coverage for live release contracts; exact source is the pinned baseline file.
- **Related tests:** tests/test_live_release_contracts.py.
- **Runtime dependencies:** pathlib.
- **Security/safety impact:** Evidence integrity, dependency reproducibility or regression detection; no direct authorization grant.
- **Status:** UNVERIFIED.

### `tests/test_moderation_benchmark_readiness.py`
- **Domain:** tests
- **Why it changed:** Extend regression coverage for moderation benchmark readiness.
- **Current responsibility:** Extend regression coverage for moderation benchmark readiness; exact source is the pinned baseline file.
- **Related tests:** tests/test_moderation_benchmark_readiness.py.
- **Runtime dependencies:** pathlib; sys; pytest; evaluate_toxicity.
- **Security/safety impact:** Evidence integrity, dependency reproducibility or regression detection; no direct authorization grant.
- **Status:** UNVERIFIED.

### `tests/test_smtp_readiness.py`
- **Domain:** tests
- **Why it changed:** Extend regression coverage for smtp readiness.
- **Current responsibility:** Extend regression coverage for smtp readiness; exact source is the pinned baseline file.
- **Related tests:** tests/test_smtp_readiness.py.
- **Runtime dependencies:** io; json; os; urllib.error; unittest.mock; mailg.send_email.
- **Security/safety impact:** Evidence integrity, dependency reproducibility or regression detection; no direct authorization grant.
- **Status:** UNVERIFIED.

### `tests/test_submission_publication_recommendations.py`
- **Domain:** tests
- **Why it changed:** Extend regression coverage for submission publication recommendations.
- **Current responsibility:** Extend regression coverage for submission publication recommendations; exact source is the pinned baseline file.
- **Related tests:** tests/test_submission_publication_recommendations.py.
- **Runtime dependencies:** pathlib; services; services.curated_feed; services.recommendation; child.service.
- **Security/safety impact:** Evidence integrity, dependency reproducibility or regression detection; no direct authorization grant.
- **Status:** UNVERIFIED.

### `uploadPost/routes.py`
- **Domain:** uploadPost
- **Why it changed:** Sanitize legacy images, refresh ALLOW visibility and record eligible social feedback.
- **Current responsibility:** Sanitize legacy images, refresh ALLOW visibility and record eligible social feedback; exact source is the pinned baseline file.
- **Related tests:** tests/test_adult_content_hardening.py; tests/test_agent_d_parent_admin.py; tests/test_audio_retirement_runtime.py; tests/test_college_submission_critical_regressions.py; tests/test_content_search.py; tests/test_discovery_privacy.py; tests/test_guardian_verification_fail_closed.py; tests/test_parent_auth_end_to_end_contract.py; tests/test_password_reset.py; tests/test_quiz_server_persistence.py; tests/test_real_postgres_role_smoke.py; tests/test_two_parent_friendship.py; tests/test_usage_heartbeat_visibility.py; tests/test_wave2_security_contract.py; mobile_app/tests/agentC.test.ts; mobile_app/tests/flows.test.ts; mobile_app/tests/onboarding.test.ts.
- **Runtime dependencies:** os; uuid; flask; decorators; config; database.connection; services.social; safety.moderation_service; safety.policy; safety.visual_service; quiz.service; services.audit; services.controls; extensions; services.recommendation_signals; safety.pii_service; services.media_sanitizer; services.media_persistence; services.publication_lifecycle; PIL.
- **Security/safety impact:** Child privacy, eligibility, moderation or privileged server behavior must remain authoritative.
- **Status:** PARTIAL.
