# Deployment Readiness (evidence-based, partial)

| Area | Status | Evidence |
|---|---|---|
| Backend code | PARTIALLY READY | later blocks still pending; this block did not rerun the full suite |
| Database | EXTERNAL VERIFICATION REQUIRED | PG16 + pgvector required; this machine has none; Neon not contacted |
| R2 | EXTERNAL VERIFICATION REQUIRED | later storage work exists; live R2 not contacted here |
| Resend | EXTERNAL VERIFICATION REQUIRED | not contacted |
| Modal / AI | BLOCKED until real model weights are pulled via Git LFS | weights are pointers in this package |
| Expo/EAS | PARTIALLY READY | package `com.littlenet.app`, app `1.0.2` / versionCode `3`; preview = internal APK; `usesCleartextTraffic=false`; no cloud EAS build in this block |
| Android APK | EXTERNAL VERIFICATION REQUIRED | preview profile builds APK; not built here |
| OTP / auth residuals | ALREADY FIXED / VERIFIED | mock coverage for parent signup/verify/resend, reset verify, approval tokens; residual: forgot-password still returns `user_id`+`masked_email` for real accounts |
| Profile / follow | ALREADY FIXED / VERIFIED | `child_id` = requester, `following_child_id` = target; friendship counts are symmetric by design |
| Stories | ALREADY FIXED / VERIFIED | hooks stay unconditional; empty/error/exit/media fallbacks remain |
| Health / readiness | ALREADY FIXED / VERIFIED | `/healthz`, `/readyz`, `/api/mobile/v1/health` stay leak-safe |
| Mobile API URL | FIXED (this block) | production rejects cleartext plus RFC1918 / CGNAT / link-local / IPv6 ULA; `tools/set_backend_url.py` writes Expo `.env` only |
| Env templates | VERIFIED (this block) | root `.env.example` placeholders; Expo only `EXPO_PUBLIC_API_BASE_URL` |

Overall: **PARTIALLY READY — remaining work is full regression / docs consolidation / ZIP, not this config block.**
