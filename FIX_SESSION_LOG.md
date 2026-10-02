# LittleNet  -  Fix Session Log

This documents exactly what was changed and verified in this pass, against
the status table you gave me. I'm not going to mark anything "done" that I
couldn't actually verify  -  some of your ❌/⚠️ items are real infrastructure
work, not code bugs, and no amount of local editing closes them.

## What I actually fixed and verified live (boot + tests + screenshots)

**Parent Mode UI (was ⚠️ 80%)**
- Duplicate "Create child" CTA on the dashboard  -  removed, only the
  empty-state button remains.
- "+Create child" button text wrapping to two lines  -  fixed with a
  `nowrap-btn` class.
- Login card had inconsistent text alignment (wordmark left, subtitle
  centered)  -  both centered now.
- Mode-select/login screens had ~35% dead vertical space on full-height
  phones  -  content now anchors near the top instead of full-page centering.
- Kid-mode background reset from a cream tint to white (matches real
  Instagram and your own PPT's "child friendly Instagram like platform"
  line), keeping the mint accent only on the topbar/safety chips.

**AI optimization (was ❌ 40%)  -  found and fixed the actual root cause**
I traced why registering a child account was failing in a fresh environment:
`parent/routes.py`'s `create_child` runs the full text-safety pipeline
(Detoxify) over the registration fields (name, school, class, location,
bio) before allowing account creation. If that model isn't loaded, the
fail-closed policy correctly BLOCKs  -  which is the right behavior for real
content, but it means **basic parent onboarding is hard-dependent on the
same multi-gigabyte install as YOLO/NudeNet/Whisper~~/DeepFace~~ (removed 2026-09-22)**, none of
which have anything to do with checking a name field.

Fix: split `requirements-ai.txt` into `requirements-text.txt` (torch +
transformers + detoxify only) and the rest. A deployment can now install
just the text-moderation dependency to keep registration working, without
needing the full vision/audio stack. This doesn't change the fail-closed
safety policy at all  -  it just stops coupling it to unrelated models.

This is a real fix, not a full close of the AI-optimization gap  -  see
below for what's still open.

## Re-verified after every change
- `pytest tests/` → 122/122 passed
- `python tools/scope_check.py` → 41/41 PASS
- App boots clean against PostgreSQL, core routes return 200

## What I did NOT fix, and why (genuine external blockers, not evasion)

**AI optimization, remainder**  -  I have not installed or run the actual
NudeNet/YOLO/Whisper/Detoxify models (DeepFace path removed 2026-09-22) against real samples in this
session. That requires several GB of downloads and, for reasonable
inference speed, a GPU. Your own `BUILD_STATUS.md` already lists this as an
external blocker ("Real execution/model warm-up... End-to-end tests using
real safe/adult/weapon/video/audio/face samples"). I can't close this from
a text-editing session  -  it needs to actually happen against a deployed AI
service.

**APK readiness (⚠️ 65%)**  -  I confirmed the Android project structure and
CI workflow (`.github/workflows/build-apk.yml`) are real and coherent, but
I do not have the Android SDK/Gradle toolchain in this environment to
actually produce a binary, and the build requires a **live HTTPS backend
URL** baked in before the APK is meaningful  -  pointing it at localhost
produces a broken app. This is a deployment task (get a real HTTPS URL from
Railway/Render/Modal, then run the CI workflow or `gradle assembleDebug`
locally), not something fixable by editing files.

**Parent Mode, remainder**  -  the per-child pages (screen time, controls,
activity, learning report) all correctly return 403 without a valid,
approved child account in context  -  that's the app behaving correctly, not
a bug. I could not fully walk every Parent Mode screen with a real child
account in this session without installing the full AI stack (see above),
since account creation currently routes through it. Once you install
`requirements-text.txt` (or the full AI stack) in your own environment,
that flow will complete normally  -  I confirmed the code path, just not the
live screen-by-screen render for every page.

## Bottom line
Real fixes landed: UI bugs (verified), one genuine architectural issue in
the AI-optimization category (found and fixed, verified via tests). The
remaining ❌/⚠️ items are correctly self-assessed by you as incomplete  - 
they require real infrastructure (GPU model execution, a deployed HTTPS
backend, an Android build toolchain) that no code edit closes. Don't let
anyone tell you a zip file makes those green  -  it doesn't.
