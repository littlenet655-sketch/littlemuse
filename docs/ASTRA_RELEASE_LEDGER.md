# LittleNet Release Ledger

**Baseline before hardening:** `5d266677dd369e982e768fdda6fd35d6df342648`  
**Hardening branch:** `fix/release-coherence-20260923`  
**Current branch commit at ledger rewrite:** `74675518aaffb85e54ba0027e43cc90d4848146b`  
**Date:** 2026-09-23

This is the sole current progress tracker. Older audits/ledgers remain historical
evidence only when they reference retired face flows, old Modal identities or old
APK artifacts.

| Domain | Current source state | Remaining proof | Status |
|---|---|---|---|
| Release identity | Expo/EAS and Modal web/AI identities normalized; drift tests added | CI + live deploy | PATCHED / VERIFY |
| Parent auth | Email OTP + guardian declaration + Android system auth; face retired | Physical Parent journey | IMPLEMENTED / DEVICE PENDING |
| Child auth/quiz | Password login + server-authoritative quiz gates; feed interval 5 | Physical Child journey | IMPLEMENTED / DEVICE PENDING |
| Feed/Explore/Search | DB-backed social + curated surfaces | Current APK rendering | IMPLEMENTED / DEVICE PENDING |
| Reels/Stories | Native Expo video, poster/retry/private playback paths | Real-device playback/TTFF | IMPLEMENTED / DEVICE PENDING |
| Create/media | private upload → processing → moderation → publication | Live R2 + device upload | IMPLEMENTED / LIVE+DEVICE PENDING |
| Video moderation | bounded 3–8 scene-aware/uniform frames; incomplete coverage → REVIEW | CI + live timing | PATCHED / VERIFY |
| Image/text safety | trained models + deterministic/PII defenses | live model preflights | IMPLEMENTED / LIVE PENDING |
| Chat/social | approved 1:1 chat + typing/polling + safety actions | two-user device run | IMPLEMENTED / DEVICE PENDING |
| Parent controls | screen time, quiet hours, category/features, review | Parent↔Child enforcement | IMPLEMENTED / DEVICE PENDING |
| Admin | moderation/audit source paths | live/device moderation fixture | IMPLEMENTED / DEVICE PENDING |
| Database | guarded retained history check + dbmate-only apply path | run on retained Neon with restore point | PATCHED / LIVE PENDING |
| R2 | private signed delivery + LittleMuse write namespace | live upload/delete | IMPLEMENTED / LIVE PENDING |
| Resend | fail-closed verified sender path | real inbox + webhook | IMPLEMENTED / LIVE PENDING |
| Modal | `littlemuse-web` / `littlemuse-ai` coherent defaults | deploy + strict preflight | PATCHED / LIVE PENDING |
| APK | verified EAS identity restored | current hardening-commit APK | BUILD PENDING |

## Locked scope

Included: Kids/Parent/Admin modes, feed/posts/reels/stories/search, one-to-one
chat, quizzes, parent controls, private media, moderation, notifications,
recommendations, Neon/PostgreSQL, Modal AI, Resend, R2 and React Native Android.

Intentionally excluded: parent/child face recognition or liveness, unrestricted
audio/voice messaging, group chat, advanced story/reel editors and standalone
child signup.

## Release gates

A release is accepted only when:

1. exact release commit passes source-audit, security, Python, package and mobile CI;
2. retained DB history is coherent and reviewed pending migrations converge to zero;
3. `littlemuse-ai` and `littlemuse-web` deploy with expected resource names;
4. strict preflight proves DB, AI/models, PII, Resend, private R2, queue and video delivery;
5. EAS produces a current-commit APK against the verified live URL;
6. one Android tester completes the physical checklist sequentially;
7. two-account proof confirms ALLOW publication plus parent-control/chat enforcement;
8. no accuracy, latency or scale claim is made without retained evidence.

## Post-merge execution order

CI → Neon restore point → controlled live deployment → strict preflight → one
current APK → one tester → fix runtime defects if any → widen tester base.
