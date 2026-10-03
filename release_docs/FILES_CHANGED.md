# Files Changed — release line vs baseline `ac9be32`

This lists the release-line work, not every historical file in the repository.
Documentation in the final packaging pass is recorded in the docs-only commit(s)
after executable baseline `0860174`. The `f4be262` row below is **HISTORICAL — SUPERSEDED**.

## Commits (in order)

| SHA | Subject |
|---|---|
| `3c13988` | Parent Review authorization / blocked-content republish fix |
| `9afb91f` | R2 media security / delete retry bound / `R2_STORAGE_MAP` |
| `f8b40e1` | Path traversal protections / Git LFS checkpoint detection |
| `0f425af` | Curated Reel media audit / `CURATED_MEDIA_READINESS` |
| `768b5f7` | Modal resource/cost hardening / Demo Boost restore fix |
| `e55a628` | Upload security / OTP / login / health hardening |
| `715a594` | Database and Neon readiness |
| `09466c9` | API URL / profile / Stories / env / Expo config checks |
| `f4be262` | Complete final local regression and final technical fixes (HISTORICAL — SUPERSEDED by `0860174`) |
| docs commit | `docs: reconcile final LittleNet submission evidence` (docs-only; executable source unchanged) |

## Areas touched (summary)

- `auth/` — approval-token DB-clock expiry; parent OTP resend attempt model
- `mobile/api.py` — upload timezone/SQL expiry; quiz latch on playback; parent resend contract unchanged (503 residual)
- `services/media_processor.py` — retry backoff on the DB clock
- `services/media_outbox.py` — delete-retry bound
- `services/demo_boost.py` — autoscaler restore-before-OFF
- `services/object_storage.py` / R2 helpers — private media access
- `child/routes.py`, `uploadPost/routes.py`, `childMessage/routes.py` — stored-byte caps, EXIF strip
- `safety/model_files.py` — LFS pointer rejection
- `database/connection.py` — `database_aware()` timestamp helper
- `tools/set_backend_url.py` — writes `mobile_app/.env` `EXPO_PUBLIC_API_BASE_URL` only
- `mobile_app/` — 428 quiz handoff, logout/401, polling bounds, Expo SDK 57 plugins
- `requirements-core.txt` — `tzdata==2025.2`
- `tests/` and `mobile_app/tests/` — regressions for the fixes above
- Release docs listed in README (`RELEASE_IDENTITY.md`, `DATABASE_READINESS.md`, `R2_STORAGE_MAP.md`, `CURATED_MEDIA_READINESS.md`, `MODAL_COST_READINESS.md`, `release_docs/*`)
