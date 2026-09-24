-- migrate:up
-- Forward-only architecture alignment from the already-merged creator_key model
-- to the relational creator_id model. Do not rewrite migration 00002.

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='curated_creators' AND column_name='vertical'
  ) AND NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='curated_creators' AND column_name='interest_vertical'
  ) THEN
    ALTER TABLE curated_creators RENAME COLUMN vertical TO interest_vertical;
  END IF;
END $$;

ALTER TABLE curated_creators
  ADD COLUMN IF NOT EXISTS creator_id BIGSERIAL,
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP;

-- creator_key must remain a stable unique seed key while creator_id becomes
-- the actual relational primary key.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid='curated_creators'::regclass
      AND conname='curated_creators_creator_key_unique'
  ) THEN
    ALTER TABLE curated_creators
      ADD CONSTRAINT curated_creators_creator_key_unique UNIQUE (creator_key);
  END IF;
END $$;

-- Drop the old curated_content -> creator_key FK before replacing the PK.
DO $$
DECLARE fk_name text;
BEGIN
  SELECT c.conname INTO fk_name
  FROM pg_constraint c
  WHERE c.conrelid='curated_content'::regclass
    AND c.contype='f'
    AND pg_get_constraintdef(c.oid) ILIKE '%(creator_key)%'
    AND pg_get_constraintdef(c.oid) ILIKE '%curated_creators%';
  IF fk_name IS NOT NULL THEN
    EXECUTE format('ALTER TABLE curated_content DROP CONSTRAINT %I', fk_name);
  END IF;
END $$;

ALTER TABLE curated_creators DROP CONSTRAINT IF EXISTS curated_creators_pkey;
ALTER TABLE curated_creators
  ADD CONSTRAINT curated_creators_pkey PRIMARY KEY (creator_id);

ALTER TABLE curated_content
  ADD COLUMN IF NOT EXISTS creator_id BIGINT;

UPDATE curated_content cc
SET creator_id = cr.creator_id
FROM curated_creators cr
WHERE cc.creator_id IS NULL
  AND cc.creator_key = cr.creator_key;

-- Fail closed: every existing curated row from migration 00002 must resolve to
-- one editorial creator before the old key is removed.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM curated_content WHERE creator_id IS NULL) THEN
    RAISE EXCEPTION 'curated_creator_backfill_incomplete';
  END IF;
END $$;

ALTER TABLE curated_content
  ALTER COLUMN creator_id SET NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid='curated_content'::regclass
      AND conname='curated_content_creator_id_fkey'
  ) THEN
    ALTER TABLE curated_content
      ADD CONSTRAINT curated_content_creator_id_fkey
      FOREIGN KEY (creator_id) REFERENCES curated_creators(creator_id);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_curated_content_creator_id
  ON curated_content(creator_id);

ALTER TABLE curated_content DROP COLUMN IF EXISTS creator_key;

-- migrate:down
ALTER TABLE curated_content
  ADD COLUMN IF NOT EXISTS creator_key VARCHAR(64);

UPDATE curated_content cc
SET creator_key = cr.creator_key
FROM curated_creators cr
WHERE cc.creator_key IS NULL
  AND cc.creator_id = cr.creator_id;

ALTER TABLE curated_content
  ALTER COLUMN creator_key SET NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid='curated_content'::regclass
      AND conname='curated_content_creator_key_fkey'
  ) THEN
    ALTER TABLE curated_content
      ADD CONSTRAINT curated_content_creator_key_fkey
      FOREIGN KEY (creator_key) REFERENCES curated_creators(creator_key);
  END IF;
END $$;

DROP INDEX IF EXISTS idx_curated_content_creator_id;
ALTER TABLE curated_content DROP COLUMN IF EXISTS creator_id;

ALTER TABLE curated_creators DROP CONSTRAINT IF EXISTS curated_creators_pkey;
ALTER TABLE curated_creators
  ADD CONSTRAINT curated_creators_pkey PRIMARY KEY (creator_key);
ALTER TABLE curated_creators DROP CONSTRAINT IF EXISTS curated_creators_creator_key_unique;
ALTER TABLE curated_creators DROP COLUMN IF EXISTS creator_id;
ALTER TABLE curated_creators DROP COLUMN IF EXISTS updated_at;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='curated_creators' AND column_name='interest_vertical'
  ) AND NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='curated_creators' AND column_name='vertical'
  ) THEN
    ALTER TABLE curated_creators RENAME COLUMN interest_vertical TO vertical;
  END IF;
END $$;
