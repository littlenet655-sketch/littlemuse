# LittleNet — Physical Device Checklist

**Status: NOT PERFORMED.** No physical device was available in this environment. Run this list on at least one Android device before any store submission or user pilot.

## Device prep

- [ ] Android device with camera; install the debug APK built from this tree (`com.littlenet.app`).
- [ ] Point the app at a staging backend (`EXPO_PUBLIC_API_BASE_URL`).
- [ ] Confirm no `RECORD_AUDIO` permission is requested (only CAMERA).

## Parent onboarding

- [ ] Parent registers → email OTP → ACTIVE (Parent Mode additionally gated by Android device auth).
- [ ] Unfinished parent login returns the resume gate (`parent_verification_required`), not access.
- [ ] Parent creates a child; child appears in Parent Mode dashboard.

## Child onboarding

- [ ] Child logs in with their password.
- [ ] Wrong credentials show one generic, non-enumerating failure message.
- [ ] Compulsory age quiz gates Kids Mode entry.

## Posting pipeline (v2)

- [ ] Create post/reel/story: upload session → R2 PUT → complete → processing screen → published after moderation.
- [ ] Story with music: track attaches and plays on the story.
- [ ] Reels playback: signed URL plays, refreshes before expiry, manual retry on failure.

## Social & safety

- [ ] Feed, like, comment (rude comment held for review), follow, block, mute, report.
- [ ] Messaging: PII (phone number) blocked; flagged message shows as pending to sender, never to receiver.
- [ ] Parent safety review queue: approve/block a flagged item; child notified appropriately.
- [ ] Screen-time limit set/reset/extend; quiet hours respected.

## Admin

- [ ] Admin review queue approve/block/escalate; audit log records each action.
- [ ] Attempt to activate an unverified parent → blocked with clear error (web + mobile admin).

## Media edge cases

- [ ] Airplane mode during upload → clear error, redrive works.
- [ ] Expired signed playback URL → player refreshes without losing position.
- [ ] Missing/broken media → placeholder UI, no crash.

## Sign-off

- Tester name / device model / OS version / date:
- Issues found (link to tracker):
