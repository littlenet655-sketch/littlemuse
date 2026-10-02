-- migrate:up
-- Support the 30-day child/category affinity aggregation used when a new
-- recommendation session is ranked. This keeps the behavior-learning query
-- bounded to one inexpensive indexed lookup per session.
CREATE INDEX IF NOT EXISTS idx_recommendation_signals_child_type_recent
  ON recommendation_signals(child_id, source_type, created_at DESC);

-- migrate:down
DROP INDEX IF EXISTS idx_recommendation_signals_child_type_recent;
