# Final Fix Report — release-candidate (CURRENT)

Significant fixes on `release-candidate` through the outbox-trigger freeze
(parent `826e633`). Older root `FINAL_FIX_REPORT.md` (2026-09-21) is a
**HISTORICAL RESULT**.

| Area | What changed |
|---|---|
| HTTP 428 generic retry | QueryClient uses `shouldRetryQuery`; 428 / `quiz_required` never retries |
| dbmate CI checksum | `ci.yml` and `role-e2e.yml` verify pinned v2.34.1 SHA-256 before exec |
| Python outbox re-enqueue | `ENQUEUE_DELETE_SQL` resets `attempts` only when exhausted or completed |
| DB trigger outbox re-enqueue | `20261002120000_outbox_trigger_attempts_reset.sql` updates live post and message delete triggers the same way |
| Silent video metadata | Remux always; `-map_metadata -1` and `-map_chapters -1` on sanitizer and derivatives |
| Demo Boost restore | Restores configured `MODAL_AI_*_SCALEDOWN_WINDOW`, not hardcoded 30s |
| Portable ZIP | `LittleNet/` root, forward-slash entries, extra key-material suffix excludes |
| transformers residual | Keep `transformers==5.10.0` (yanked PyPI, proven with trained text model) |

## Verification used

Authoritative local regression on this freeze: backend 898/2 skipped/0 failed;
mobile 283/0; TypeScript passed; Expo Doctor 21/21; Android export passed;
**43/43** migrations on disposable PostgreSQL 16.15 + pgvector 0.8.7.
Rollback and re-apply of migration 43 succeeded.

Live Neon / R2 / Resend / Modal / EAS / device were **not** executed.
