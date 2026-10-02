# Release Checklist — CURRENT FINAL RELEASE RESULT

Technical baseline: `f4be262`. Docs/packaging commit follows.

## Locally completed

- [x] Backend tests: **885 passed / 1 skipped / 0 failed**
- [x] Single skip identified: `test_agent_c_notifications_read.py` (non-localhost hostname)
- [x] Mobile tests: **281 passed / 0 failed**
- [x] TypeScript: passed
- [x] Expo Doctor: **21/21**
- [x] Android Expo export: passed
- [x] Migrations from zero: **42/42** on PostgreSQL 16.15 + pgvector 0.8.7
- [x] compileall / `audit_all` / `audit_dynamic_sql` / `npm ci --dry-run`: passed
- [x] HTTP 428 quiz handoff + server latch on the two playback bypass routes
- [x] Logout / 401 amplification fixed
- [x] Timestamp skew fixed at upload / backoff / approval-token sites
- [x] Parent Review authorization + blocked-content republish guard
- [x] R2 delete retry bound; traversal refs rejected; LFS pointers rejected as weights
- [x] Health/readiness leak-safe
- [x] README / release identity / readiness docs reconciled
- [x] `ARTIFACT_MANIFEST.sha256` regenerated (LFS pointers annotated as pointers)
- [x] Final source ZIP packaged and integrity-checked

## External — required before live submission (not source failures)

- [ ] `git lfs pull` of actual custom model payloads
- [ ] Production secrets configured
- [ ] Live Neon connection verified
- [ ] Live Cloudflare R2 verified
- [ ] Resend email/OTP delivery verified
- [ ] Current Modal source deployed and settings verified
- [ ] EAS preview APK cloud build from this exact HEAD
- [ ] APK installed on a physical Android device
- [ ] Physical-device smoke tests
- [ ] Legitimate live Parent Review event
- [ ] Live R2 Reel ffprobe
- [ ] CI scanners: pip-audit, bandit, gitleaks
