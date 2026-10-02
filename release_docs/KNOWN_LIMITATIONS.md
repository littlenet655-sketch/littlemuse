# Known Limitations — current residuals only

**CURRENT FINAL RELEASE RESULT** residuals for this release-candidate package.
Fixed items from earlier RC commits are not repeated here.

## Source residuals (real, still present)

1. **Forgot-password response can reveal whether an account exists.**
   `POST /api/mobile/v1/auth/forgot-password` returns `user_id` / `masked_email` /
   `is_parent_proxy` for a matching eligible account because the current mobile
   reset screen requires `user_id`. Deferred: needs a coordinated server + client
   reset-handle redesign. Mitigated by per-IP limits and no OTP being sent for
   unknown accounts.

2. **Parent email resend returns HTTP 503 for cooldown / already-verified.**
   `POST /api/mobile/v1/auth/parent/resend-email` uses `200` on success and `503`
   when `resend_parent_email_otp` returns false (cooldown or already verified).
   The JSON `error` string is still returned. This is a client-contract residual,
   not a missing cooldown.

3. **Discover / suggested still does per-row follow lookups.**
   Suggested listing size is 15. Each row calls `is_following` / `is_follow_pending`.
   Not redesigned.

4. **No hashed Python lockfile / `--require-hashes`.**
   Direct pins exist in `requirements-core.txt`, `requirements-text.txt`,
   `requirements-safety.txt`, and `requirements-ai.txt`. Transitive packages float.
   `mobile_app/package-lock.json` is present and `npm ci --dry-run` passed.
   Blind full pinning of the ML stack was intentionally not done.

## External / not executed here (not source failures)

5. No live Neon, Cloudflare R2, Resend, or Modal verification was performed.
6. No live R2 Reel ffprobe data (0 local videos in this tree).
7. No EAS cloud APK was built from this exact final source.
8. No physical-device test was run from this exact final source.
9. CI-only scanners were not run locally: `pip-audit`, `bandit`, `gitleaks`.
    These are not source-code failures.

See `release_docs/DEPLOYMENT_READINESS.md` for the external-requirements list.
