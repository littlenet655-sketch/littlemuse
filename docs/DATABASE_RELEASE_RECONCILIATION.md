# Retained Neon Database Release Reconciliation

Use this only for the existing data-bearing LittleNet/LittleMuse release
database. It prevents accidental legacy-bootstrap replay or dbmate history drift.

## Before mutation

1. Confirm the target DATABASE_URL belongs to the intended release database.
2. Create/verify a Neon restore point or disposable branch for rollback.
3. Use the exact release commit; do not mix migrations from another branch.
4. Never edit schema_migrations manually to make a check pass.
5. Do not run tools/init_db.py on the retained database as a migration shortcut.

## Read-only history check

```bash
modal run modal_web.py --migration-status-check
```

Require:

- `tracked: true`
- `ok: true`
- `unknown_applied: []`
- `missing_adoption_marker: false`

Review every version listed in `pending` against `db/migrations/`.

## Stop conditions

Stop the release when:

- schema_migrations is missing on a database believed to be retained;
- an applied version has no migration file in the release checkout;
- the adoption marker is missing while later versions are recorded;
- the database/branch is not the intended release target;
- pending migrations include an unreviewed destructive/data change.

## Apply reviewed deltas

```bash
modal run modal_web.py --migrate-db
modal run modal_web.py --migration-status-check
```

The second command must report zero pending versions.

## Post-migration verification

```bash
modal run modal_web.py --seed
modal run modal_web.py --preflight
```

Then require public /healthz, /readyz and /api/mobile/v1/health success.

## Rollback rule

If migration or strict preflight fails after mutation:

1. stop the release and do not distribute a new APK;
2. retain logs and the exact commit SHA;
3. restore/use the verified Neon restore point according to Neon operations;
4. reproduce and fix on a disposable clone before another production attempt.

Do not use arbitrary migrate:down execution as the primary rollback strategy for
a data-bearing production-like database.
