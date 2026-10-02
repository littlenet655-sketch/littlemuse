# LittleNet dbmate migrations

LittleNet adopted **dbmate** after the original PostgreSQL schema and idempotent
`database/upgrade.sql` / `database/friendship_upgrade.sql` files were already in
use. **dbmate is the single migration owner.** To protect existing Neon
databases, deployment currently does this:

1. run `tools/init_db.py` as the legacy/idempotent bootstrap (fresh databases only);
2. run `dbmate --no-dump-schema --migrations-dir db/migrations up`;
3. create every **new** schema change as a timestamped file in this directory.

See `MODAL_DEPLOYMENT.md` (canonical deployment guide) for the exact release
sequence. Never run `dbmate up` alone on an empty database: the migrations are
deltas, not a full baseline — step 1 must come first on fresh databases.

Do not copy the historical full schema into a new migration and replay it against
an existing database. The adoption marker is intentionally a no-op boundary.

Create future migrations with:

```bash
dbmate new descriptive_change_name
```

Each migration must contain both `-- migrate:up` and `-- migrate:down`, use
PostgreSQL-safe transactional DDL where possible, and be exercised on a disposable
staging database before production.
