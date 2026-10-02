# Test Results (real runs in the sandbox)

Environment: PostgreSQL 16 + pgvector (local), all 42 dbmate migrations applied cleanly,
`APP_TIMEZONE=Asia/Kolkata`, Python venv from requirements-core.txt (+ pydantic>=2,<3 as CI does), Node via `npm ci`.

| Check | Command | Result |
|---|---|---|
| Backend baseline (before any change) | `pytest tests/ -q` | 770 passed, 2 skipped, 0 failed |
| Backend final | `pytest tests/ -q` | **783 passed, 2 skipped, 0 failed** (exit 0) |
| Mobile baseline | `npm test` | 267 passed, 0 failed, 0 skipped |
| Mobile final | `npm test` | **281 passed, 0 failed, 0 skipped** (exit 0) |
| TypeScript | `npm run typecheck` (tsc --noEmit) | exit 0 |
| Expo export | `expo export --platform android` (EXPO_PUBLIC_API_BASE_URL placeholder) | exit 0; Hermes bundle ~3.7 MB |
| Expo Doctor | `npx expo-doctor` | 19/21 passed. Duplicate `expo-constants` finding FIXED. 2 failures are network-only: config-schema validation and React Native Directory check — **NOT EXECUTED (sandbox network)** |
| Lockfile consistency | `npm ci --dry-run` | exit 0 |
| Lint | — | not configured in package.json (no lint script) |

Regression tests added and proven to fail on the pre-fix code: upload_sessions expiry clock, media retry backoff,
approval-token expiry, quiz-latch bypass on the generic playback routes (mutation check done).

NOT EXECUTED: any live Neon / Cloudflare R2 / Resend / Modal / EAS call; real-device playback; Android build;
ffprobe of curated Reel assets; live Parent Review end-to-end (needs a legitimate REVIEW event).
The 2 skipped backend tests were skipped by the repository itself; their reasons were not investigated here.
