-- migrate:up

-- Identity comparisons in the application are case-insensitive. Make the
-- database authoritative too so concurrent signups cannot create Alice/alice.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM users WHERE username IS NOT NULL GROUP BY LOWER(username) HAVING COUNT(*) > 1) THEN
    RAISE EXCEPTION 'Cannot add case-insensitive username uniqueness: duplicates exist';
  END IF;
  IF EXISTS (SELECT 1 FROM users WHERE email IS NOT NULL GROUP BY LOWER(email) HAVING COUNT(*) > 1) THEN
    RAISE EXCEPTION 'Cannot add case-insensitive email uniqueness: duplicates exist';
  END IF;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS users_username_ci_unique ON users ((LOWER(username))) WHERE username IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS users_email_ci_unique ON users ((LOWER(email))) WHERE email IS NOT NULL;

-- Durable private-object deletion outbox. Objects remain private even when a
-- delete retry is pending, so a crash can cause storage leakage but not exposure.
CREATE TABLE IF NOT EXISTS media_delete_outbox (
  outbox_id BIGSERIAL PRIMARY KEY,
  reference TEXT NOT NULL UNIQUE,
  source_table TEXT NOT NULL,
  source_id BIGINT,
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_media_delete_outbox_pending
  ON media_delete_outbox(created_at) WHERE completed_at IS NULL;

CREATE OR REPLACE FUNCTION littlenet_queue_post_media_delete() RETURNS trigger AS $$
BEGIN
  IF OLD.media_path LIKE 'uploads/r2/%' THEN
    INSERT INTO media_delete_outbox(reference,source_table,source_id)
    VALUES(OLD.media_path,'posts',OLD.post_id)
    ON CONFLICT(reference) DO UPDATE SET completed_at=NULL,last_error=NULL;
  END IF;
  IF OLD.story_music_path LIKE 'uploads/r2/%' THEN
    INSERT INTO media_delete_outbox(reference,source_table,source_id)
    VALUES(OLD.story_music_path,'posts',OLD.post_id)
    ON CONFLICT(reference) DO UPDATE SET completed_at=NULL,last_error=NULL;
  END IF;
  RETURN OLD;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_posts_media_delete_outbox ON posts;
CREATE TRIGGER trg_posts_media_delete_outbox
  AFTER DELETE ON posts FOR EACH ROW EXECUTE FUNCTION littlenet_queue_post_media_delete();

CREATE OR REPLACE FUNCTION littlenet_queue_message_media_delete() RETURNS trigger AS $$
BEGIN
  IF OLD.media_path LIKE 'uploads/r2/%' THEN
    INSERT INTO media_delete_outbox(reference,source_table,source_id)
    VALUES(OLD.media_path,'child_messages',OLD.child_message_id)
    ON CONFLICT(reference) DO UPDATE SET completed_at=NULL,last_error=NULL;
  END IF;
  RETURN OLD;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_messages_media_delete_outbox ON child_messages;
CREATE TRIGGER trg_messages_media_delete_outbox
  AFTER DELETE ON child_messages FOR EACH ROW EXECUTE FUNCTION littlenet_queue_message_media_delete();

-- A message may only reference a conversation containing exactly its sender and
-- receiver. This prevents future routes/scripts from bypassing app authorization.
CREATE OR REPLACE FUNCTION littlenet_validate_message_conversation() RETURNS trigger AS $$
DECLARE c1 BIGINT; c2 BIGINT;
BEGIN
  SELECT child1_id,child2_id INTO c1,c2 FROM child_conversations WHERE conversation_id=NEW.conversation_id;
  IF c1 IS NULL OR c2 IS NULL OR NOT (
       (NEW.sender_child_id=c1 AND NEW.receiver_child_id=c2)
    OR (NEW.sender_child_id=c2 AND NEW.receiver_child_id=c1)
  ) THEN
    RAISE EXCEPTION 'Message participants do not match conversation %', NEW.conversation_id;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_validate_message_conversation ON child_messages;
CREATE TRIGGER trg_validate_message_conversation
  BEFORE INSERT OR UPDATE OF conversation_id,sender_child_id,receiver_child_id ON child_messages
  FOR EACH ROW EXECUTE FUNCTION littlenet_validate_message_conversation();

-- Enforce parent/child role semantics at the persistence boundary.
CREATE OR REPLACE FUNCTION littlenet_validate_parent_child_roles() RETURNS trigger AS $$
DECLARE child_role TEXT; parent_role TEXT; verified_role TEXT;
BEGIN
  SELECT role INTO child_role FROM users WHERE user_id=NEW.child_id;
  IF child_role IS DISTINCT FROM 'CHILD' THEN RAISE EXCEPTION 'child_id must reference a CHILD'; END IF;
  IF NEW.parent_id IS NOT NULL THEN
    SELECT role INTO parent_role FROM users WHERE user_id=NEW.parent_id;
    IF parent_role IS DISTINCT FROM 'PARENT' THEN RAISE EXCEPTION 'parent_id must reference a PARENT'; END IF;
  END IF;
  IF NEW.verified_parent_id IS NOT NULL THEN
    SELECT role INTO verified_role FROM users WHERE user_id=NEW.verified_parent_id;
    IF verified_role IS DISTINCT FROM 'PARENT' THEN RAISE EXCEPTION 'verified_parent_id must reference a PARENT'; END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_validate_parent_child_roles ON parent_child_map;
CREATE TRIGGER trg_validate_parent_child_roles
  BEFORE INSERT OR UPDATE OF child_id,parent_id,verified_parent_id ON parent_child_map
  FOR EACH ROW EXECUTE FUNCTION littlenet_validate_parent_child_roles();

-- Settings rows also need role correctness even when an administrative/data
-- repair path writes them outside normal Flask routes.
CREATE OR REPLACE FUNCTION littlenet_validate_parent_setting_roles() RETURNS trigger AS $$
DECLARE child_role TEXT; parent_role TEXT;
BEGIN
  SELECT role INTO child_role FROM users WHERE user_id=NEW.child_id;
  SELECT role INTO parent_role FROM users WHERE user_id=NEW.parent_id;
  IF child_role IS DISTINCT FROM 'CHILD' OR parent_role IS DISTINCT FROM 'PARENT' THEN
    RAISE EXCEPTION 'Parent settings require PARENT -> CHILD roles';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_validate_parent_control_roles ON parent_control_settings;
CREATE TRIGGER trg_validate_parent_control_roles
  BEFORE INSERT OR UPDATE OF child_id,parent_id ON parent_control_settings
  FOR EACH ROW EXECUTE FUNCTION littlenet_validate_parent_setting_roles();
DROP TRIGGER IF EXISTS trg_validate_parent_safety_roles ON parent_safety_settings;
CREATE TRIGGER trg_validate_parent_safety_roles
  BEFORE INSERT OR UPDATE OF child_id,parent_id ON parent_safety_settings
  FOR EACH ROW EXECUTE FUNCTION littlenet_validate_parent_setting_roles();

-- migrate:down
DROP TRIGGER IF EXISTS trg_validate_parent_safety_roles ON parent_safety_settings;
DROP TRIGGER IF EXISTS trg_validate_parent_control_roles ON parent_control_settings;
DROP FUNCTION IF EXISTS littlenet_validate_parent_setting_roles();
DROP TRIGGER IF EXISTS trg_validate_parent_child_roles ON parent_child_map;
DROP FUNCTION IF EXISTS littlenet_validate_parent_child_roles();
DROP TRIGGER IF EXISTS trg_validate_message_conversation ON child_messages;
DROP FUNCTION IF EXISTS littlenet_validate_message_conversation();
DROP TRIGGER IF EXISTS trg_messages_media_delete_outbox ON child_messages;
DROP FUNCTION IF EXISTS littlenet_queue_message_media_delete();
DROP TRIGGER IF EXISTS trg_posts_media_delete_outbox ON posts;
DROP FUNCTION IF EXISTS littlenet_queue_post_media_delete();
DROP TABLE IF EXISTS media_delete_outbox;
DROP INDEX IF EXISTS users_email_ci_unique;
DROP INDEX IF EXISTS users_username_ci_unique;
