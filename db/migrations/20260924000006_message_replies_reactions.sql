-- migrate:up
ALTER TABLE child_messages
  ADD COLUMN IF NOT EXISTS reply_to_message_id BIGINT REFERENCES child_messages(child_message_id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_child_messages_reply_to
  ON child_messages(reply_to_message_id)
  WHERE reply_to_message_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS message_reactions (
  reaction_id BIGSERIAL PRIMARY KEY,
  message_id BIGINT NOT NULL REFERENCES child_messages(child_message_id) ON DELETE CASCADE,
  child_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  emoji VARCHAR(8) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(message_id, child_id)
);

CREATE INDEX IF NOT EXISTS idx_message_reactions_message
  ON message_reactions(message_id, updated_at DESC);

-- migrate:down
DROP INDEX IF EXISTS idx_message_reactions_message;
DROP TABLE IF EXISTS message_reactions;
DROP INDEX IF EXISTS idx_child_messages_reply_to;
ALTER TABLE child_messages DROP COLUMN IF EXISTS reply_to_message_id;
