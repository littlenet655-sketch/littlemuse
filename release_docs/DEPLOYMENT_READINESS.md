# Deployment Readiness (evidence-based, after final local regression)

| Area | Status | Evidence |
|---|---|---|
| Backend code | LOCALLY VERIFIED | `pytest tests/ -q`: **885 passed, 1 skipped, 0 failed** in 53.60s against disposable PG16+pgvector |
| Database (local) | VERIFIED on disposable PG16 | `pgvector/pgvector:pg16` (PostgreSQL 16.15, `vector` 0.8.7); `init_db.py` + dbmate **42 applied / 0 pending** |
| Database (Neon) | EXTERNAL VERIFICATION REQUIRED | production Neon was not contacted |
| R2 | EXTERNAL VERIFICATION REQUIRED | live R2 not contacted |
| Resend | EXTERNAL VERIFICATION REQUIRED | not contacted |
| Modal / AI | BLOCKED until real model weights are pulled via Git LFS | weights remain LFS pointers in this package |
| Expo/EAS | LOCALLY VERIFIED / no cloud build | `npx expo-doctor` 21/21; `npm run export:android` exit 0; package `com.littlenet.app`, app `1.0.2` / versionCode `3`; cleartext still disabled via prebuild plugin; no EAS cloud build |
| Android APK | EXTERNAL VERIFICATION REQUIRED | preview profile builds APK; not built here (no EAS) |
| Mobile tests | LOCALLY VERIFIED | `npm test` **281 passed, 0 failed**; `npm run typecheck` exit 0 |
| OTP / auth residuals | ALREADY FIXED / VERIFIED | mock coverage for parent signup/verify/resend, reset verify, approval tokens; residual: forgot-password still returns `user_id`+`masked_email` for real accounts |
| Profile / follow | ALREADY FIXED / VERIFIED | `child_id` = requester, `following_child_id` = target; friendship counts are symmetric by design |
| Stories | ALREADY FIXED / VERIFIED | hooks stay unconditional; empty/error/exit/media fallbacks remain |
| Health / readiness | ALREADY FIXED / VERIFIED | `/healthz`, `/readyz`, `/api/mobile/v1/health` stay leak-safe |
| Mobile API URL | FIXED | production rejects cleartext plus RFC1918 / CGNAT / link-local / IPv6 ULA; `tools/set_backend_url.py` writes Expo `.env` only |
| Env templates | VERIFIED | root `.env.example` placeholders; Expo only `EXPO_PUBLIC_API_BASE_URL` |

Overall: **LOCAL REGRESSION COMPLETE.** Remaining release work is docs consolidation / `RELEASE_IDENTITY` / `ARTIFACT_MANIFEST` / ZIP, plus owner external verification (Neon, R2, Resend, Modal, EAS APK).
