-- migrate:up
-- LittleNet P0: Upload State Machine and Face Authentication Hardening

-- 1. Ensure no invalid face embeddings exist before applying constraint
DELETE FROM face_profiles
WHERE embedding IS NULL
   OR jsonb_typeof(embedding) != 'array'
   OR jsonb_array_length(embedding) != 512
   OR model_name != 'Facenet512';

-- 2. Enforce fail-closed child face profile embedding constraint (must be array with EXACTLY 512 dimensions and model_name='Facenet512')
ALTER TABLE face_profiles DROP CONSTRAINT IF EXISTS face_profiles_embedding_valid_check;
ALTER TABLE face_profiles ADD CONSTRAINT face_profiles_embedding_valid_check
  CHECK (model_name = 'Facenet512' AND jsonb_typeof(embedding) = 'array' AND jsonb_array_length(embedding) = 512);

-- 3. Add durable upload idempotency and processing attempt columns to posts
ALTER TABLE posts ADD COLUMN IF NOT EXISTS upload_id UUID REFERENCES upload_sessions(upload_id) ON DELETE SET NULL;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS processing_attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS max_processing_attempts INTEGER NOT NULL DEFAULT 3;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS last_attempt_at TIMESTAMP;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS job_id VARCHAR(100);

-- 4. Reconcile historical duplicate source_media_path without inventing fake storage keys
-- (preserve canonical real reference on the newest post, nullify older duplicate rows)
WITH ranked_dups AS (
  SELECT post_id, source_media_path,
         ROW_NUMBER() OVER (PARTITION BY source_media_path ORDER BY post_id DESC) as rn
  FROM posts
  WHERE source_media_path IS NOT NULL
)
UPDATE posts p
SET source_media_path = NULL
FROM ranked_dups r
WHERE p.post_id = r.post_id AND r.rn > 1;

CREATE UNIQUE INDEX IF NOT EXISTS idx_posts_source_media_path_uniq
  ON posts (source_media_path)
  WHERE source_media_path IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_posts_upload_id_uniq
  ON posts (upload_id)
  WHERE upload_id IS NOT NULL;

-- migrate:down
DROP INDEX IF EXISTS idx_posts_upload_id_uniq;
DROP INDEX IF EXISTS idx_posts_source_media_path_uniq;
ALTER TABLE posts DROP COLUMN IF EXISTS job_id;
ALTER TABLE posts DROP COLUMN IF EXISTS last_attempt_at;
ALTER TABLE posts DROP COLUMN IF EXISTS max_processing_attempts;
ALTER TABLE posts DROP COLUMN IF EXISTS processing_attempts;
ALTER TABLE posts DROP COLUMN IF EXISTS upload_id;
ALTER TABLE face_profiles DROP CONSTRAINT IF EXISTS face_profiles_embedding_valid_check;
