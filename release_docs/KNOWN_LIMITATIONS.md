# Known Limitations (genuine, current)

1. **Trained model weights are Git LFS pointers (133–134 bytes).** `littlenet_core_safety_v2.pth`,
   `littlenet_weapons_violence_v3.pth`, `littlenet_text_safety/model.safetensors` are NOT trained models in this ZIP.
   Run `git lfs pull` on the real repository before deploying AI inference. (yolov8n*.pt are real files.)
2. **Audit incomplete.** Not examined: R2 storage map, Reel codecs (ffprobe), moderation pipeline doc, profile/follow queries,
   Story hook, Modal cost config, health endpoint, full security review, README refresh, DATABASE_READINESS, SCHEMA_OVERVIEW.
3. **`/api/mobile/v1/media?ref=` is not covered by the quiz latch.** It serves by opaque object key (parental `reels`
   permission is enforced). Latching it would blank Reel thumbnails; revisit if stricter enforcement is required.
4. **Remaining naive-timestamp sites** (e.g. services/recommendation.py ~line 203; other tables) were not swept. Impact there is small.
5. **No live verification:** Neon, R2, Resend, Modal, EAS build, real-device playback, and live Parent Review E2E
   (needs a legitimate REVIEW event) were not run.
6. **Parent Review**: no direct test for a CHILD token calling the parent route, an invalid action, or a duplicate decision
   (code paths exist and are covered indirectly).
7. **Expo Doctor** config-schema and React Native Directory checks could not run (sandbox network).
8. **config.py** keeps a localhost development fallback for DATABASE_URL; production must set DATABASE_URL.
