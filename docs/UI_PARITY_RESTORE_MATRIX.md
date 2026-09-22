# UI Parity Restore Matrix

_Last audited: 2026-09-14 against Google Stitch ZIP and React Native branch `feature/submission-readiness-fixes`._

## Authority and scoring

- **Primary visual authority:** `.conversation/attached_assets/stitch_instagram_ui_clone_1789325739406.zip`
- **Functional implementation:** `mobile_app/` (React Native + Expo)
- **Secondary gap reference only:** `feature/submission-rebuild-v2/mobile_flutter/`
- Percentages are conservative visual/interaction parity estimates, not functional test results.
- A consolidated React Native screen may implement several Stitch states. Rows remain separate so missing sheets, editors and warning states cannot be hidden by route consolidation.
- `IN PROGRESS` identifies screens included in the current shared visual restoration pass. It does not mean final parity is complete.

## Global Stitch contract

| Area | Stitch requirement | React Native restoration target |
|---|---|---|
| Brand/action | `#0095F6`, pressed `#1877F2` | Shared semantic tokens; primary CTAs and active navigation |
| Surfaces | `#FFFFFF`, scaffold `#FAFAFA` | Flat, zero-shadow surfaces with media-led composition |
| Text/dividers | `#262626`, muted `#737373`/`#8E8E8E`, line `#DBDBDB` | Compact hierarchy and hairline separators |
| Safety | ALLOW `#00BA88`, REVIEW `#F59E0B`, BLOCK/heart `#ED4956` | Shared status colors and explanatory states |
| Geometry | 8pt grid, 8px controls, circular avatars, edge-to-edge media | Replace oversized cards/pills where Stitch is compact |
| Navigation | 44–48px top bars; 50–54px five-item bottom bar | Compact Instagram-style app chrome |
| Stories | Orange/pink/violet unread ring; gray seen ring | Shared story-ring component and segmented viewer progress |

## 61-state matrix

| # | Final screen/state | Stitch source folder | Current React Native screen | Parity | Missing visual/interaction elements | Status |
|---:|---|---|---|---:|---|---|
| 01 | Splash Screen | `01_03_splash_parent_login/` | `mobile_app/src/screens/WelcomeLogin.tsx` | 45% | Logo-led splash timing, animation and exact auto-route presentation | PARTIAL |
| 02 | Choose User / Role Switcher | `02_04_choose_user_child_login/` | `mobile_app/src/screens/WelcomeLogin.tsx` | 55% | Stitch role cards, compact app bar and exact child/parent artwork | PARTIAL |
| 03 | Parent Login & Signup | `01_03_splash_parent_login/` | `mobile_app/src/screens/WelcomeLogin.tsx; mobile_app/src/screens/ParentOnboarding.tsx` | 55% | Exact Stitch form density, password recovery placement and OTP transition styling | PARTIAL |
| 04 | Child Login (password) | `01_02_04_login_child_face_login_instagram_clone/` | `mobile_app/src/screens/WelcomeLogin.tsx` | 55% | Role-specific header and quick-switch presentation (face-login camera treatment removed 2026-09-22) | PARTIAL |
| 05 | Create Child Account | `05_06_child_account_setup_guardian_consent/` | `mobile_app/src/screens/Parent.tsx` | 60% | Avatar/interest selection and Stitch step hierarchy | PARTIAL |
| 06 | Parent-Child Linking & Consent | `05_06_child_account_setup_guardian_consent/` | `mobile_app/src/screens/Parent.tsx` | 50% | Pairing/consent visual state and completion confirmation | PARTIAL |
| 07 | ~~Face Enrollment / Liveness~~ | — | REMOVED 2026-09-22 | — | Face enrollment removed; children log in with password | REMOVED |
| 08 | Kids Home Feed | `08_kids_home_feed_instagram_clone/` | `mobile_app/src/screens/kids/FeedScreen.tsx` | 60% | Exact compact header, edge-to-edge media/actions and story-ring treatment | IN PROGRESS |
| 09 | Feed Tabs (For You/Friends/Learn) | `08_kids_home_feed_instagram_clone/` | `mobile_app/src/screens/kids/FeedScreen.tsx` | 55% | Friends remains constrained by the existing feed contract; tab selector and Learn filtering are wired | PARTIAL |
| 10 | Post Detail | `10_11_post_detail_safe_comments_instagram_clone/` | `mobile_app/src/screens/kids/PostDetailScreen.tsx` | 65% | Edge-to-edge media remains limited by shared Card geometry; actions and creator safety menu are wired | PARTIAL |
| 11 | Safe Comments & Replies | `10_11_post_detail_safe_comments_instagram_clone/` | `mobile_app/src/screens/kids/PostDetailScreen.tsx` | 55% | Comment submit/review state is wired; reply threading and dedicated PII sheet are not exposed by the current API | PARTIAL |
| 12 | Create Post & Media Picker | `12_create_post_media_picker_instagram_clone/` | `mobile_app/src/screens/kids/CreateScreen.tsx` | 50% | Grid picker, multi-select state, audience sheet and compact toolbar | PARTIAL |
| 13 | Post Preview & AI Safety Check | `13_50_post_preview_ai_safety_check/` | `mobile_app/src/screens/kids/ProcessingScreen.tsx` | 50% | Preview composition plus ALLOW/REVIEW/BLOCK evidence cards | PARTIAL |
| 14 | Share / Direct Send Sheet | `14_share_send_direct_sheet_instagram_clone/` | `mobile_app/src/screens/kids/PostDetailScreen.tsx; mobile_app/src/api/kidsChat.ts` | 65% | Dedicated recipient sheet, approved connection list, avatars and sent state are wired; recipient search is still limited | PARTIAL |
| 15 | Report / Hide Options Sheet | `15_49_report_options_sheet_instagram_clone/` | `mobile_app/src/screens/kids/PostDetailScreen.tsx` | 55% | Exact Stitch bottom-sheet animation; hide is device-local because no hide API exists | PARTIAL |
| 16 | Story Viewer | `16_story_viewer_instagram_clone/` | `mobile_app/src/screens/kids/StoriesScreen.tsx` | 50% | Full-screen media, segmented timing, reactions and pause/resume | IN PROGRESS |
| 17 | Create Story Camera | `17_18_story_camera_creator_instagram_clone/` | `mobile_app/src/screens/kids/CreateScreen.tsx` | 35% | Full-screen camera controls, flash/flip and shutter presentation | PARTIAL |
| 18 | Story Editor & Stickers | `18_19_story_editor_stickers/` | `mobile_app/src/screens/kids/CreateScreen.tsx` | 10% | Overlay text, stickers, drawing and undo/redo editor | MISSING DEDICATED UI |
| 19 | Story Safety Check & Publish | `18_19_story_editor_stickers/` | `mobile_app/src/screens/kids/ProcessingScreen.tsx` | 35% | Story-specific preview, safety state and publish confirmation | PARTIAL |
| 20 | Safe Reels Feed | `20_safe_reels_feed_instagram_clone/` | `mobile_app/src/screens/kids/ReelsScreen.tsx` | 55% | Full-screen paging, right action rail and audio attribution | IN PROGRESS |
| 21 | Reel Comments | `10_11_post_detail_safe_comments_instagram_clone/` | `mobile_app/src/screens/kids/PostDetailScreen.tsx` | 25% | Reel-overlay comment sheet and keyboard state | PARTIAL |
| 22 | Create Reel Studio | `22_23_create_reel_studio_instagram_clone/` | `mobile_app/src/screens/kids/CreateScreen.tsx` | 35% | Recording timer, hands-free/flip controls and clip manager | PARTIAL |
| 23 | Reel Editor | `22_23_create_reel_studio_instagram_clone/` | `mobile_app/src/screens/kids/CreateScreen.tsx` | 10% | Clip timeline, trim controls, overlays and audio-level UI | MISSING DEDICATED UI |
| 24 | Reel Preview & Moderation | `24_reel_preview_moderation/` | `mobile_app/src/screens/kids/ProcessingScreen.tsx` | 35% | 9:16 preview, safety evidence breakdown and edit/publish actions | PARTIAL |
| 25 | Reel Detail & Audio Page | `25_reel_detail_audio_page/` | `mobile_app/src/screens/kids/ReelsScreen.tsx` | 10% | Audio detail route, related reels grid and Use Audio action | MISSING DEDICATED UI |
| 26 | Explore Grid | `26_27_explore_safe_search_instagram_clone/` | `mobile_app/src/screens/kids/DiscoverScreen.tsx` | 60% | Explore result grid is wired; staggered media tiles remain constrained by available result fields | PARTIAL |
| 27 | Safe Search Input | `26_27_explore_safe_search_instagram_clone/` | `mobile_app/src/screens/kids/DiscoverScreen.tsx` | 70% | Search bar, local recent searches and People/Posts/Reels/Learn tabs are wired | PARTIAL |
| 28 | Safe Search Results | `28_29_safe_search_blocked_warning/` | `mobile_app/src/screens/kids/DiscoverScreen.tsx` | 55% | Grouped People/content filtering is wired; follow-state actions remain profile-owned | PARTIAL |
| 29 | Blocked / Unsafe Search Warning | `28_29_safe_search_blocked_warning/` | `mobile_app/src/screens/kids/DiscoverScreen.tsx` | 50% | Backend PII warning is shown through the shared gate treatment; dedicated Learn Why CTA is unavailable | PARTIAL |
| 30 | Messages & DM Inbox | `30_messages_dm_inbox_instagram_clone/` | `mobile_app/src/screens/kids/ConversationsScreen.tsx` | 55% | Exact inbox rows, unread badges, shield and new-message action | PARTIAL |
| 31 | Direct Safe Chat | `31_35_direct_safe_chat_instagram_clone/` | `mobile_app/src/screens/kids/ChatScreen.tsx` | 55% | Stitch bubbles, sticky composer, attachment and long-press actions | PARTIAL |
| 32 | New Message & Friend Picker | `32_new_message_friend_picker/` | `mobile_app/src/screens/kids/SocialStates.tsx; mobile_app/src/screens/kids/ConversationsScreen.tsx` | 65% | Dedicated approved-friend picker and search are wired; group selection is not supported by the existing chat API | PARTIAL |
| 33 | Group Chat | `33_group_chat_robotics_team/` | `mobile_app/src/screens/kids/ChatScreen.tsx` | 25% | Group header, participant state, shared attachment cards | PARTIAL |
| 34 | Chat Details & Safety Controls | `34_chat_details_safety_instagram_clone/` | `mobile_app/src/screens/kids/SocialStates.tsx; mobile_app/src/screens/kids/ChatScreen.tsx` | 65% | Dedicated details route and mute/block/report controls are wired; shared-media history is not returned by the API | PARTIAL |
| 35 | Unsafe Message / PII Warning | `31_35_safe_chat_message_warning/` | `mobile_app/src/screens/kids/ChatScreen.tsx` | 40% | Blurred quarantined bubble and Ask Parent explanation sheet | PARTIAL |
| 36 | My Profile & Highlights | `36_my_profile_highlights_rebuilt/` | `mobile_app/src/screens/kids/OwnProfileScreen.tsx` | 55% | Exact profile header, highlights carousel and three-tab grid | IN PROGRESS |
| 37 | Other User Profile | `37_other_user_profile_maya_draws/` | `mobile_app/src/screens/kids/OtherProfileScreen.tsx` | 50% | Mutuals, requested/follow state and Stitch grid geometry | PARTIAL |
| 38 | Edit Profile | `38_edit_profile/` | `mobile_app/src/screens/kids/SocialStates.tsx; mobile_app/src/screens/kids/OwnProfileScreen.tsx` | 60% | Dedicated form and PUT wiring are present; avatar picker and guardian-managed interests remain unavailable | PARTIAL |
| 39 | Followers & Following Directory | `39_40_friends_directory_requests/` | `mobile_app/src/screens/kids/SocialStates.tsx` | 60% | Dedicated Followers/Following tabs and profile navigation are wired; relationship actions remain API-dependent | PARTIAL |
| 40 | Friend / Follow Requests | `39_40_followers_requests_instagram_clone/` | `mobile_app/src/screens/parent/ParentScreens.tsx` | 25% | Child-facing request list and accept/decline/block presentation | PARTIAL |
| 41 | Saved Content Hub | `41_saved_content_posts_reels_learning/` | `mobile_app/src/screens/kids/SocialStates.tsx; mobile_app/src/screens/kids/OwnProfileScreen.tsx` | 65% | Dedicated Posts/Reels/Learning tabs use the saved API; category chips are not present in the response contract | PARTIAL |
| 42 | Notifications Centre | `42_notifications_centre_instagram_clone/` | `mobile_app/src/screens/kids/NotificationsScreen.tsx` | 60% | Category filters, thumbnails, follow actions and safety styling | PARTIAL |
| 43 | Learning Hub & Quizzes | `43_learning_hub_quizzes_instagram_clone/` | `mobile_app/src/screens/Quiz.tsx` | 55% | Live quiz-bank topic hub and session entry are wired; streak, active challenge cards and subject filters are not returned by the API | IN PROGRESS |
| 44 | Educational Feed & Reels | `44_45_educational_feed_quiz_hub/` | `mobile_app/src/screens/Quiz.tsx` | 20% | Honest educational-content notice is shown; dedicated educational playlist and in-video prompts are not supported by the current API/navigation | PARTIAL |
| 45 | Quiz List & Challenges | `44_45_educational_feed_quiz_hub/` | `mobile_app/src/screens/Quiz.tsx` | 50% | Returned quiz bank is presented with topic chips and practice entry; filterable difficulty/challenge metadata is unavailable | PARTIAL |
| 46 | Quiz Play & Results | `46_47_quiz_play_challenges_instagram_clone/` | `mobile_app/src/screens/Quiz.tsx` | 75% | Server-authoritative answer feedback, progress, XP and practice results are wired; exact Stitch celebration remains | IN PROGRESS |
| 47 | Learning Challenges & Missions | `47_learning_challenges_missions/` | `mobile_app/src/screens/Quiz.tsx` | 20% | No dedicated route or challenge/mission contract exists; hub documents the gap rather than fabricating progress | PARTIAL |
| 48 | Safety Centre | `48_49_safety_centre_report_instagram_clone/` | `mobile_app/src/screens/kids/SafetyScreens.tsx` | 55% | Exact Stitch resource artwork and a dedicated parent-help route are unavailable in child navigation | PARTIAL |
| 49 | Report User / Content Flow | `49_50_safety_report_moderation_flow/` | `mobile_app/src/screens/kids/PostDetailScreen.tsx; mobile_app/src/api/kidsSocial.ts` | 70% | Exact confirmation sheet and comment/message entry points remain | PARTIAL |
| 50 | Moderation Result | `13_50_post_preview_ai_safety_check/` | `mobile_app/src/screens/kids/ProcessingScreen.tsx` | 45% | Full ALLOW/REVIEW/BLOCK explanation and action variants | PARTIAL |
| 51 | Report History & Status | `51_safety_report_history_status/` | `mobile_app/src/screens/kids/SafetyScreens.tsx; mobile_app/src/api/kidsSocial.ts` | 65% | Exact status timeline/detail treatment is not represented by the current API response | PARTIAL |
| 52 | Parent Dashboard | `52_53_54_parent_dashboard_alerts_instagram_clone/` | `mobile_app/src/screens/parent/ParentScreens.tsx` | 68% | Child switcher and server usage progress are wired; circular usage gauge and pause-app treatment are unavailable | IN PROGRESS |
| 53 | Child Activity Telemetry | `53_54_parent_activity_alerts/` | `mobile_app/src/screens/parent/ParentScreens.tsx` | 55% | Usage graph, recent contacts and quiz telemetry visualizations | PARTIAL |
| 54 | Parent Alerts | `53_54_parent_activity_alerts/` | `mobile_app/src/screens/parent/ParentScreens.tsx` | 50% | Priority grouping, safety thumbnails and action hierarchy | PARTIAL |
| 55 | Parent Review & Flagged Items | `55_parent_review_moderation/` | `mobile_app/src/screens/parent/ParentScreens.tsx` | 70% | Evidence preview, risk/status labeling and approve/block actions are wired; split evidence layout and reason chips remain | IN PROGRESS |
| 56 | Screen-Time Dashboard | `56_57_61_screen_time_smart_controls_instagram_clone/` | `mobile_app/src/screens/parent/ParentScreens.tsx` | 68% | Server-backed usage bar, limit editor and strict mode are wired; schedule visualization and day selector are unavailable | IN PROGRESS |
| 57 | Smart Controls & Toggles | `56_57_61_screen_time_smart_controls_instagram_clone/` | `mobile_app/src/screens/parent/ParentScreens.tsx` | 72% | Grouped Stitch switches, category chips, descriptions and save feedback are wired; advanced schedules are unavailable | IN PROGRESS |
| 58 | Admin Safety Operations Dashboard | `58_admin_safety_operations_dashboard/` | `mobile_app/src/screens/admin/AdminScreens.tsx` | 72% | Priority callout, live counts, loading/error/empty states and audit route are wired; accuracy/throughput metrics are not returned | IN PROGRESS |
| 59 | Admin Moderation Queue | `59_60_admin_moderation_ai_evidence_instagram_clone/` | `mobile_app/src/screens/admin/AdminScreens.tsx` | 68% | Compact triage rows, risk accents, evidence type and refresh states are wired; filter chips are unavailable | IN PROGRESS |
| 60 | Admin Review & AI Evidence | `59_60_admin_moderation_ai_evidence_instagram_clone/` | `mobile_app/src/screens/admin/AdminScreens.tsx` | 68% | Private media/text evidence, risk/status, notes and approve/block/escalate actions are wired; model-signal visualization is not returned | IN PROGRESS |
| 61 | Settings & Guardian Preferences | `61_settings_safety_preferences/` | `mobile_app/src/screens/parent/ParentScreens.tsx` | 50% | Language/security groups and linked-guardian status presentation | PARTIAL |

## Release evidence note

The 2026-09-14 source-level release checks pass for the current mobile
candidate: 80 mobile tests, TypeScript typecheck, Android export, and Expo
dependency alignment. Expo Doctor remains 19/21 because of tool metadata
warnings; this matrix does not treat those warnings as proof of native
incompatibility. Physical Android evidence is still `DEVICE-UNVERIFIED`, and
no visual row is upgraded to `COMPLETE` without a device or emulator run for
critical interactions.

## Completion rule

A row can move to **COMPLETE** only when its visible states match the corresponding Stitch screenshot/HTML at a mobile viewport, all existing API/security behavior remains wired, TypeScript and React Native tests pass, and the interaction is included in device or emulator evidence where the state is critical.
