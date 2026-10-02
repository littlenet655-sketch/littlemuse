# Deployment Readiness (evidence-based, partial)

| Area | Status | Evidence |
|---|---|---|
| Backend code | PARTIALLY READY | 783 tests pass locally; audit incomplete |
| Database | EXTERNAL VERIFICATION REQUIRED | 42 migrations apply on PG16 + pgvector (pgvector is required); Neon not contacted |
| R2 | EXTERNAL VERIFICATION REQUIRED | not audited; not contacted |
| Resend | EXTERNAL VERIFICATION REQUIRED | not contacted |
| Modal / AI | BLOCKED until real model weights are pulled via Git LFS | weights are pointers in this package |
| Expo/EAS | PARTIALLY READY | tsc, 281 tests, export OK, Doctor 19/21 (2 network-only); no cloud build run |
| Android APK | EXTERNAL VERIFICATION REQUIRED | preview profile builds APK; not built here |

Overall: **PARTIALLY READY — not a finished release candidate.**
