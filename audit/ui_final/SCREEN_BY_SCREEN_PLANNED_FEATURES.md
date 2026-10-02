# LittleNet V2: Complete Product Blueprint & Screen-by-Screen Planned Features

## 1. Complete Project Vision & Architectural Idea

### The Core Problem
Mainstream social media platforms (Instagram, TikTok, YouTube Shorts) are built for dopamine retention and advertisement revenue, exposing children to predatory actors, toxic algorithms, cyberbullying, explicit content, and data harvesting. Conversely, existing "kids apps" are often infantile, unappealing, and quickly abandoned by older children (ages 9–14) who crave the real social feeling of sharing media, connecting with school peers, and exploring trends.

### The LittleNet Solution
**LittleNet** is a modern, media-first, Instagram-grade social media platform re-engineered from the ground up for kids aged 6–18, supervised by verified guardians and guarded by a multi-layer server-side AI safety engine.

### Three Unified Roles & Surfaces
1. **Child (Ages 6–13 / 14–18)**:
   - Media-first Instagram familiarity: Stories rail, fullscreen vertical Reels, Explore grid, direct messaging with approved connections, and interactive profiles.
   - Child-safe content: Positive interactions, zero public metrics anxiety (no public follower competition), gamified educational learning quizzes, and strict PII pre-filtering.
2. **Parent / Guardian**:
   - Legally compliant onboarding via Email OTP and AI Facial Liveness Verification.
   - Real-time guardian dashboard: Screen time allowances, feature toggles (enable/disable Reels, Stories, public discovery), connection request approvals, and flagged content safety review queue.
3. **Safety Moderator / Operator**:
   - Professional operational dark-slate console: Real-time incident review queue with split-pane inspector, AI risk scoring, server-side immutable decisions (Approve, Block, Escalate), and permanent audit trail.

---

## 2. Screen-by-Screen Feature Blueprint

Below is the exhaustive specification of every planned feature, component, safety contract, and visual refinement target for each of the 39 rendered screens.

---

### AUTHENTICATION & ONBOARDING

#### `01_login.png` — Role-Aware Universal Authentication
- **User Role**: Child, Parent, Moderator
- **Planned Features**:
  - Unified credential login (Username/Email + Password) with secure token retrieval (`POST /api/mobile/v1/auth/login`).
  - Interactive role switcher tab / visual chips (Child, Parent, Moderator) allowing seamless role-specific shell routing.
  - "Parent Sign Up" direct CTA for new families.
  - Password visibility toggle, inline input validation, and automatic session restoration on app restart.
- **Safety & Guardrails**:
  - Suspended account blocking (`403 Account Suspended`).
  - Rate limiting (5 attempts/min) to prevent credential brute-forcing.
- **Visual Enhancement Target**:
  - Sleek modern gradient background, subtle logo pulse micro-animation, elevated soft-shadow authentication card, and high-contrast primary CTA.

---

#### `02_parent_signup.png` — Guardian Legal Registration
- **User Role**: Parent
- **Planned Features**:
  - Multi-field guardian registration form (Full Legal Name, Email, Password, Date of Birth).
  - COPPA / Child Safety Legal Consent checkbox with expandable policy terms.
  - One-tap submission to trigger OTP delivery (`POST /api/mobile/v1/auth/register-parent`).
- **Safety & Guardrails**:
  - Under-age restriction (parent must be 18+).
  - Disposable email rejection and strong password policy enforcement (min 8 chars, uppercase, digit, symbol).
- **Visual Enhancement Target**:
  - Step-by-step progress stepper (Step 1 of 3: Account Info -> Step 2: Email OTP -> Step 3: Face Liveness), floating input labels with green checkmark validation.

---

#### `03_email_otp.png` — Two-Factor Email Verification
- **User Role**: Parent
- **Planned Features**:
  - 6-digit individual box PIN input with automatic focus advancement and backspace support.
  - Resend OTP countdown timer (60-second cooldown).
  - Automatic submission upon 6th digit entry (`POST /api/mobile/v1/auth/verify-email-otp`).
- **Safety & Guardrails**:
  - 10-minute expiry token with maximum 3 verification attempts before invalidation.
- **Visual Enhancement Target**:
  - Active box glow with primary accent border, shake animation on invalid OTP, and clean contextual email indicator badge.

---

#### `04_parent_liveness.png` — AI Face Liveness & Anti-Spoofing Check
- **User Role**: Parent
- **Planned Features**:
  - Real-time circular camera viewport with dynamic oval guide overlay.
  - Motion challenge guidance (Blink, Turn Left, Smile) or active anti-spoofing analysis.
  - Instant server-side verification (`POST /api/mobile/v1/auth/parent-liveness`).
- **Safety & Guardrails**:
  - ~~DeepFace / FaceNet embedding verification~~ — REMOVED 2026-09-22: all face/biometric verification deleted by product decision; child password login + parent email OTP instead.
  - Guarantees child cannot impersonate a parent to self-approve permissions.
- **Visual Enhancement Target**:
  - Pulsing animated scan ring around the camera viewport, high-contrast instruction pill with icon states (Scanning -> Success).

---

#### `05_child_enrollment.png` — Guardian-Assisted Child Account Provisioning
- **User Role**: Parent
- **Planned Features**:
  - Child profile setup: First name, chosen unique `@username`, date of birth / age selector (6–18).
  - Initial safety tier preset selection (Strict for ages 6–9, Balanced for 10–13, Teen for 14+).
  - Optional biometric face enrollment for child login safety.
  - Submission creates supervised child account (`POST /api/mobile/v1/parent/children`).
- **Safety & Guardrails**:
  - Account is permanently linked to the creating parent's `parent_id`.
  - Child username PII filter (rejects phone numbers, real full names, address words).
- **Visual Enhancement Target**:
  - Colorful age-bracket illustration cards, avatar preset carousel (animals, astronauts, superheroes), smooth stepper animation.

---

### KIDS SOCIAL EXPERIENCE

#### `06_home.png` — Media-First Social Home Feed
- **User Role**: Child
- **Planned Features**:
  - Top Stories rail with active unread story rings, "+ Add Story" button for child.
  - Top AppBar: Clean LittleNet wordmark logo, Notifications bell (with unread badge), Direct Messages paper airplane icon.
  - Media feed stream: High-resolution post cards, author avatar, username, category badge ("LittleNet Pick", "Science", "Crafts").
  - Post interaction row: Like heart, Comment bubble, Save bookmark.
  - Expandable caption, hashtags, and quick comment preview.
  - Contextual banner for remaining daily screen time.
- **Safety & Guardrails**:
  - Zero public like counts or follower counts displayed on feed to prevent social anxiety.
  - All displayed posts are pre-filtered (`is_safe=TRUE` and `moderation_status='ALLOWED'`).
- **Visual Enhancement Target**:
  - High-saturation Instagram-style story gradient rings (purple-to-orange), skeleton shimmer loading cards, double-tap heart particle animation on like.

---

#### `07_search_explore.png` — Curated Visual Discovery & Category Hub
- **User Role**: Child
- **Planned Features**:
  - Top search bar with clear button and real-time query debounce.
  - Horizontal scrolling category pill rail (`✨ All`, `🚀 Science`, `🎨 Art`, `💻 Coding`, `📐 Math`, `🌿 Nature`, `🎵 Music`, `📖 Books`).
  - 4 Discovery Tabs:
    - **Top**: Algorithmic blend of high-engagement educational content.
    - **Posts**: 3-column staggered visual media grid.
    - **People**: Verified school peers, age-bracket-matched classmates.
    - **Learning**: Quiz challenges and interactive lessons.
  - Tap on media item opens full-screen interactive preview modal.
- **Safety & Guardrails**:
  - Search input PII filter (warns immediately if child types a phone number or address).
  - Search results exclude any account outside child's allowed visibility scope.
- **Visual Enhancement Target**:
  - Staggered masonry grid layout with subtle video preview badges, glassmorphic search bar background, tactile chip press animations.

---

#### `08_feed.png` — Dedicated Social Post Stream View
- **User Role**: Child
- **Planned Features**:
  - Infinite scrolling feed with cursor-based pagination (`GET /api/mobile/v2/kids/feed`).
  - Full-width media container with 4:5 social aspect ratio support.
  - Like button with instant optimistic UI toggle and haptic feedback.
  - Comment count button opening the interactive Comments Sheet.
  - Subtle post category badge and author timestamp.
- **Safety & Guardrails**:
  - Report Post button on top-right menu (`Report for Bullying, PII, Inappropriate Content`).
- **Visual Enhancement Target**:
  - Edge-to-edge media rendering, smooth image fade-in with blurhash placeholders, refined micro-typography.

---

#### `09_reels.png` — Full-Screen Vertical Video Experience
- **User Role**: Child
- **Planned Features**:
  - 9:16 edge-to-edge full-screen vertical video feed with snap-to-page physics.
  - Unobtrusive bottom-left overlay: Author avatar, @username, audio track name, caption, category tag.
  - Right-side vertical action column: Like heart with counter, Comment icon, Share/Save bookmark.
  - Tap to pause/play overlay icon.
- **Safety & Guardrails**:
  - Video content is scanned for motion-based explicit content and audio transcript toxicity.
  - Guardian can toggle Reels off completely via Parent Controls.
- **Visual Enhancement Target**:
  - Cinematic gradient overlay behind bottom text for 100% legibility on bright backgrounds, animated sound-wave indicator for audio track.

---

#### `10_create_post.png` — Creative Expression Studio
- **User Role**: Child
- **Planned Features**:
  - Creation type selector pills: **Post**, **Reel**, **Story**.
  - Photo/Video selector with device gallery integration and camera capture.
  - Caption text area with character counter and emoji bar.
  - Audience target age-bracket selectors (`ALL`, `6-8`, `9-11`, `12-13`, `14-18`).
  - Category tag selector (`Art`, `Science`, `Gaming`, `Pets`, `Fun`).
- **Safety & Guardrails**:
  - Instant client-side PII check (checks caption for phone, address, email, full names).
  - Server-side asynchronous moderation pipeline on upload before content goes live.
- **Visual Enhancement Target**:
  - Rounded media preview card with remove/replace overlay, vibrant primary "Share Post" button with loading spinner state.

---

#### `11_comments.png` — Positive & Kind Interactive Comments Sheet
- **User Role**: Child
- **Planned Features**:
  - Slide-up bottom sheet with grab handle and dismiss gesture.
  - Comment thread listing with user avatar, username, time ago, and comment text.
  - Sticky bottom input bar with send button and quick-reaction emoji chips (`❤️`, `👏`, `⭐`, `🔥`, `🎉`).
- **Safety & Guardrails**:
  - Real-time toxicity & cyberbullying sentiment scan on submission.
  - Blocks harmful slurs, insults, and personal contact solicitations immediately.
- **Visual Enhancement Target**:
  - Smooth slide-up transition, keyboard avoidance padding, friendly placeholder: *"Be kind and encouraging..."*.

---

#### `12_messages.png` — Approved Connections Inbox
- **User Role**: Child
- **Planned Features**:
  - Direct message conversation list with peer avatar, name, last message preview, and timestamp.
  - Search bar to filter conversations.
  - Online active presence indicator dot.
  - Tap opens dedicated direct message conversation.
- **Safety & Guardrails**:
  - Only approved connections can start a conversation.
  - Stranger messaging is strictly impossible under LittleNet protocol.
- **Visual Enhancement Target**:
  - Unread conversation counter badge, sleek card separation with swipe actions (Mute, Archive).

---

#### `13_chat.png` — Safe Direct Messaging Conversation
- **User Role**: Child
- **Planned Features**:
  - WhatsApp/iMessage-style chat bubbles with sender vs receiver color coding.
  - Top header with peer avatar, name, and connection status.
  - Bottom input bar with text field, emoji picker, and image attachment button.
  - Message status indicators (Sent, Delivered, Read).
- **Safety & Guardrails**:
  - Safety banner at top: *"Messages in LittleNet are supervised for safety. Never share passwords or home address."*
  - Image attachments undergo immediate automated safety scan.
- **Visual Enhancement Target**:
  - Soft pastel speech bubbles with rounded corners, message delivery animation, haptic feedback on send.

---

#### `14_profile.png` — Instagram-Grade Child Profile
- **User Role**: Child
- **Planned Features**:
  - Profile header: Large avatar with verified badge, @username, full name.
  - 3 Interactive Statistics Columns:
    - **Posts** (displays count)
    - **Friends** (tappable, opens Followers list)
    - **Following** (tappable, opens Following list)
  - Custom Bio and Interest chips (`Space`, `Robotics`, `Drawing`).
  - "Edit Profile" primary action button.
  - Tabbed media grid: **Posts** (3-column grid), **Reels**, **Saved**.
- **Safety & Guardrails**:
  - Child's phone number, email, and location are never exposed on the profile.
- **Visual Enhancement Target**:
  - Clean 3-column media grid with aspect ratio 1:1, crisp metric counter typography, sleek profile settings cog icon in AppBar.

---

#### `15_edit_profile.png` — Profile Customizer
- **User Role**: Child
- **Planned Features**:
  - Avatar tap-to-change action with camera/gallery sheet.
  - Full Name input, Bio multi-line text input (max 150 chars).
  - Multi-select interest chips (e.g. Science, Football, Chess, Music).
  - Save Changes button updating backend (`POST /api/mobile/v1/kids/profile`).
- **Safety & Guardrails**:
  - Bio text is analyzed for personal contact details and PII before saving.
- **Visual Enhancement Target**:
  - Camera overlay badge on avatar, character countdown, green feedback toast on save.

---

### SETTINGS & MICRO PAGES

#### `16_settings.png` — Settings Hub
- **User Role**: Child
- **Planned Features**:
  - Grouped navigation menu: Account, Privacy, Safety, Notifications, Screen Time, Guardian Controls, Blocked, Muted, Help & About.
  - Session user summary card.
  - "Log Out" outlined danger button.
- **Visual Enhancement Target**:
  - iOS-style grouped section cards with colorful icon badges and chevron arrows.

---

#### `17_privacy.png` — Privacy Configuration
- **User Role**: Child
- **Planned Features**:
  - "Allow Search Discovery" toggle.
  - "Direct Messages from Classmates" toggle.
  - "Activity Status Visible" toggle.
- **Safety & Guardrails**:
  - Locked to most restrictive state if parent sets Strict Mode.

---

#### `18_safety.png` — AI Safety Engine Information
- **User Role**: Child
- **Planned Features**:
  - Informative cards explaining how LittleNet's automated safety scanner protects the child.
  - Safety Sensitivity Level indicator (`STRICT`, `BALANCED`).
  - "Report an Emergency / Contact Guardian" quick button.

---

#### `19_notifications.png` — Push Notification Preferences
- **User Role**: Child
- **Planned Features**:
  - Toggles for Post Likes, New Comments, Friend Requests, Learning Reminders, and Daily Screen Time Alerts.

---

#### `20_screen_time.png` — Digital Wellness & Daily Usage
- **User Role**: Child
- **Planned Features**:
  - Circular progress ring showing minutes used today vs daily guardian allowance (e.g., 25 / 60 min).
  - Visual breakdown: Social Feed vs Learning Quizzes vs Chat.
  - Bedtime schedule reminder countdown.
- **Safety & Guardrails**:
  - Child cannot override limits set by the parent.

---

#### `21_parent_controls_info.png` — Active Guardian Rules Viewer
- **User Role**: Child
- **Planned Features**:
  - Read-only transparent view of the rules set by the parent: Reels enabled/disabled, Stories enabled/disabled, Bedtime lock hours.
  - Teaches transparency between parents and children.

---

#### `22_blocked_users.png` — Blocked Accounts Manager
- **User Role**: Child
- **Planned Features**:
  - List of blocked accounts with avatar, name, and date blocked.
  - "Unblock" action button with confirmation dialog.

---

#### `23_muted_users.png` — Muted Accounts Manager
- **User Role**: Child
- **Planned Features**:
  - List of muted users (posts/stories hidden without blocking).
  - "Unmute" quick action button.

---

#### `24_help_about.png` — Compliance & App Information
- **User Role**: Child, Parent
- **Planned Features**:
  - App build version, COPPA compliance certification statement, Child Safety Hotline links, Terms of Service.

---

### LEARNING & SOCIAL CONNECTION

#### `25_learning.png` — Educational Hub
- **User Role**: Child
- **Planned Features**:
  - Interactive learning course modules: Science, Space, Coding, Math, Nature.
  - Progress bar per module, earned badges, and daily quiz streak counter.
- **Visual Enhancement Target**:
  - Vibrant card graphics, gamified star icons, level badges.

---

#### `26_quiz.png` — Interactive Gamified Quiz
- **User Role**: Child
- **Planned Features**:
  - Multiple-choice question card with timer.
  - Instant visual feedback: green for correct, gentle red for incorrect with friendly explanation.
  - Score summary and streak reward points upon completion.

---

#### `27_discovery.png` — Peer Discovery & Community Recommendations
- **User Role**: Child
- **Planned Features**:
  - Suggested classmate cards with shared interests (e.g. "Also likes Astronomy").
  - "Send Request" primary button with state change to "Pending".

---

#### `28_followers_following.png` — Connections Manager
- **User Role**: Child
- **Planned Features**:
  - 3 Top Tabs: **Followers (Friends)**, **Following**, **Suggested**.
  - Real-time search bar to search connection names.
  - Action buttons: "Unfollow", "Message", "Remove".
- **Visual Enhancement Target**:
  - Instagram-identical layout with user avatars, full name, @username, and clean pill action buttons.

---

#### `29_requests.png` — Connection Requests Gate
- **User Role**: Child
- **Planned Features**:
  - Two Tabs: **Received Requests**, **Sent Requests**.
  - Action buttons: "Confirm" (green filled) and "Delete" (light gray outlined).
- **Safety & Guardrails**:
  - Once child confirms, connection goes to the parent for final sign-off if guardian rules require approval.

---

### PARENT GUARDIAN SUITE

#### `30_parent_dashboard.png` — Guardian Supervision Console
- **User Role**: Parent
- **Planned Features**:
  - Child selector pill rail (switch between multiple enrolled children).
  - Real-time metrics: Today's Screen Time, Flagged Incidents, Pending Connection Requests.
  - Quick action shortcuts: "Set Limits", "Review Safety", "Pending Requests", "Add Child".
- **Visual Enhancement Target**:
  - Clean calming white & slate design, high-contrast KPI cards, reassurance cues.

---

#### `31_parent_controls.png` — Feature & Safety Gate Controls
- **User Role**: Parent
- **Planned Features**:
  - Feature switches: Allow Reels, Allow Stories, Educational-Only Mode.
  - Safety filter strictness slider (Strict, Moderate, Relaxed).
  - Save Changes button (`POST /api/mobile/v1/parent/children/<id>/controls`).

---

#### `32_parent_screen_time.png` — Usage Limits & Bedtime Lock
- **User Role**: Parent
- **Planned Features**:
  - Daily Screen Time allowance slider (30 min to 180 min).
  - Bedtime schedule time pickers (e.g., Lock app from 8:30 PM to 7:00 AM).
  - "Lock App Now" instant emergency kill-switch.

---

#### `33_parent_safety_review.png` — Flagged Content Guardian Review
- **User Role**: Parent
- **Planned Features**:
  - Feed of posts or messages flagged by the AI safety scanner for the child.
  - Card displays flagged image/text, AI risk reason ("Potential personal phone number detected"), and risk score.
  - Actions: **Allow** (Approve) or **Keep Blocked**.

---

#### `34_parent_follow_requests.png` — Guardian Connection Sign-Off
- **User Role**: Parent
- **Planned Features**:
  - Displays other children requesting to connect with the user's child.
  - Shows requester's age, mutual friends, and school/community tag.
  - Actions: **Approve Connection** or **Decline**.

---

### SAFETY MODERATOR & ADMIN CONSOLE

#### `35_moderator_dashboard.png` — Operations Command Center
- **User Role**: Safety Moderator / Admin
- **Planned Features**:
  - Dark-slate operational theme (`#0F172A`).
  - Active Safety Engine status banner with live pulse indicator.
  - Real-time KPI metrics: Open Reviews, Enrolled Children, Verified Parents, Total Users.
  - Quick shortcuts to Incident Queue, User Directory, and Audit Log.
  - Recent incident previews in queue with risk badges.

---

#### `36_moderation_queue.png` — Server-Side Human Review Gate
- **User Role**: Safety Moderator / Admin
- **Planned Features**:
  - Filter Tabs: **All**, **Critical (Risk >= 70%)**, **Review Required (Risk < 70%)**.
  - Split-pane layout on wide screens (Queue list on left, full case detail on right).
  - Incident cards showing author, content type (IMAGE, VIDEO, TEXT), AI flag reason, risk percentage.
  - Inline Quick Actions: **Block**, **Escalate**, **Approve**.
- **Safety & Guardrails**:
  - System hard-blocks cannot be overridden if safety policy marks them non-reviewable.

---

#### `37_incident_detail.png` — Full Forensic Incident Inspector
- **User Role**: Safety Moderator / Admin
- **Planned Features**:
  - Comprehensive case dossier: Event ID, Child ID, Content ID, timestamp.
  - High-resolution media preview (post image/video or message text).
  - AI Safety Score meter with color-coded severity.
  - Detailed reason breakdown (Vision AI, Text Toxicity, PII Detection).
  - Moderator Notes input field for audit trail recording.
  - Action buttons: **Approve Content**, **Escalate to Senior**, **Confirm Block**.

---

#### `38_user_admin.png` — User Directory & Compliance Management
- **User Role**: Safety Moderator / Admin
- **Planned Features**:
  - Real-time searchable user directory by name, @username, or email.
  - Role filter chips: All Users, Children, Parents, Admins.
  - Account status badges (`ACTIVE`, `PENDING_APPROVAL`, `SUSPENDED`).
  - Tap opens Account Inspector modal with user details and **Suspend Account / Reactivate Account** actions.
- **Safety & Guardrails**:
  - Admin cannot suspend their own session account.
  - Every status change writes to immutable `activity_logs`.

---

#### `39_moderator_audit.png` — Immutable Server Activity Audit Trail
- **User Role**: Safety Moderator / Admin
- **Planned Features**:
  - Chronological feed of all moderator decisions and system compliance events.
  - Cards show event type (`MODERATION_APPROVE`, `MODERATION_BLOCK`, `USER_SUSPENDED`), timestamp, moderator ID, target user ID, and JSON metadata.
  - Read-only integrity to comply with child data protection laws.

---

## 3. Summary of Visual Strengthening Recommendations

To make the UI visual appearance even stronger and more impactful:
1. **Typography**: Adopt Google Fonts *Outfit* or *Plus Jakarta Sans* for modern geometric headings, and *Inter* for body readability.
2. **Micro-Interactions**: Add double-tap heart bursting particles on post media, tactile bounce on bottom navigation icons, and shimmer skeleton loaders.
3. **Contrast & Hierarchy**: Enhance border dividers with subtle hairline borders (`#F1F5F9`), introduce high-contrast gradient cards for Stories, and elevate the dark-slate operations styling for the Moderator console.
4. **Color Tokens**: Standardize child accent colors to LittleNet Indigo (`#4F46E5`), Coral (`#F43F5E`), and Sky (`#0EA5E9`), with soothing emerald green (`#10B981`) for safety verifications.
