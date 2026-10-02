# Final Fix Report — release-candidate (CURRENT)

Significant fixes on `release-candidate` after baseline `ac9be32`, through
technical baseline `f4be262`. This is the **CURRENT** RC fix record.
Older root `FINAL_FIX_REPORT.md` (2026-09-21) is a **HISTORICAL RESULT**.

| Area | What changed |
|---|---|
| Upload-session timezone | `upload_sessions.expires_at` written as aware UTC; completion expiry decided in SQL |
| Processing retry/backoff clock | Retry-backoff age computed by PostgreSQL, not a UTC-relabelled naive timestamp |
| Parent approval token expiry | Compared in SQL on the DB clock (was ~5.5 h too long under `Asia/Kolkata`) |
| Quiz-latch endpoint bypass | Reel-scoped 428 `quiz_required` on `/api/mobile/v2/media/playback` and `/api/mobile/v2/curated/media` |
| Mobile HTTP 428 quiz handoff | Playback 428 stops fetch, calls `onQuizRequired`, no generic error / retry storm |
| Logout / 401 stale-request | Cancel-then-clear queries; clear before server logout; token-aware 401 handler |
| Polling bounds | Adaptive Demo Boost intervals; parent email-delivery poll capped; other audited pollers bounded |
| Parent Review blocked-content republish | Effective decision after downgrade logic; APPROVE cannot resurrect a BLOCKED post; web chat review fail-closed |
| R2 delete retry hardening | `reconcile_pending_deletes` bounded to `attempts < 8` |
| Traversal reference rejection | `_unsafe_local_media_ref` rejects `..` / leading `/` (HTTP 400) |
| Git LFS pointer checkpoint rejection | `safety/model_files.py` treats LFS pointers as unavailable; trained-text gate requires a real weight file |
| Demo Boost idle-window restore | Restore autoscaler first; mark OFF only on success so a failed restore is retried |
| Upload byte/MIME hardening | Stored-byte caps (not Content-Length only); finalize requires exact size + declared MIME |
| Avatar / chat EXIF stripping | Profile and web-chat images sanitized before moderation; published images re-encoded |
| OTP resend attempt-reset | Parent OTP attempts carry over while a live code exists; reset only after expiry |
| dbmate checksum validation | `modal_web.py` uses the same SHA-256 pin as the Dockerfiles |
| API URL private-network rejection | Production rejects cleartext plus RFC1918 / CGNAT / link-local / IPv6 ULA |
| Expo SDK 57 configuration | Splash via `expo-splash-screen` plugin; `usesCleartextTraffic=false` via `plugins/withCleartextDisabled.js` |
| tzdata Windows fix | `tzdata==2025.2` so Windows `ZoneInfo` resolves `Asia/Kolkata` |

## Verification used

Authoritative local regression on `f4be262`: backend 885/1 skipped/0 failed;
mobile 281/0; TypeScript passed; Expo Doctor 21/21; Android export passed;
42/42 migrations on disposable PostgreSQL 16.15 + pgvector 0.8.7.

Live Neon / R2 / Resend / Modal / EAS / device were **not** executed.
