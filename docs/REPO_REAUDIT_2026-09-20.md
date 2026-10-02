# LittleNet Repository Re-audit — 20 September 2026

## Scope

This re-audit compares the current React Native/Flask repository with the Monday demo requirements and rechecks stale branches, current source, CI contracts, media delivery, recommendation paths, OTP/mail handling and release automation.

Base main before this re-audit: `5ea6e8354de3deab6a45fb9444720583066cc26e`.

## Branch reconciliation

Open PRs were zero at the start of this pass.

The historical Agent A/B/C/D, Antigravity audit, submission and video-recommendation branches are behind current main and have no current-main-ahead commits to merge. Two divergent old branches contain legacy hardening/Flutter-era work and are intentionally not merged wholesale because current React Native main already supersedes their relevant contracts.

## Monday requirement matrix

| Requirement | Source status | Automated evidence | Live/device evidence still required |
|---|---|---|---|
| Parent signup | Implemented | Backend contracts/CI | clean live account run |
| Resend OTP | Implemented + delivery lifecycle | Tests + security CI | webhook account config + delivered inbox |
| Guardian face | Implemented | face/state suites | physical Android |
| Child enrollment/login | Implemented | face/gate suites | physical Android |
| Safe image upload | Implemented | state/concurrency tests | live R2/AI/device |
| Reel upload/playback | Implemented | player/API tests | physical playback |
| 18+ fail-closed moderation | Implemented | policy/moderation suites | benchmark if accuracy is claimed |
| Cross-user visibility | Implemented | publication/feed tests | two-child device journey |
| APK pipeline | Implemented | RN tests/export; EAS workflow | trigger + install artifact |

## New source fixes from this re-audit

- Implemented an opt-in Cloudflare Stream adapter using a real one-time direct upload URL with signed playback required from creation.
- Persist real Stream UIDs and processing state; poll readiness; serve signed HLS only when READY.
- Preserve private sanitized R2 MP4 as the failure/encoding fallback.
- Added optional local Stream JWT signing for high token volume, with the Cloudflare token API as lower-volume fallback.
- Added video-delivery preflight without exposing provider credentials.
- Changed social Reel page hydration to JIT playback credentials instead of minting a token for every unseen page item.
- Fixed refreshed playback-expiry state on mobile.
- Kept poster visible until a real first-frame callback rather than merely `readyToPlay`.
- Corrected first completion vs replay telemetry and initial loading vs rebuffer semantics.
- Prevented duplicate cumulative Reel telemetry flushes.
- Reworked the EAS workflow to wait for the preview APK, validate success, download it and retain SHA/build metadata.
- Removed a committed default bearer token from k6 and made load tests staging-only with explicit credentials.
- Marked the Python high-load helper honestly as an in-process regression profiler rather than 1000-user production evidence.
- Updated deployment/env contracts for Modal-native queueing and optional adaptive video.

## Still intentionally unclaimed

No source audit can certify a physical camera, real inbox, real GPU moderation call, real CDN stream, physical Reel decoder behavior, or two-user device visibility without executing those systems. Those remain manual/live gates.
