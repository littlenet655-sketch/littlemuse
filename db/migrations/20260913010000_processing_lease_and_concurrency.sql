-- migrate:up
ALTER TABLE posts ADD COLUMN IF NOT EXISTS processing_lease_token VARCHAR(64);
ALTER TABLE posts ADD COLUMN IF NOT EXISTS processing_lease_expires_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_posts_lease_expiry ON posts(processing_lease_expires_at)
  WHERE processing_status IN ('UPLOADED', 'PROCESSING');

-- migrate:down
DROP INDEX IF EXISTS idx_posts_lease_expiry;
ALTER TABLE posts DROP COLUMN IF EXISTS processing_lease_expires_at;
ALTER TABLE posts DROP COLUMN IF EXISTS processing_lease_token;
