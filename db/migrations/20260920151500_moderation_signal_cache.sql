-- migrate:up
-- Exact-content cache for reusable moderation *signals*. Final policy decisions
-- are never cached; each child/session re-applies the current LittleNet policy.
CREATE TABLE IF NOT EXISTS moderation_signal_cache (
  content_type VARCHAR(16) NOT NULL CHECK (content_type IN ('TEXT','IMAGE','VIDEO')),
  content_sha256 CHAR(64) NOT NULL,
  cache_version VARCHAR(80) NOT NULL,
  signals JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_used_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  hit_count BIGINT NOT NULL DEFAULT 0 CHECK (hit_count >= 0),
  PRIMARY KEY(content_type, content_sha256, cache_version)
);

CREATE INDEX IF NOT EXISTS idx_moderation_signal_cache_recent
  ON moderation_signal_cache(content_type, cache_version, created_at DESC);

-- migrate:down
DROP INDEX IF EXISTS idx_moderation_signal_cache_recent;
DROP TABLE IF EXISTS moderation_signal_cache;
