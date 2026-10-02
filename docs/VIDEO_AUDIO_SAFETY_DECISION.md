# Video Audio Safety Decision (LittleNet)

**Decision: Option A — strip audio from user videos before publication.**
Status: implemented and enforced. Date: 2026-09-21.

## What happens to audio

1. **User-uploaded videos are published silent.** Every video publish path
   removes all audio streams before the bytes become visible:
   - `services/media_processor.py::_make_video_derivatives` calls
     `services.media_sanitizer.strip_video_audio_in_place`, and raises
     (`video_sanitization_failed`) if stripping fails for any reason. Both
     video publish paths go through it: `_process_media_job_impl` (posts /
     reels / stories pipeline) and `sanitize_and_promote_media` (quarantine
     promotion).
   - `services/object_storage.py::upload_file` strips audio from any
     `video/*` upload before R2 upload, and raises on failure. This covers
     every `persist_before_db` caller (`mobile/api.py` post creation,
     `uploadPost/routes.py`, `childMessage/routes.py` chat media).
   - The non-R2 local publish branch of `sanitize_and_promote_media` copies
     the already-stripped `final_media_local`, never the raw upload.
2. **Video moderation is frames-only.** `safety/visual_service.py::check_video`
   and `safety/video_service.py::check_video` sample frames and run image
   moderation on each frame. Audio tracks are never transcribed or moderated —
   they do not need to be, because they never reach publication.
3. **Standalone audio is disabled.** `safety/moderation_service.py::evaluate`
   hard-BLOCKs `AUDIO`/`VOICE` content types; upload routes reject
   `audio/*` files and story-music uploads with 400. `safety/audio_service.py`
   is a retired compatibility shim (hard-BLOCK) kept only for legacy
   imports/tests.

Note: stories may reference platform-curated music from the `curated_music`
catalog (operator-owned audio URLs played alongside the silent video file).
That catalog is not user-uploaded content and is outside the upload
moderation path; the published video bytes themselves remain audio-free.

## Why Option A

- There is **no tested transcription + moderation pipeline** in the codebase
  for video audio. Building a half-working one (e.g. best-effort Whisper with
  partial language coverage) would create a false sense of coverage while
  unmoderated or mis-transcribed speech — grooming, contact sharing, abuse —
  could reach children.
- Stripping is deterministic, cheap (ffmpeg `-an`, no re-encode), and
  fail-closed: any uncertainty raises instead of publishing.
- Audio adds no product value that outweighs the risk for a child-safety
  platform; reels/stories work fine silent (the product already ships them
  that way).

## What Option B would require (future)

If product ever wants audio in videos, ALL of the following must land first —
no partial rollout:

1. A tested speech-to-text pipeline (e.g. Whisper) with measured accuracy on
   children's speech, background noise, and the languages LittleNet serves.
2. Transcripts routed through the **same** `check_text` + PII policy as typed
   text, with deterministic hard-block categories honored.
3. Bounded processing (max audio seconds, timeout) and a defined failure
   posture: transcription failure must fail closed (BLOCK/REVIEW), never
   publish unmoderated audio.
4. Regression tests proving no code path can publish the original audio
   track, and an update to this document.

## Verification

- `tests/test_video_audio_stripping.py` asserts the sanitizer contract and
  that all video publish paths route through audio stripping.
- `tests/test_audio_retirement_runtime.py` covers the retired-audio behavior.
