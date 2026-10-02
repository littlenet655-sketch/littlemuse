# LittleNet Completion Changelog

## Final completion pass  -  September 2026

### Kids Mode UI
- Reworked the existing Jinja/CSS interface into a child-native mobile UI with larger tap targets, bright high-contrast tokens, rounded cards, labeled five-item bottom navigation, candy Story rings, empty states and reduced-motion support.
- Added accessible animated like/save controls, smooth Clips/Reels snap scrolling, visible-video playback and Story navigation without changing the Flask/Jinja stack.

### Parent/Admin UI
- Parent dashboard now shows real online/offline state, daily usage, pending reviews, 7-day behavior score and recent quiz activity.
- Parent Review shows ALLOW/REVIEW/BLOCK context plus adult, weapon, violence and toxicity signals. REVIEW media stays blurred until the parent explicitly reveals it.
- Admin console now supports users, reports, model/risk scores, audit history, account suspension, REVIEW blocking and explicit post removal.

### Parent controls
- Added server-enforced quiet hours with timezone support and active-session redirect.
- Posting, Clips/Reels, Stories, Messaging and Discover permissions remain server-enforced.
- Content-category and educational-only feed controls remain enforced on every child-facing content surface.

### Social safety
- Feed and Clips/Reels now use the child's own content plus parent-approved connections only.
- Likes/comments require an approved connection for another child's post.
- Direct post access is relationship-aware.
- Discover no longer uses a global random child directory; suggestions come from the approved network, same school, or same parent family context.
- Safety BLOCK/REVIEW events create Parent Mode notifications and send best-effort email alerts when SMTP is configured.

### AI hardening
- Standardized moderation signal keys and max-score ensemble behavior.
- Added per-model timeout guards and optional feature-flagged extra NSFW/text classifiers.
- Preserved hard block for adult/sexual >= 0.40 and weapon >= 0.45.
- Preserved fail-closed behavior for total model outage and REVIEW behavior for partial failures without hard-block evidence.
- Video moderation continues to inspect sampled frames and extracted audio.

### Learning
- Expanded demo seed data so each supported quiz age group has enough safe science, kindness and digital-safety questions.
- Added child Learn card, learning challenges, points/history and Parent Mode learning report.

### Deployment and verification
- Lightweight web and heavyweight AI deployments remain split (`Dockerfile.web`, `Dockerfile.ai`, `modal_ai.py`).
- `/healthz` checks web/database; `/readyz` also checks AI readiness.
- Current source evidence: 122 tests, 110 Flask routes, 64 templates, 41/41 scope checks.
