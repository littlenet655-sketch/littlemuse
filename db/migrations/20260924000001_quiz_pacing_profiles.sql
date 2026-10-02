-- migrate:up
-- Parent-selected random Reel Brain Break pacing profiles.
-- Preserve the current persisted threshold/latch; the new policy only affects
-- the next roll after a compulsory quiz is completed.
ALTER TABLE parent_quiz_settings
  ADD COLUMN IF NOT EXISTS quiz_pacing_policy VARCHAR(16) NOT NULL DEFAULT 'FREQUENT';

ALTER TABLE parent_quiz_settings
  DROP CONSTRAINT IF EXISTS parent_quiz_settings_quiz_pacing_policy_check;
ALTER TABLE parent_quiz_settings
  ADD CONSTRAINT parent_quiz_settings_quiz_pacing_policy_check
  CHECK (quiz_pacing_policy IN ('FREQUENT','BALANCED','LIGHT'));

ALTER TABLE child_quiz_progress
  DROP CONSTRAINT IF EXISTS child_quiz_progress_next_quiz_threshold_check;
ALTER TABLE child_quiz_progress
  ADD CONSTRAINT child_quiz_progress_next_quiz_threshold_check
  CHECK (next_quiz_threshold BETWEEN 2 AND 10);

-- migrate:down
UPDATE parent_quiz_settings SET quiz_pacing_policy='FREQUENT';
UPDATE child_quiz_progress SET next_quiz_threshold=LEAST(next_quiz_threshold,5);
ALTER TABLE child_quiz_progress
  DROP CONSTRAINT IF EXISTS child_quiz_progress_next_quiz_threshold_check;
ALTER TABLE child_quiz_progress
  ADD CONSTRAINT child_quiz_progress_next_quiz_threshold_check
  CHECK (next_quiz_threshold BETWEEN 2 AND 5);
ALTER TABLE parent_quiz_settings
  DROP COLUMN IF EXISTS quiz_pacing_policy;
