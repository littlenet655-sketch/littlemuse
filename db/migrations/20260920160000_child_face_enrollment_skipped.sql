-- migrate:up
ALTER TABLE child_profiles ADD COLUMN IF NOT EXISTS face_enrollment_skipped BOOLEAN NOT NULL DEFAULT FALSE;

-- migrate:down
ALTER TABLE child_profiles DROP COLUMN IF EXISTS face_enrollment_skipped;
