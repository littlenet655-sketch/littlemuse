# LittleNet — Current Known Limitations

_Last re-audited: 22 September 2026._

This file lists only limitations that remain after the final React Native/mobile API hardening pass. Older gaps such as conversation pagination, social notifications, native post/story deletion, story avatar normalization, and child face authentication are not current gaps.

## External/live verification still required

1. **Production credentials and deployment evidence** — Neon/PostgreSQL, private R2, Modal, Resend and Expo/EAS credentials are intentionally not stored in Git. The source is wired for them, but the final live preflight must be run after those secrets are configured.
2. **Physical Android validation** — React Native typecheck/tests/export pass in CI, but the final APK still needs installation and the full Parent → Child → upload → moderation → second-child journey on a real Android device.
3. **Push delivery** — Expo device-token registration/unregistration and backend notification dispatch are implemented; physical push receipt still needs Firebase/APNs/EAS credentials and a real device.
4. **Cross-user publication evidence** — source contracts cover publication invalidation and feed eligibility, but a live two-account run should prove Child A ALLOW content appears for eligible Child B.
5. **Real-device Reel measurements** — one-active-player, buffering/retry, signed playback and background behavior are implemented; TTFF/rebuffer metrics require a real network/device measurement.
6. **Optional Cloudflare Stream** — private Stream integration remains opt-in. R2 is the current safe fallback; do not enable Stream until its credentials and live playback path are verified.
7. **Bounded video moderation** — the release policy intentionally caps visual moderation at 8 scene-aware/uniform frames. Longer clips that cannot satisfy the temporal-coverage contract are REVIEW-only rather than being silently auto-published.

## Evidence limitations, not missing product features

- The historical `audit/ui_final/` screenshot archive predates the final password-only authentication and latest UI hardening. Current code is the source of truth until a fresh screenshot capture is made from the release APK.
- Do not claim a production moderation-accuracy percentage until the labelled held-out benchmark protocol has been executed and retained.
- Do not claim Instagram/YouTube-scale capacity from local profilers alone; production scale requires staged load evidence.

## Intentionally out of scope

- unrestricted user-generated audio or voice messaging;
- group chat;
- advanced story/reel editing;
- standalone child signup;
- child or guardian face authentication.

These are scope decisions, not incomplete implementation.
