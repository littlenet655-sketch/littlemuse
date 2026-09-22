-- migrate:up
-- A physical Expo push token must belong to exactly one current LittleNet user.
-- Older schema uniqueness was (user_id, push_token), which allowed the same
-- device token to remain active for multiple accounts after an account switch.

WITH ranked AS (
  SELECT id,
         ROW_NUMBER() OVER (
           PARTITION BY push_token
           ORDER BY (revoked_at IS NULL) DESC,
                    last_seen_at DESC NULLS LAST,
                    id DESC
         ) AS rn
  FROM user_device_tokens
)
DELETE FROM user_device_tokens t
USING ranked r
WHERE t.id = r.id AND r.rn > 1;

ALTER TABLE user_device_tokens
  DROP CONSTRAINT IF EXISTS uq_user_device_token;

ALTER TABLE user_device_tokens
  DROP CONSTRAINT IF EXISTS uq_push_token_owner;

ALTER TABLE user_device_tokens
  ADD CONSTRAINT uq_push_token_owner UNIQUE (push_token);

-- migrate:down
ALTER TABLE user_device_tokens
  DROP CONSTRAINT IF EXISTS uq_push_token_owner;

ALTER TABLE user_device_tokens
  ADD CONSTRAINT uq_user_device_token UNIQUE (user_id, push_token);
