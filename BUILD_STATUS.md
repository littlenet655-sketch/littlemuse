# LittleNet Build Status

_Last migration preparation: 2026-09-12_

## Repository state
- Python backend retained as the working server authority.
- React Native / Expo / TypeScript is the sole mobile source in `mobile_app/`.
- Duplicate native Android scaffolding is removed from source control.
- Mobile package manifests are tracked by Git.
- CI no longer depends on the retired client toolchain.
- Direct R2 + asynchronous moderation remains the required mobile media flow.
- Scene-aware video frame selection is wired into the active visual moderation path.
- Legacy Flutter audit artifacts and Buildozer packaging configuration are removed.
- Dynamic SQL security audit permits only the existing fixed content-approval identifier whitelist; all other migrated queries are parameterized.

## Validation gates
- `python tools/audit_all.py`
- `python tools/audit_dynamic_sql.py`
- PostgreSQL-backed migration-critical tests in GitHub Actions
- `cd mobile_app && npm install && npm run typecheck && npm run export:android`

Cloud credentials and final EAS/Modal releases remain external deployment configuration, not source-code readiness blockers.

> Current release evidence (backend 898 / 2 skipped / 0 failed, mobile 283 / 0 failed,
> 43/43 migrations at executable baseline `0860174`) is recorded in
> `release_docs/FINAL_VERIFICATION_EVIDENCE.md`. The gates listed above are the
> standing source-level gates, not a dated test count.
