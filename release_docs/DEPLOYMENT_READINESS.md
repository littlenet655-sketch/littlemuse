# Deployment Readiness — CURRENT FINAL RELEASE RESULT

**Status: DEPLOYMENT READY WITH EXTERNAL REQUIREMENTS**

The source at this freeze (parent `826e633`) is locally green. The package is
**not** fully production verified. Remaining blockers are external
infrastructure and device testing.

| Area | Status | Evidence |
|---|---|---|
| Backend source | LOCALLY VERIFIED | 898 passed / 2 skipped / 0 failed |
| Mobile source | LOCALLY VERIFIED | 283 passed / 0 failed; TypeScript passed |
| TypeScript / Expo | LOCALLY VERIFIED | Expo Doctor 21/21; Android export passed |
| Database (disposable) | VERIFIED | PostgreSQL 16.15 + pgvector 0.8.7; **43/43** migrations from zero |
| Latest migration | VERIFIED | `20261002120000_outbox_trigger_attempts_reset.sql` |
| Database (Neon) | EXTERNAL REQUIREMENT | production Neon was not contacted |
| Cloudflare R2 | EXTERNAL REQUIREMENT | live R2 was not contacted |
| Resend | EXTERNAL REQUIREMENT | live email/OTP delivery was not contacted |
| Modal | EXTERNAL REQUIREMENT | current Modal source was not deployed from this HEAD |
| Custom model payloads | LOCALLY VERIFIED | Real V2/V3 `.pth` and text `model.safetensors` |
| EAS preview APK | EXTERNAL REQUIREMENT | preview profile is internal APK; no cloud build from this source |
| Physical device | EXTERNAL REQUIREMENT | no install/smoke from this exact source |
| CI scanners | NOT RUN LOCALLY | `pip-audit`, `bandit`, `gitleaks` are CI-only; not source failures |

## External requirements before live submission

1. Configure production secrets (never put them in Expo; only `EXPO_PUBLIC_API_BASE_URL` is public).
2. Verify live Neon connection (direct endpoint; `sslmode=require`).
3. Verify live Cloudflare R2 (private bucket, signed URLs, no public read).
4. Verify Resend email/OTP delivery.
5. Deploy current Modal source and verify settings (scale-to-zero, GPU confined to `ai_web` / `warm_models`).
6. Run the EAS preview APK cloud build.
7. Install the APK on an actual Android device.
8. Run final physical-device smoke tests (`PHYSICAL_DEVICE_CHECKLIST.md`).
9. Verify a legitimate live Parent Review event.
10. Probe actual R2 Reel files with ffprobe.

Also run CI-only security tooling in CI: `pip-audit`, `bandit`, `gitleaks`.
Do not treat their local absence as a source-code failure.

## What this status does not mean

- It does not mean live production was exercised.
- It does not mean an APK from this exact HEAD is already installed on a phone.
