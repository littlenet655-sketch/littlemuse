# LittleNet Physical Device Checklist

This is the required evidence sheet for the preview APK. It must be completed on
an Android device or emulator after installing the APK. Do not change a status
to `PASS` without executing the journey and recording the evidence filename.

Allowed statuses:

- **PASS** — executed successfully with the named evidence.
- **FAIL** — executed and failed with the named evidence.
- **BLOCKED** — could not be executed because a prerequisite, service, device,
  or credential was unavailable.

APK artifact: **UNVERIFIED — no current-HEAD APK was built; do not reuse the obsolete preview artifact.**
Backend: `https://netlittle2--littlenet-web-web.modal.run`

| # | Journey | Status | Evidence filename | Notes |
|---:|---|---|---|---|
| 1 | Install preview APK | BLOCKED | `device/01_apk_install.log` | APK artifact is reachable, but this workstation has no `adb`, Android emulator, or other Android install target. |
| 2 | Launch app and confirm backend connection | BLOCKED | `device/02_launch_backend.log` | Backend `/healthz` returned HTTP 200, but the APK could not be installed or launched. |
| 3 | Parent signup form validation | BLOCKED | `device/03_parent_signup.log` | Requires an installed APK and Android UI interaction. |
| 4 | Parent OTP email delivery | BLOCKED | `device/04_parent_otp_delivery.log` | Current live API/Resend evidence is recorded separately in `FINAL_E2E_MATRIX.md`; the APK journey was not run. |
| 5 | Parent OTP entry and verification | BLOCKED | `device/05_parent_otp_verify.log` | Requires an installed APK and a completed OTP delivery journey. |
| 6 | ~~Guardian liveness/adult verification~~ | REMOVED 2026-09-22 | — | Face/liveness verification removed by product decision; parent identity is email-OTP-only, Parent Mode is gated by Android device auth. |
| 7 | Child enrollment by verified parent | BLOCKED | `device/07_child_enrollment.log` | Requires completed parent verification in the installed app. |
| 8 | Child password login | BLOCKED | `device/08_child_password_login.log` | Requires a created child account and password. |
| 9 | Mandatory onboarding quiz | BLOCKED | `device/09_onboarding_quiz.log` | Requires child login in the installed app. |
| 10 | Kids feed shows approved content | BLOCKED | `device/10_feed.log` | Requires child login and device-rendered feed evidence. |
| 11 | Stories viewer and progress | BLOCKED | `device/11_stories.log` | Requires child login and an Android run. |
| 12 | Reels playback, pause, retry, save | BLOCKED | `device/12_reels.log` | Requires child login and Android media playback. |
| 13 | Explore and search states | BLOCKED | `device/13_explore_search.log` | Requires child login and device interaction. |
| 14 | Create ALLOW image post | BLOCKED | `device/14_allow_image_post.log` | Requires Android camera/gallery, R2 upload, and the installed app. |
| 15 | ALLOW post refreshes profile/feed | BLOCKED | `device/15_allow_refresh.log` | Requires a successful on-device ALLOW post. |
| 16 | REVIEW content stays private | BLOCKED | `device/16_review_privacy.log` | Requires on-device media creation and review evidence. |
| 17 | BLOCK content is not public | BLOCKED | `device/17_block_privacy.log` | Requires on-device media creation and blocked-feed evidence. |
| 18 | Parent safety queue displays REVIEW | BLOCKED | `device/18_parent_review_queue.log` | Requires parent session and review media created through the device journey. |
| 19 | Parent approves REVIEW content | BLOCKED | `device/19_parent_approve.log` | Requires parent queue journey in the installed app. |
| 20 | Parent disables messaging | BLOCKED | `device/20_parent_messaging_control.log` | Requires parent and child sessions in the installed app. |
| 21 | Screen-time limit locks child | BLOCKED | `device/21_screen_time.log` | Requires a clock-controlled Android device journey. |
| 22 | Quiet hours lock child | BLOCKED | `device/22_quiet_hours.log` | Requires parent control setup and an Android run. |
| 23 | Category controls affect feed | BLOCKED | `device/23_category_controls.log` | Requires parent control setup and eligible device-rendered content. |
| 24 | Follow approval lifecycle | BLOCKED | `device/24_follow_approval.log` | Requires two child accounts and parent approval in the installed app. |
| 25 | Text chat send/read | BLOCKED | `device/25_text_chat.log` | Requires an approved connection and two device sessions. |
| 26 | Chat mute/block/report safety actions | BLOCKED | `device/26_chat_safety.log` | Requires an approved connection and Android safety-action journey. |
| 27 | Notifications and mark-read | BLOCKED | `device/27_notifications.log` | Requires generated notification events and an installed app. |
| 28 | Saved content and unsave | BLOCKED | `device/28_saved_content.log` | Requires child login and eligible content in the installed app. |
| 29 | Profile, connections, and comments | BLOCKED | `device/29_profile_social.log` | Requires child login and social fixtures in the installed app. |
| 30 | Admin moderation queue | BLOCKED | `device/30_admin_queue.log` | Requires admin session and moderation fixtures in the installed app. |
| 31 | Admin evidence and moderation action | BLOCKED | `device/31_admin_action.log` | Requires admin session and review fixture in the installed app. |
| 32 | Logout and session restoration | BLOCKED | `device/32_logout_restore.log` | Requires a completed authenticated Android session. |
| 33 | Safe recommendation filtering | BLOCKED | `device/33_recommendation_safety.log` | Requires eligible content plus block/mute/age controls in the installed app. |
| 34 | App recovers from offline/API error | BLOCKED | `device/34_offline_error.log` | Requires installed APK and a controlled Android network interruption. |
| 35 | Final clean relaunch and evidence bundle | BLOCKED | `device/35_final_relaunch.log` | Requires all preceding Android journeys and screenshots. |

The current non-device evidence is recorded in
`docs/FINAL_E2E_MATRIX.md` and `docs/KNOWN_LIMITATIONS.md`. The `BLOCKED`
entries above are not claims that the implementation is absent; they identify
journeys that still need real device evidence.

## Device run record

- Run date: 2026-09-14
- Target: none available; `adb`, Android emulator, and `scrcpy` were not present.
- APK artifact availability: no current-HEAD APK; installation was not attempted.
- Backend probe: `https://netlittle2--littlenet-web-web.modal.run/healthz`
  returned HTTP 200 with `{"database":true,"status":"ok"}`.
- Result: 0/35 journeys executed on Android; all rows are `BLOCKED`.
- Evidence format: per-row `.log` files record the prerequisite and the
  observed blocker. No screenshot is claimed where no Android surface existed.