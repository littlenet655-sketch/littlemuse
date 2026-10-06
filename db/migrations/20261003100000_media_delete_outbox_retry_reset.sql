-- migrate:up
-- Requeue a previously completed/exhausted media-delete outbox reference safely
-- when a newly deleted row points at the same R2 object.
CREATE OR REPLACE FUNCTION public.littlenet_queue_message_media_delete()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
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
$function$;

CREATE OR REPLACE FUNCTION public.littlenet_queue_post_media_delete()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
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
$function$;

-- migrate:down
CREATE OR REPLACE FUNCTION public.littlenet_queue_message_media_delete()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
  IF OLD.media_path LIKE 'uploads/r2/%' THEN
    INSERT INTO media_delete_outbox(reference,source_table,source_id)
    VALUES(OLD.media_path,'child_messages',OLD.child_message_id)
    ON CONFLICT(reference) DO UPDATE SET completed_at=NULL,last_error=NULL;
  END IF;
  RETURN OLD;
END;
$function$;

CREATE OR REPLACE FUNCTION public.littlenet_queue_post_media_delete()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
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
$function$;
