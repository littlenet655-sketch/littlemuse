# LittleNet — Known Limitations

Things this tree does **not** do, classified from the contract audit (2026-09-21). None of them is a release blocker under the project's rule (no visible mobile feature calls a missing or broken contract), but each is real work for a later milestone.

## Functional gaps (backend work needed)

1. **Kids messages lack pagination** — `GET /api/mobile/v1/kids/messages` returns all conversations; per-chat reads already paginate. Fine at small scale; add `limit`/`before_id` before large pilots.
2. **No LIKE/COMMENT/FOLLOW notifications** — the actions work, but the content owner is never notified. `NotificationsScreen` shows MESSAGE/PARENT_CONTROLS/SCREEN_TIME types only.
3. **No bearer-native post/story deletion** — deletion exists only as session-cookie web routes. The native app has no delete affordance at all (by design for now); adding one requires `DELETE /api/mobile/v1/kids/posts/<id>` plus R2 cleanup wiring.
4. **No bearer parent learning-report endpoint** — the report is web-HTML only (`quiz/routes.py`); no mobile call site exists.
5. **Push delivery still needs Firebase/APNs credentials** — push device registration is wired end-to-end (the app requests permission, takes the Expo push token via the EAS projectId, and registers it with `POST /api/mobile/v2/device/register` on sign-in / `POST /api/mobile/v2/device/unregister` on sign-out; `mobile_app/src/push/notifications.ts`, `mobile_app/src/auth/AuthProvider.tsx`). Actual token delivery to a physical device remains unverified until Firebase/APNs credentials exist.

## Quality / performance improvements

6. **Story viewer payload uses raw `profile_picture`** — renders defensively on the client; should resolve to `avatar_url` server-side.
7. **Feed/home posts omit media width/height/aspect-ratio** — client falls back to local measurement; server should persist dimensions at processing time.
8. **Kids home is v1-only** — works; a v2 home route would be a consistency improvement.
9. **`update_time_limit` staleness** — could not reproduce server-side (read-after-write, no cache); if observed, it is likely the client's dashboard-invalidation race.

## Test-environment limitations

10. `tests/test_message_review_visibility.py` E2E pair errors in sandboxes where the disposable DB is only reachable via localhost (the file's own anti-footgun guard). The DB-free contract half passes.
11. Gradle `assembleDebug` could not run in this sandbox (blocked localhost TCP for the Gradle daemon) — see FINAL_TEST_RESULTS.md.
12. Physical-device and live-production verification were not performed (no device, no prod credentials) — see PHYSICAL_DEVICE_CHECKLIST.md.

## Deliberately retained (not limitations)

- Compatibility fallbacks, private-R2 fallback for Stream, migration history, safety checks, and physical-device docs were kept on purpose.
- `POST /api/mobile/v1/kids/posts` returns **410** (not removed) so old clients get a directed error instead of a silent 404.
