# 05 — PostgreSQL & Neon Database Audit Report

**Audited Date:** 2026-09-08  
**Audit Scope:** Schema integrity, migration sequence, foreign keys, check constraints, transaction boundaries, indexing, SQL injection prevention, and database-level publication triggers.  

---

## 1. Schema & Migration Architecture

The LittleNet persistence layer utilizes PostgreSQL (hosted on Neon Serverless) managed via `dbmate` migration scripts located in [`db/migrations/`](file:///d:/aitprojects/LittleNet-1/db/migrations/):

1. `20260906180000_adopt_dbmate.sql`: Adopts baseline schema management into dbmate.
2. `20260907001500_content_search_indexes.sql`: Full-text search gin indexes over captions, hashtags, and titles.
3. `20260907142000_audit_p0_p1_hardening.sql`: Hardens foreign keys, cascade deletes, and check constraints.
4. `20260907150000_final_runtime_invariants.sql`: Enforces child-safety constraints (`is_safe=FALSE` when `moderation_status='BLOCKED'`).
5. `20260908093000_native_admin_escalation.sql`: Admin and moderator role hierarchies.
6. `20260908195500_curated_dataset_foundation.sql`: Introduces curated dataset tables, impressions, and feed session caching.

---

## 2. Curated Content Tables & Database-Level Invariants

Migration `20260908195500_curated_dataset_foundation.sql` creates dedicated tables separating system/curated content from child-generated posts:

```sql
CREATE TABLE curated_media_assets (
  asset_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  dataset_version TEXT NOT NULL,
  source_row_id TEXT NOT NULL,
  archive_file TEXT NOT NULL,
  original_filename TEXT NOT NULL,
  sha256 CHAR(64) NOT NULL UNIQUE,
  media_type TEXT NOT NULL CHECK(media_type IN ('IMAGE','VIDEO')),
  original_object_key TEXT NOT NULL UNIQUE,
  delivery_object_key TEXT NOT NULL UNIQUE,
  moderation_status TEXT NOT NULL CHECK(moderation_status IN ('PENDING','ALLOWED','REVIEW','BLOCKED')),
  is_safe BOOLEAN NOT NULL DEFAULT FALSE,
  ...
  CHECK(moderation_status <> 'ALLOWED' OR is_safe=TRUE),
  CHECK(moderation_status <> 'BLOCKED' OR is_safe=FALSE)
);

CREATE TABLE curated_content (
  content_id BIGSERIAL PRIMARY KEY,
  asset_id UUID NOT NULL UNIQUE REFERENCES curated_media_assets(asset_id) ON DELETE RESTRICT,
  category_id SMALLINT NOT NULL REFERENCES content_categories(category_id) ON DELETE RESTRICT,
  title TEXT NOT NULL,
  caption TEXT NOT NULL,
  publish_status TEXT NOT NULL DEFAULT 'DRAFT' CHECK(publish_status IN ('DRAFT','PUBLISHED','ARCHIVED')),
  ...
);
```

### Proof of Non-Leakage (Database Engine Invariant)
To guarantee that a buggy application route or unauthorized administrator cannot accidentally publish unsafe media, a PostgreSQL trigger function enforces strict safety at the database engine level:

```sql
CREATE OR REPLACE FUNCTION littlenet_validate_curated_publish() RETURNS trigger AS $$
DECLARE
  asset_status TEXT;
  asset_safe BOOLEAN;
BEGIN
  IF NEW.publish_status='PUBLISHED' THEN
    SELECT moderation_status,is_safe INTO asset_status,asset_safe
      FROM curated_media_assets WHERE asset_id=NEW.asset_id;
    IF asset_status IS DISTINCT FROM 'ALLOWED' OR asset_safe IS DISTINCT FROM TRUE THEN
      RAISE EXCEPTION 'Curated content cannot be published unless its media asset is ALLOWED and safe';
    END IF;
    IF NEW.published_at IS NULL THEN NEW.published_at=NOW(); END IF;
  END IF;
  NEW.updated_at=NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_validate_curated_publish
  BEFORE INSERT OR UPDATE OF asset_id,publish_status ON curated_content
  FOR EACH ROW EXECUTE FUNCTION littlenet_validate_curated_publish();
```

**Audit Proof**: Even if an INSERT or UPDATE query attempts to set `publish_status = 'PUBLISHED'`, the PostgreSQL engine aborts the transaction if the underlying media asset has `moderation_status` in `('BLOCKED', 'REVIEW', 'PENDING')` or `is_safe = FALSE`.

---

## 3. SQL Injection Audit

- Execution of `python tools/audit_dynamic_sql.py` confirmed `DYNAMIC_SQL_CALLS 2 APPROVED 2 ERRORS 0`.
- All query construction throughout `database/connection.py`, `auth/`, `child/`, `parent/`, and `mobile/` utilizes parameterized `%s` placeholders. Zero string interpolation of user input was found.
