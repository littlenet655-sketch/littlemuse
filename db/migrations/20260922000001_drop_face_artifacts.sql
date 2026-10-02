-- migrate:up
-- Product decision 2026-09-22: all face/biometric artifacts are removed from
-- LittleNet. Children log in with a password; parents verify by email OTP.
-- Drop the face tables, the child_profiles deferral column, and the
-- face/liveness evidence columns on the parent_verifications audit table
-- (all IF EXISTS so the migration is safe to replay on databases that
-- never had them).
DROP TABLE IF EXISTS face_profiles CASCADE;
DROP TABLE IF EXISTS face_auth_challenges CASCADE;
DROP TABLE IF EXISTS face_login_attempts CASCADE;
ALTER TABLE child_profiles DROP COLUMN IF EXISTS face_enrollment_skipped;
ALTER TABLE parent_verifications DROP COLUMN IF EXISTS liveness_status;
ALTER TABLE parent_verifications DROP COLUMN IF EXISTS face_match_status;

-- migrate:down
-- Face removal is intentionally one-way; there is no down migration.
SELECT 1;
