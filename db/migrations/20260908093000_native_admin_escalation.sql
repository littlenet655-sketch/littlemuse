-- migrate:up

-- Native Admin Mode has a three-stage moderation action surface:
-- APPROVE / BLOCK resolve an event, while ESCALATE records moderator attention
-- and deliberately leaves the event OPEN for a later final decision.
--
-- The original schema made moderation_reviews.event_id UNIQUE and restricted
-- action to APPROVE/BLOCK. That made ESCALATE fail immediately and, even if the
-- action constraint were widened alone, prevented a later final review. Keep
-- the table as an append-only review trail instead: many review actions may
-- reference one moderation event, with only APPROVE/BLOCK resolving it.
ALTER TABLE moderation_reviews
  DROP CONSTRAINT IF EXISTS moderation_reviews_event_id_key;

ALTER TABLE moderation_reviews
  DROP CONSTRAINT IF EXISTS moderation_reviews_action_check;

ALTER TABLE moderation_reviews
  ADD CONSTRAINT moderation_reviews_action_check
  CHECK (action IN ('APPROVE','BLOCK','ESCALATE'));

CREATE INDEX IF NOT EXISTS idx_moderation_reviews_event
  ON moderation_reviews(event_id, reviewed_at DESC);

-- migrate:down
DROP INDEX IF EXISTS idx_moderation_reviews_event;

-- A downgrade is only safe when no event has accumulated multiple review-trail
-- rows. Fail explicitly rather than silently deleting audit evidence.
DO $$
BEGIN
  IF EXISTS (
    SELECT event_id FROM moderation_reviews
    GROUP BY event_id HAVING COUNT(*) > 1
  ) THEN
    RAISE EXCEPTION 'Cannot restore one-review-per-event constraint while moderation review history contains multiple actions';
  END IF;
END $$;

ALTER TABLE moderation_reviews
  DROP CONSTRAINT IF EXISTS moderation_reviews_action_check;
ALTER TABLE moderation_reviews
  ADD CONSTRAINT moderation_reviews_action_check
  CHECK (action IN ('APPROVE','BLOCK'));
ALTER TABLE moderation_reviews
  ADD CONSTRAINT moderation_reviews_event_id_key UNIQUE(event_id);
