-- migrate:up
-- Final social/supervision hardening: comments are parent-controlled and
-- individually disableable per post; timeline/comment/chat reads receive
-- indexes that support stable cursor pagination without OFFSET drift.
ALTER TABLE parent_control_settings
  ADD COLUMN IF NOT EXISTS allow_comments BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE posts
  ADD COLUMN IF NOT EXISTS comments_enabled BOOLEAN NOT NULL DEFAULT TRUE;

CREATE INDEX IF NOT EXISTS idx_comments_post_cursor
  ON comments(post_id, comment_id DESC)
  WHERE moderation_status='ALLOWED';

CREATE INDEX IF NOT EXISTS idx_activity_logs_child_cursor
  ON activity_logs(child_id, log_id DESC);

CREATE INDEX IF NOT EXISTS idx_child_messages_conversation_recent
  ON child_messages(conversation_id, sent_at DESC)
  WHERE is_deleted=FALSE;

-- migrate:down
DROP INDEX IF EXISTS idx_child_messages_conversation_recent;
DROP INDEX IF EXISTS idx_activity_logs_child_cursor;
DROP INDEX IF EXISTS idx_comments_post_cursor;
ALTER TABLE posts DROP COLUMN IF EXISTS comments_enabled;
ALTER TABLE parent_control_settings DROP COLUMN IF EXISTS allow_comments;
