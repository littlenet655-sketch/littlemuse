-- migrate:up

-- Submission-critical publication freshness and explainable recommendation feedback.
CREATE TABLE IF NOT EXISTS recommendation_signals (
  signal_id BIGSERIAL PRIMARY KEY,
  child_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  source_type VARCHAR(20) NOT NULL CHECK(source_type IN ('SOCIAL','CURATED','CREATOR')),
  source_id BIGINT NOT NULL,
  signal VARCHAR(30) NOT NULL CHECK(signal IN (
    'INTEREST','REEL_COMPLETION','REEL_REPLAY','LIKE','SAVE','COMMENT',
    'SHARE','FOLLOW','SEARCH_CLICK','NOT_INTERESTED','HIDE','MUTE','BLOCK','REPORT'
  )),
  weight NUMERIC(8,3) NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_recommendation_signals_child_source
  ON recommendation_signals(child_id,source_type,source_id,created_at DESC);

ALTER TABLE content_impressions
  ADD COLUMN IF NOT EXISTS replay_count INTEGER NOT NULL DEFAULT 0;

-- migrate:down

ALTER TABLE content_impressions
  DROP COLUMN IF EXISTS replay_count;

DROP TABLE IF EXISTS recommendation_signals;