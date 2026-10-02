-- migrate:up
-- Performance indexes for tables introduced by curated dataset migrations.
-- Kept out of database/schema.sql because those tables are migration-owned and
-- do not exist yet when the legacy bootstrap schema is applied.
CREATE INDEX IF NOT EXISTS idx_content_impressions_child_shown
  ON content_impressions(child_id, shown_at DESC);

CREATE INDEX IF NOT EXISTS idx_feed_sessions_child_exp
  ON feed_sessions(child_id, surface, expires_at);

-- migrate:down
DROP INDEX IF EXISTS idx_feed_sessions_child_exp;
DROP INDEX IF EXISTS idx_content_impressions_child_shown;
