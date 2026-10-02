-- migrate:up

-- Intentional re-enqueue of an exhausted or completed outbox row must start a
-- new bounded cycle. In-flight rows keep their attempt count.
-- Historical 20260907150000 is left untouched; this replaces the live functions.

CREATE OR REPLACE FUNCTION littlenet_queue_post_media_delete() RETURNS trigger AS $$
BEGIN
  IF OLD.media_path LIKE 'uploads/r2/%' THEN
    INSERT INTO media_delete_outbox(reference,source_table,source_id)
    VALUES(OLD.media_path,'posts',OLD.post_id)
    ON CONFLICT(reference) DO UPDATE
      SET completed_at=NULL,last_error=NULL,
          attempts=CASE
            WHEN media_delete_outbox.attempts >= 8
              OR media_delete_outbox.completed_at IS NOT NULL
            THEN 0 ELSE media_delete_outbox.attempts END;
  END IF;
  IF OLD.story_music_path LIKE 'uploads/r2/%' THEN
    INSERT INTO media_delete_outbox(reference,source_table,source_id)
    VALUES(OLD.story_music_path,'posts',OLD.post_id)
    ON CONFLICT(reference) DO UPDATE
      SET completed_at=NULL,last_error=NULL,
          attempts=CASE
            WHEN media_delete_outbox.attempts >= 8
              OR media_delete_outbox.completed_at IS NOT NULL
            THEN 0 ELSE media_delete_outbox.attempts END;
  END IF;
  RETURN OLD;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION littlenet_queue_message_media_delete() RETURNS trigger AS $$
BEGIN
  IF OLD.media_path LIKE 'uploads/r2/%' THEN
    INSERT INTO media_delete_outbox(reference,source_table,source_id)
    VALUES(OLD.media_path,'child_messages',OLD.child_message_id)
    ON CONFLICT(reference) DO UPDATE
      SET completed_at=NULL,last_error=NULL,
          attempts=CASE
            WHEN media_delete_outbox.attempts >= 8
              OR media_delete_outbox.completed_at IS NOT NULL
            THEN 0 ELSE media_delete_outbox.attempts END;
  END IF;
  RETURN OLD;
END;
$$ LANGUAGE plpgsql;

-- migrate:down

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
