# LittleNet Production Readiness Assessment

**Assessment synchronized:** 2026-09-23  
**Current release-hardening branch:** `fix/release-coherence-20260923`  
**Classification:** **PRODUCTION CANDIDATE — LIVE/DEVICE VERIFICATION PENDING**

Evidence states:

- **IMPLEMENTED** — source exists.
- **AUTOMATED_TESTED** — current automated suite covers the contract.
- **LIVE_SERVICE_VERIFIED** — exercised against the configured external service.
- **DEVICE_VERIFIED** — exercised on a physical Android device using the current artifact.
- **UNVERIFIED** — current evidence is missing.

## Current repository gates

| Gate | State | Evidence / remaining requirement |
|---|---|---|
| Clean PostgreSQL + pgvector bootstrap | **AUTOMATED_TESTED** | CI uses pgvector PostgreSQL and dbmate migrations. |
| Backend regression | **AUTOMATED_TESTED** | Base main passed 407 tests with 2 skips; this re-audit branch must pass CI before merge. |
| Python security + secret scan | **AUTOMATED_TESTED** | Base main green; rerun required on this branch. |
| React Native TypeScript/tests/export | **AUTOMATED_TESTED** | Base main passed typecheck, 83/83 tests and Android export; rerun required after JIT Reel changes. |
| Production OTP secrecy | **AUTOMATED_TESTED** | Production cannot expose/print `dev_code`. |
| Resend lifecycle receiver | **IMPLEMENTED** | Signed webhook handler stores accepted/delivered/bounced/suppressed/failed states. |
| Resend account webhook | **UNVERIFIED** | Connected Resend account currently has no configured webhook; configure it before live release. |
| Private R2 media fallback | **AUTOMATED_TESTED** | Sanitized private MP4 + signed playback remains authoritative fallback. |
| Adaptive Cloudflare Stream | **IMPLEMENTED / LIVE UNVERIFIED** | Real direct upload, real UID/status, signed HLS and R2 fallback exist; remains opt-in pending credentials and live proof. |
| Recommendation/feed sessions | **AUTOMATED_TESTED** | Safe ranking + stable sessions + feedback/impression batching exist. |
| Social Reel JIT playback | **IMPLEMENTED** | Page metadata no longer mints playback credentials for unseen social Reels; current/adjacent player fetches JIT. |
| APK release workflow | **IMPLEMENTED** | EAS workflow now waits for a preview APK, downloads it and retains build/SHA evidence. Must be triggered with real Expo credentials. |
| Parent OTP + Android device authentication | **UNVERIFIED ON DEVICE** | Physical current-APK Parent journey required; face/liveness is retired from scope. |
| Child password login + compulsory quiz | **UNVERIFIED ON DEVICE** | Physical current-APK Child journey required; child face auth is retired from scope. |
| Reel TTFF/rebuffer/background resume | **UNVERIFIED ON DEVICE** | Must be measured on current APK. |
| Two-child publication visibility | **UNVERIFIED ON DEVICE** | Must be proven with two eligible demo children. |
| Push delivery | **UNVERIFIED ON DEVICE** | Requires real Expo device token. |

## Production OTP contract

Production must satisfy:

1. `ENABLE_DEV_OTP` absent or `0`.
2. No production registration/resend response returns `dev_code`.
3. OTP values are not printed to production logs.
4. Resend API acceptance is not treated as delivery.
5. The live Resend webhook points to `/webhooks/resend` and its signing secret is mounted in Modal.
6. Hard-bounced addresses are not automatically unsuppressed.

## Video contract

Moderation samples a bounded 3–8 scene-aware/uniform frame set. If the configured
temporal-coverage requirement cannot be met within the cap, the clip stays
private for REVIEW rather than being auto-published from sparse evidence.

Default safe path:

```text
direct private R2 quarantine
 -> moderation
 -> sanitize / strip user audio
 -> private published R2 MP4 + poster
 -> authorized signed playback
```

Optional adaptive path when explicitly configured:

```text
same sanitized MP4
 -> Cloudflare Stream one-time private direct upload
 -> real Stream UID
 -> ENCODING
 -> readiness poll
 -> READY
 -> short-lived signed HLS
```

If Stream is unavailable, not configured, still encoding or token generation fails, LittleNet returns to the private sanitized R2 MP4. Stream is not a moderation authority and never bypasses the LittleNet ALLOW gate.

## Final release requirement

Do not label LittleNet **PRODUCTION READY** until the current merged commit has:

1. green backend/security/mobile CI on the exact release commit;
2. verified Neon restore point plus guarded retained-DB reconciliation with zero pending migrations;
3. live `littlemuse-ai` + `littlemuse-web` deployment and strict dependency preflight;
4. enabled Resend webhook + delivered OTP evidence;
5. current EAS preview APK artifact built against the verified live URL;
6. physical Android Parent OTP → device-auth → child password → quiz journey;
7. safe image and Reel ALLOW/playback journey;
8. second-child visibility plus Parent control/chat enforcement;
9. REVIEW/BLOCK non-leakage;
10. push delivery if push is part of the demo claim;
11. raw staging load evidence before making high-scale performance claims.
