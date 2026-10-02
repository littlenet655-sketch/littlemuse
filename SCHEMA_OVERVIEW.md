# Schema Overview — CURRENT release view

Deeper pooling/timestamp/Neon notes: `DATABASE_READINESS.md`.
Migration rules: `db/migrations/README.md`.
Retained-database procedure: `docs/DATABASE_RELEASE_RECONCILIATION.md`.

## Supported install path

A complete schema is **legacy baseline + dbmate deltas**. `database/schema.sql`
alone is not current.

```text
python tools/init_db.py
dbmate --no-dump-schema --migrations-dir db/migrations up
dbmate --no-dump-schema --migrations-dir db/migrations status
```

Never run `dbmate up` alone on an empty database.

**CURRENT FINAL RELEASE RESULT:** 43/43 migrations applied from zero on a
disposable `pgvector/pgvector:pg16` container (PostgreSQL 16.15, pgvector 0.8.7).
Latest file: `20261002120000_outbox_trigger_attempts_reset.sql`.
That container was removed after the run. Production Neon was not contacted.

## Extensions (hard requirements at schema creation)

| Extension | Why |
|---|---|
| `pgcrypto` | `gen_random_uuid()` |
| `vector` | `item_embeddings.embedding vector(384)` |
| `pg_trgm` | GIN search indexes |

## Core domains

| Domain | Principal tables |
|---|---|
| Identity | `users`, `child_profiles`, `parent_child_map`, `parent_verifications` |
| Auth / session | `mobile_token_revocations`, `login_throttle`, `parent_email_otps`, `password_reset_otps` |
| Social | `followers`, blocked/muted pairs, `notifications`, `parent_notifications` |
| Content | `posts` (processing_status: UPLOADING…ALLOWED/BLOCKED/FAILED), stories/reels as post kinds |
| Uploads | `upload_sessions`, `chat_upload_sessions` |
| Chat | `child_messages`, `chat_typing` |
| Moderation | `moderation_events`, `moderation_reviews`, `moderation_signal_cache` |
| Media lifecycle | `media_delete_outbox`, `media_assets` |
| Learning | quiz / vocabulary progress tables |
| Curated | `curated_creators`, `curated_media_assets`, `curated_music` |
| Controls | screen-time / extension-request tables |

## Timestamp rule

Legacy columns are naive `TIMESTAMP` holding **session-timezone wall-clock**
(`APP_TIMEZONE`, default `Asia/Kolkata`). Newer tables use `TIMESTAMPTZ`.
Safe writes are SQL `NOW()` or timezone-aware Python datetimes.

## Production Neon (not verified live)

Use the **direct** (non-`-pooler`) endpoint for the app and for dbmate.
Put `sslmode=require` in the secret. Do not run `tools/init_db.py` on a
retained data-bearing database as a migration shortcut.
