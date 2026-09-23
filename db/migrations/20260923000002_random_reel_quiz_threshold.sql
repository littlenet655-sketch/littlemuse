-- migrate:up
-- Introduce server-authoritative random non-skippable Reel Brain Break threshold (2-5).
-- Preserves all existing posts_seen, quiz_required, required_quiz_id, and viewed_post_ids.
ALTER TABLE child_quiz_progress
  ADD COLUMN IF NOT EXISTS next_quiz_threshold INTEGER NOT NULL DEFAULT 5
  CHECK (next_quiz_threshold BETWEEN 2 AND 5);

-- migrate:down
ALTER TABLE child_quiz_progress
  DROP COLUMN IF EXISTS next_quiz_threshold;
