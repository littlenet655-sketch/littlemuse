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

2. **transformers 5.10.0 is a yanked PyPI release but is the exact version validated with the current LittleNet trained text model. Upgrade deferred to a separately tested dependency-refresh cycle.**
   Canonical pins are `requirements-text.txt` and `modal_ai.py`
   (`transformers==5.10.0`). Root `requirements.txt` still has
   `transformers>=4.40.0` as a compatibility leftover; it is **not** used by
   Docker, Modal, or CI (those install `requirements-text.txt` /
   `requirements-ai.txt` / inline Modal pins). Do not treat the root range as
   the production AI runtime.

3. **Parent email resend returns HTTP 503 for cooldown / already-verified.**
   `POST /api/mobile/v1/auth/parent/resend-email` uses `200` on success and `503`
   when `resend_parent_email_otp` returns false (cooldown or already verified).
   The JSON `error` string is still returned. This is a client-contract residual,
   not a missing cooldown.

4. **Discover / suggested still does per-row follow lookups.**
   Suggested listing size is 15. Each row calls `is_following` / `is_follow_pending`.
   Not redesigned.

5. **No hashed Python lockfile / `--require-hashes`.**
   Direct pins exist in `requirements-core.txt`, `requirements-text.txt`,
   `requirements-safety.txt`, and `requirements-ai.txt`. Transitive packages float.
   `mobile_app/package-lock.json` is present and `npm ci --dry-run` passed.
   Blind full pinning of the ML stack was intentionally not done.

6. **Demo Boost idle-window restore is lazy.**
   Expiry restore uses the configured scaledown windows on the existing
   `status()` / `stop()` poll path. There is no permanent scheduled GPU worker.

## External / not executed here (not source failures)

7. No live Neon, Cloudflare R2, Resend, or Modal verification was performed.
8. No live R2 Reel ffprobe data (0 local videos in this tree).
9. No EAS cloud APK was built from this exact final source.
10. No physical-device test was run from this exact final source.
11. CI-only scanners were not run locally: `pip-audit`, `bandit`, `gitleaks`.
    These are not source-code failures.

See `release_docs/DEPLOYMENT_READINESS.md` for the external-requirements list.
