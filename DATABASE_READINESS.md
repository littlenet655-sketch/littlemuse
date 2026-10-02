# LittleNet Database / Neon Readiness

## CURRENT FINAL RELEASE RESULT (2026-10-02, freeze after `826e633`)

A disposable Docker `pgvector/pgvector:pg16` database was brought up, migrated
from zero, used for the final local regression, and torn down.

| Item | Result |
|---|---|
| Docker | 29.7.2 |
| Image | `pgvector/pgvector:pg16` |
| PostgreSQL | **16.15** |
| pgvector | **0.8.7** |
| Port | `127.0.0.1:55432` (disposable; container removed afterward) |
| Bootstrap | `python tools/init_db.py` then `dbmate --no-dump-schema --migrations-dir db/migrations up` |
| Migrations | **43 applied / 0 pending** |
| Latest migration | `20261002120000_outbox_trigger_attempts_reset.sql` |
| Full backend | **898 passed / 2 skipped / 0 failed** |
| Live Neon | **NOT CONTACTED** — EXTERNAL REQUIREMENT |

The sections below retain the earlier source analysis (commit that introduced
this file, parent `e55a628`). Tags such as **NOT EXECUTED** in those sections
are **HISTORICAL RESULT** for that writing session. They are superseded by the
disposable-PG run above wherever they conflict.

---

Authoritative source analysis (historical session). Each historical statement
is tagged **EXECUTED** (run in that session), **SOURCE** (read from code, not
run) or **NOT EXECUTED** (needed an environment that did not exist in that
session). No production Neon, R2 or Modal contact was made in either session.

## 1. Architecture

| Item | Finding | Where |
|---|---|---|
| Engine | PostgreSQL via `psycopg2`, `RealDictCursor` | `database/connection.py` |
| Pool | `ThreadedConnectionPool` min `DB_POOL_MIN_CONNECTIONS` (default 2), max `DB_POOL_MAX_CONNECTIONS` (default 20), lazy, one per process | `_get_pool` |
| Checkout | idle-validation (`SELECT 1`) only if last validation > `DB_POOL_VALIDATION_INTERVAL_SECONDS` (30 s); dead connections are discarded and retried once | `get_db_connection`, `_connection_is_usable`, `_discard_connection` |
| Fallback | any pool error (incl. exhaustion or failed validation) opens one **unpooled** `psycopg2.connect`, closed by the caller | `get_db_connection` |
| Transactions | `execute`/`execute_count` commit once, roll back and re-raise on error; `fetch_*` never commit; returning a pooled connection always rolls back first | `execute`, `PooledConnectionWrapper.close` |
| Failure behaviour | DB unreachable -> `psycopg2.OperationalError` propagates; mobile token-revocation lookup fails closed (401) | `connection.py`, `mobile.api._mobile_token_revoked` |
| Session timezone | every connection starts with `-c timezone=<APP_TIMEZONE>` (default `Asia/Kolkata`; invalid value -> `UTC`) | `_database_timezone` |
| Credentials in logs | pool metrics expose counters only (`pool_metrics_snapshot`); `config.py`/`connection.py` never log the URL. Not re-scanned repo-wide in this task | SOURCE |
| Migration owner | **dbmate** (v2.34.1, sha256-pinned in `Dockerfile`, `Dockerfile.web`, `modal_web.py`) | `db/migrations/README.md` |

### DATABASE_URL handling
`config.py`: in production (HTTPS/`_PRODUCTION`) an empty `DATABASE_URL` raises
`RuntimeError("Production DATABASE_URL must be explicitly configured")`. Outside
production the fallback is `postgresql://postgres:littlenet@localhost:5432/safeconnect_db`
(development fallback only; production must set `DATABASE_URL`). `.env.example` ships
`...?sslmode=require`. CI uses `sslmode=disable` against a local service container.
No code-level `sslmode`/`connect_timeout`/`statement_timeout` default exists; they
must come from the URL (see section 7).

## 2. PostgreSQL / extensions

* Tested-image assumption: `pgvector/pgvector:pg16` in `.github/workflows/ci.yml` and `role-e2e.yml` -> **PostgreSQL 16**. No code uses a PG17-only feature (SOURCE; not exhaustively verified).
* `CREATE EXTENSION IF NOT EXISTS pgcrypto` (`database/schema.sql:11`; `gen_random_uuid()` is used by later migrations).
* `CREATE EXTENSION IF NOT EXISTS vector` (`database/schema.sql:519`, `database/upgrade.sql:343`). **pgvector is a hard requirement at schema-creation time** because `item_embeddings.embedding` is `vector(384)`. At runtime the only `<=>` query in the repo is `benchmarks/pipeline_profiler.py`; production request paths do not query it.
* `CREATE EXTENSION IF NOT EXISTS pg_trgm` (migration `20260907001500_content_search_indexes.sql`) for GIN search indexes on posts/comments/users.
* Role used for migrations must be allowed to create these three extensions. **EXTERNAL VERIFICATION REQUIRED** on Neon.

## 3. Migrations

Counted by a throwaway script (not committed) over `db/migrations/*.sql` - **EXECUTED**:

* **43** `.sql` files (+ `README.md`); first `20260906180000_adopt_dbmate`, last `20261002120000_outbox_trigger_attempts_reset`.
* Names all match `^\d{14}_[a-z0-9_]+\.sql$`; versions strictly ascending; **0 duplicate versions**.
* All 43 contain both `-- migrate:up` and `-- migrate:down`.
* `20260906180000_adopt_dbmate.sql` is an intentional no-op boundary (`SELECT 1`).
* `20261002120000_outbox_trigger_attempts_reset.sql` replaces the live post/message delete-outbox functions so an exhausted (`attempts >= 8`) or completed row starts a new bounded cycle. Historical `20260907150000_final_runtime_invariants.sql` is unchanged.
* Data/structure-removing statements in **up** sections (all intentional, applied once per database, not re-run): `DROP TRIGGER`/`DROP CONSTRAINT` (re-create patterns in `20260907142000`, `20260907150000`, `20260908093000`, `20260912235000`, `20260913000000`, `20260922000002`, `20260924000001`, `20260924000003`, `20260928000001`); `DELETE FROM` in `20260913000000` (invalid face_profiles), `20260921000100` (music dedup), `20260922000002` (push-token owner dedup), `20260923000000` (quiz bank simplification); `DROP TABLE`/`DROP COLUMN` in `20260922000001_drop_face_artifacts` and `DROP COLUMN` in `20260924000003`. No `TRUNCATE`. Whether the **down** sections restore deleted data was not evaluated.
* One `CREATE INDEX` without `IF NOT EXISTS`: `20260908195500_curated_dataset_foundation.sql` (executes once under dbmate tracking; not a defect, noted for idempotency).
* Migration-created tables absent from `database/schema.sql`: `chat_typing`, `content_reactions`, `content_saves`, `content_shares`, `curated_creators`, `login_throttle`, `media_delete_outbox`, `moderation_signal_cache`, `password_reset_otps`, `screen_time_extension_requests` (+ `face_auth_challenges`, later dropped). `child_xp`, `curated_music`, `parent_verifications` live in `upgrade.sql`/`friendship_upgrade.sql`, not `schema.sql`. Consequence: **`schema.sql` alone is not a complete schema; baseline + migrations is the only supported path.**

### Exact commands
Fresh database (baseline first, then deltas; never `dbmate up` alone on an empty DB):

```
python tools/init_db.py
dbmate --no-dump-schema --migrations-dir db/migrations up
dbmate --no-dump-schema --migrations-dir db/migrations status
```

Retained (Neon) database via Modal (`modal_web.py`, `.github/workflows/deploy-modal.yml`):
`database_migration_status` (read-only; requires `schema_migrations`, baseline tables, adoption marker `20260906180000`, no unknown applied versions) -> optional `migrate_retained_database` (refuses unless the status check is OK, runs `dbmate up`, re-checks `pending == []`) -> `--require-db-current` -> `modal deploy`.

Docker (`docker-entrypoint.sh`): `python tools/init_db.py` (idempotent) -> hard-fail if `dbmate` missing -> `dbmate up` -> `tools/seed_quizzes.py` -> gunicorn (1 worker, 4 threads). The Modal web function does **not** migrate at container start; migration is a separate pre-deploy step.

Execution status for the **historical** writing of this section: **NOT EXECUTED**
in that session. **CURRENT FINAL RELEASE RESULT**: disposable
PostgreSQL 16.15 + pgvector 0.8.7, **43/43** migrations from zero, backend
**898 passed / 2 skipped / 0 failed**. Live Neon remains **NOT CONTACTED**.
Historical Claude-session counts such as 783 passed / 2 skipped, and the
earlier local 42/42 run on `f4be262`, are **HISTORICAL RESULT** only.

## 4. Schema / index review (SOURCE)

| Area | Constraint / index | Verdict |
|---|---|---|
| users | role / account_status CHECKs; `idx_users_lower_email`, `idx_users_lower_username` (login `LOWER()` lookups) | OK |
| parent_child_map | `UNIQUE(child_id,parent_email)`, unique `approval_token`; role-validation + approval-guard triggers. **No index on `parent_id` / `verified_parent_id`** | Documented gap; table is one row per child-parent link, so scans stay small. Not added (no query shown to need it) |
| mobile_token_revocations | PK `token_hash`, `idx_revoked_tokens_user`; TIMESTAMPTZ | OK |
| login_throttle | PK `user_id`, `failed_attempts >= 0` CHECK; TIMESTAMPTZ | OK |
| parent_email_otps / password_reset_otps | PK `user_id`; `attempts >= 0` (password_reset); TIMESTAMP (naive) - see section 5 | OK |
| posts | status CHECKs; `idx_posts_feed*`, `idx_posts_child`, `idx_posts_processing`, partial `idx_posts_lease_expiry`, unique partial `source_media_path`, unique partial `upload_id` | OK |
| upload_sessions | status CHECK `PENDING/UPLOADED/CONSUMED/EXPIRED/CANCELLED`; `idx_upload_sessions_child(child_id,status,created_at)`. Reaper `reconcile_abandoned_upload_sessions` filters `status IN (...) AND expires_at < x ORDER BY expires_at LIMIT 50` with no `expires_at`-leading index | Table is TTL-bounded; documented, no index added |
| chat_upload_sessions | status CHECK `PENDING/REVIEW/CONSUMED/BLOCKED/EXPIRED/CANCELLED`; `(child_id,status,expires_at)`; `object_key UNIQUE` | OK |
| moderation_events | `idx_moderation_review(decision,status,created_at DESC)` | OK |
| followers / blocked / muted | unique pair + partial indexes (`approved=TRUE`) | OK |
| notifications / parent_notifications | `(user_id,is_read,created_at DESC)`, `(parent_id,is_read,created_at DESC)` | OK |
| child_messages | `(conversation_id,sent_at DESC) WHERE is_deleted=FALSE`, reply-to partial | OK |
| quiz state | `UNIQUE(child_id,quiz_id)`, `UNIQUE(child_id,word,language)`, `idx_child_pool_unserved` partial | OK |
| media_delete_outbox / R2 references | partial `idx_media_delete_outbox_pending(created_at) WHERE completed_at IS NULL`; posts/messages triggers enqueue deletes | OK |

**No new migration or index was added.**

## 5. Timestamp semantics

Column typing (from `schema.sql` + migrations, EXECUTED by script): legacy tables use naive `TIMESTAMP` (users, parent_child_map, posts.created_at/last_attempt_at, upload_sessions, child_messages, notifications, parent_email_otps, password_reset_otps, child_vocabulary_progress, ...). Newer tables use `TIMESTAMPTZ` (posts.processing_lease_expires_at, chat_upload_sessions, login_throttle, mobile_token_revocations, media_assets, user_device_tokens, demo_boost_state, email_delivery_events, item_embeddings, recommendation_signals, story/message reactions).

Rule: naive columns hold **session-timezone wall-clock** (`APP_TIMEZONE`). Safe writes are SQL `NOW()`/`CURRENT_TIMESTAMP` or an **aware** Python datetime (psycopg2 sends `timestamptz`, which PG converts in the session zone). Naive reads from psycopg2 must be re-labelled with the session zone, not UTC.

| Site | Status |
|---|---|
| `upload_sessions.expires_at` (`mobile/api.py` ~2771), token expiry (`mobile/api.py` ~1907) | aware UTC - previously fixed, tests in `tests/test_upload_session_timezone.py` (DB-backed) |
| Media retry backoff (`claim_media_job_lease`) | age computed by Postgres - previously fixed |
| `reap_stale_media_jobs`, `reconcile_abandoned_upload_sessions` thresholds | aware UTC parameter compared with naive column -> PG casts correctly |
| OTP expiry (`auth/parent_email_otp.py` ~255, `auth/password_reset.py` ~267) | compares against DB `NOW()` and re-labels naive with `now.tzinfo` - correct |
| `quiz/learning_service.record_vocabulary_attempt` | **defect fixed here**: `datetime.now()` (container-local = UTC on Modal) was stored into naive `next_review_due` and compared with `NOW()` in `Asia/Kolkata`, delaying reviews by 5h30m. Now `datetime.now(timezone.utc)` |
| `childMessage/routes.py` conversation `time_ago`, `child/routes.py` notification grouping | **defect fixed here**: naive `sent_at`/`created_at` were subtracted from `utcnow()`, so items under 5h30m old showed "just now"/"today". Now `database_aware()` |
| `services/recommendation._recency_score` (old KNOWN_LIMITATIONS item) | **defect fixed here**: naive created_at was treated as UTC. Now `database_aware()` (ranking effect <= ~2% of the recency bonus, but now correct) |
| `quiz.learning_service.calculate_next_srs_review` | still `datetime.utcnow()`; pure helper used only by tests/`tools/run_comprehensive_audit.py`, not by a persisting path. Left unchanged |
| `services/controls.py` ~147 | uses `ZoneInfo(APP_TIMEZONE)` explicitly - correct |
| `tools/seed_demo_conversations.py` | demo seeding script, naive `datetime.now()`; not a runtime path |
| `date.today()` in `services/usage.py`, `quiz/service.py`, `curated_feed.py`, `social.py` | process-local date vs DB `CURRENT_DATE` in the APP_TIMEZONE session: equal only if the process TZ matches. No `TZ` is set in `modal_web.py` or the Dockerfiles, so the process zone is the container default (UTC on standard Linux images), and `services/usage.py` bonus-date comparison (`lim.get('bonus_date')==date.today()`) can disagree with SQL `CURRENT_DATE` for 5h30m/day under Kolkata. **Not changed** (no live evidence of user impact; documented residual) |

Added: `database.connection.database_aware()` and `tests/test_database_timestamp_semantics.py` (7 mock-only tests).

## 6. Processing / upload lifecycle (SOURCE + existing tests)

`posts.processing_status` CHECK: `UPLOADING, UPLOADED, PROCESSING, REVIEW, ALLOWED, BLOCKED, FAILED`.

* Claim (`claim_media_job_lease`): single `UPDATE ... WHERE processing_status NOT IN ('ALLOWED','BLOCKED','FAILED') AND (attempts < max OR force) AND (no lease OR lease expired OR force)` with lease 300 s and `processing_attempts+1`. Terminal states cannot be re-claimed; concurrent claimers get zero rows.
* Bound: `max_processing_attempts` (default 3) -> `FAILED` with `max_attempts_exceeded`. Backoff `min(300, 2^(attempts-1)*5)` s, measured on the DB clock.
* Every terminal write (`ALLOWED`/`BLOCKED`/`REVIEW`/`FAILED`) is guarded by `processing_lease_token=%s`; a lost lease raises `processing_lease_lost`. Transient errors (R2 unavailable, quarantine object missing) return the row to `UPLOADED` and clear the lease.
* Reaper (`reap_stale_media_jobs`): `UPLOADED/PROCESSING` with no lease or expired lease and older than the stale threshold -> redrive or `FAILED` when attempts exhausted. Backed by `idx_posts_lease_expiry`.
* Upload sessions: `PENDING -> UPLOADED -> CONSUMED`, with `EXPIRED`/`CANCELLED` terminals. Complete is idempotent per `posts.upload_id` (unique partial index); expired sessions are rejected; abandoned sessions are swept after TTL (`reconcile_abandoned_upload_sessions`, LIMIT 50, R2 delete failure queued in `media_delete_outbox`). Chat sessions: complete on a closed session returns 409 `upload_session_closed`.
* No impossible transition found. Clock-interpretation stalls were the historical defect class and are covered in section 5.

Existing tests (cited, **NOT EXECUTED** here because most need Postgres): `tests/test_agent_a_disposable_postgres.py::test_bounded_redrive_terminates_at_max_attempts`, `::test_reap_stale_jobs_marks_exceeded_attempts_as_failed`, `::test_concurrency_simultaneous_reaper_and_redrive_creates_one_logical_attempt`, `::test_dispatch_failure_and_idempotent_retry`; `tests/test_upload_session_timezone.py`; `tests/test_phase25_production_hardening.py::test_complete_rejects_expired_session`, `::test_complete_idempotency`; `tests/test_upload_security_hardening.py::test_v2_complete_replay_is_idempotent_and_does_not_spawn`, `::test_v2_complete_expired_session_is_rejected`; `tests/test_media_orphan_cleanup.py` (reaper, abandoned sessions, R2 outbox). The seven `tests/test_upload_session_timezone.py` failures seen earlier come from the deliberately invalid DB address `127.0.0.1:1` that `tests/conftest.py` installs when no `DISPOSABLE_DATABASE_URL`/`.env.disposable` is set - an environment condition, not a proven code defect.

## 7. Neon readiness (SOURCE only - no live connection)

* URL format: `postgresql://USER:PASS@ep-xxxx.<region>.aws.neon.tech/DB?sslmode=require` (append `&connect_timeout=10`; libpq has no default connect timeout). `sslmode` is not defaulted in code; Neon rejects non-TLS server-side, but `require` should be explicit in the secret.
* **Pooled vs direct endpoint.** `connection.py` always passes the startup parameter `options=-c timezone=...`. Neon's PgBouncer (`-pooler` host) historically rejects `options`. Use the **direct** (non-`-pooler`) host for the app's `DATABASE_URL` and for dbmate, unless a pooled-endpoint connection with `options` is verified. The app already pools in-process, so PgBouncer adds little. No code change made (no evidence of a defect here). **EXTERNAL VERIFICATION REQUIRED.**
* **Migrations use the DIRECT endpoint** (dbmate uses session state/advisory locks and DDL transactions).
* **Cold start**: Neon scale-to-zero can make the first connect slow; with no `connect_timeout` a stalled connect blocks the request. The pool's `SELECT 1` validation recycles connections dropped during suspend.
* **Pool sizing**: nominal ceiling `MODAL_WEB_MAX_CONTAINERS` (3) x `DB_POOL_MAX_CONNECTIONS` (20) = 60, plus up to four single-container Modal functions (`max_containers=1`, each with its own pool, nominal 20) = 140. `modal_web.py` has no `@modal.concurrent`, so one request per container keeps real usage far below the ceiling (about `min=2` per live container), but the unpooled fallback in `get_db_connection` is uncapped. Check the Neon plan's connection limit; lowering `DB_POOL_MAX_CONNECTIONS` (e.g. 5) via the Modal secret is a config-only mitigation.
* **Deploy order**: `database_migration_status` -> (reviewed) `migrate_retained_database` -> `--require-db-current` -> `modal deploy`. Migrate before deploying web; the new code assumes the new schema.
* **Rollback**: dbmate `down` exists per file, but several migrations delete or drop data (section 3); prefer a Neon branch/snapshot before `up` on a retained database and restore from it rather than running `down`.
* Live connectivity, extension privileges (`vector`, `pg_trgm`, `pgcrypto`), and the pooled-endpoint behaviour: **EXTERNAL VERIFICATION REQUIRED**.

## 8. Local DB test environment

**CURRENT FINAL RELEASE RESULT:** disposable `pgvector/pgvector:pg16` on
`127.0.0.1:55432` was used for the 31 focused DB tests and the full 885-test
backend suite, then removed. Historical probe text below is from the earlier
session that lacked Docker.

Historical probe (EXECUTED in that session only): no `psql`, `pg_isready`,
`dbmate`, PostgreSQL service/port, or running Docker daemon; no `.env.disposable`.
That session's DB-backed tests were **NOT EXECUTED**.

Commands for the final regression phase (disposable DB only, never a remote host):

```
docker run -d --name littlenet-pg -e POSTGRES_PASSWORD=littlenet -e POSTGRES_DB=littlenet_test -p 5433:5432 pgvector/pgvector:pg16
$env:DATABASE_URL = "postgresql://postgres:littlenet@127.0.0.1:5433/littlenet_test?sslmode=disable"
python tools/init_db.py
dbmate --no-dump-schema --migrations-dir db/migrations up
psql $env:DATABASE_URL -c "SELECT extname FROM pg_extension"     # expect vector, pgcrypto, pg_trgm
$env:DISPOSABLE_DATABASE_URL = $env:DATABASE_URL                  # process env only; do not commit
python -m pytest tests/test_upload_session_timezone.py tests/test_agent_a_disposable_postgres.py tests/test_phase25_production_hardening.py tests/test_video_recommendation_scale.py -q
docker rm -f littlenet-pg
```

(`dbmate` must be installed; Windows build from the dbmate v2.34.1 release.)

## 9. What was executed in this task

* Throwaway migration-parser script (naming/order/duplicates/markers/destructive/extension scan) and baseline-vs-migration table diff - EXECUTED, not committed.
* `python -m py_compile` on `database/connection.py`, `quiz/learning_service.py`, `childMessage/routes.py`, `child/routes.py`, `services/recommendation.py` - passed.
* `tests/test_database_timestamp_semantics.py` (7) + `tests/test_k2_ai_safety.py` - 33 passed.
* `tests/test_submission_publication_recommendations.py`, `test_video_recommendation_scale.py`, `test_curated_feed.py`, `test_message_review_visibility.py`, `test_chat_realtime.py` - 46 passed, 2 skipped, 3 failed. The 3 failures (`test_video_recommendation_scale.py::test_batch_impressions_contract`, `::test_reels_page_defers_social_playback_credentials`, `::test_curated_reel_playback_is_authorized_just_in_time`) are `psycopg2.OperationalError` against `127.0.0.1:1` - they require a database (NOT EXECUTED against Postgres).
* Not run: full pytest suite, any Postgres-backed test, dbmate, live Neon.
