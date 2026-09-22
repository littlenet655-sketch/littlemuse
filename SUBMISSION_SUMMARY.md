# LittleNet — Phase II Major Project Submission Status

**Department of Computer Science & Engineering (Data Science)**  
**Adichunchanagiri Institute of Technology, Chikkamagaluru — 577102**

## Project

**LittleNet — Child Centric Social Platform with AI-based Content Filtering** (`DSPG06`)

Team: ATHMIYA D, PRAGNA G SHENOY, ROHINI L GOWDA and SANGEETHA M. Project guide: Prof. Harshitha HD.

## What is submission-ready now

- Flask/Jinja/PostgreSQL source with Kids, Parent and Admin/Moderator modes
- parent-first child account controls and verified guardian flow
- approved/two-parent-gated social graph and non-global child discovery
- fail-closed TEXT/IMAGE/VIDEO moderation
- NudeNet + Falconsai NSFW + CLIP + OpenImages-capable YOLO visual safety
- Detoxify/text safety and PII protection
- video frame sampling; video audio is stripped before persistence because active speech/audio moderation is outside the locked build
- DeepFace-backed child face identity plus Android system-authenticated Parent Mode
- compulsory age-banded quiz gate, Parent Controls, screen time and quiet hours
- private R2 media authorization and PostgreSQL audit/history
- React Native/Expo Android source and automated live-backed APK release workflow
- CI security/source gates and clean submission ZIP packaging

## Live deployment status — do not overclaim

The repository contains the automated **Deploy & Validate LittleNet Live** workflow, but the latest live run is currently blocked before deployment because GitHub Actions does not contain `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET`. Therefore the source package must not claim that the current Modal web/AI URLs or database are verified live until that workflow passes.

No admin password or other demo credential belongs in this document or in the repository. Use environment/secret-managed credentials for an actual demo.

## Android APK status

The old root `LittleNet-v1.0-submission.apk` was retired because it contained a placeholder backend target. The canonical final APK is **not stored in Git**.

After the live deployment passes, GitHub Actions generates **`LittleNet-live-verified-apk`**, injected with the exact same verified HTTPS backend URL. Download that artifact for the physical-device viva test.

## Correct viva demo order

1. Parent registration → email OTP → ACTIVE; Parent Mode then requires Android system authentication.
2. Parent creates/confirms a child and shows Parent Controls.
3. Child face enrollment/login and compulsory onboarding/scroll quiz gate.
4. Safe text/image/video post.
5. Unsafe text/adult/weapon examples showing BLOCK or Parent REVIEW.
6. Two-parent-approved friendship/discovery/chat behavior.
7. Parent dashboard alerts, screen time, quiet hours and safety review.
8. Admin moderation/audit UI using a secret-managed demo account.
9. Android app only after the `LittleNet-live-verified-apk` artifact exists and has been physically tested.

## Before final submission

Do not call the build fully live until all of these are true:

- GitHub Modal credentials configured
- Modal AI warm gate passes
- web deployment and PostgreSQL migrations pass
- quiz seeding passes
- SMTP/mail and R2 preflight pass
- public `/healthz` and `/readyz` pass
- Playwright live smoke passes
- `LittleNet-live-verified-apk` is produced
- APK is installed on a real Android device and camera/face/upload flows are tested
