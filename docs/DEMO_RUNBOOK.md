# LittleNet Predictable Demo Runbook

## Prepare without production changes

1. Use a disposable/local PostgreSQL database and apply `database/schema.sql`, `database/upgrade.sql`, `database/friendship_upgrade.sql`, then all `db/migrations` in order (the repository scripts/workflows automate this).
2. Run the idempotent quiz seed/migrations and prepare one Parent, two Children, and one Admin in the disposable environment. Never record demo passwords in committed docs.
3. Configure backend-only mail/R2/Modal values in the authorized non-production environment. Configure the app only with `EXPO_PUBLIC_API_BASE_URL`.
4. Pre-test one safe image and one controlled REVIEW fixture. Do not rely on random or disturbing external content during the presentation.
5. Run the validation commands in `README.md` and record actual results in `docs/FINAL_E2E_MATRIX.md`.

## Twelve-step viva sequence

1. Parent login and dashboard summaries.
2. Child detail, screen usage, and weekly quiz summary.
3. Child password login and the required onboarding/recurring quiz gate.
4. Kids feed, discover, reels, stories, and profile.
5. Upload the prepared safe image through direct upload.
6. Show PROCESSING and the resulting ALLOWED profile/feed refresh.
7. Open the prepared private REVIEW event in Parent Mode.
8. Approve or block it and show the queue refresh.
9. Disable messaging or discover in Parent controls.
10. Refresh the Child surface and show the server-returned disabled state; re-enable it for the rest of the demo.
11. Show an approved friendship/chat and explain the two-parent gate.
12. Show Admin moderation detail/action and the resulting audit entry.

## Recovery steps

- Backend unavailable: confirm the non-secret base URL and `/api/mobile/v1/health`; do not point the app at an unapproved production environment.
- Login rejected: confirm the live account is ACTIVE and the selected role matches; do not bypass verification.
- Child remains gated: complete the quiz step reported by `/api/mobile/v1/me`.
- Upload stalled: use the existing status/redrive contract; do not publish quarantine bytes manually.
- REVIEW preview unavailable: retain the event and retry the authorized delivery path; never make the bucket public.
- Controls appear stale: pull-to-refresh the Child/Parent screen. The next protected Child request is authoritative.
- EAS unavailable: use the verified Android export as code-level evidence and report APK installation as UNVERIFIED until an authorized build is produced.
