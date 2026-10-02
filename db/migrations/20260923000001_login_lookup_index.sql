-- migrate:up
-- Login looks users up by LOWER(email)/LOWER(username), which defeats the
-- plain btree indexes on those columns and forces a sequential scan on every
-- login. Expression indexes make the lookup index-backed.

CREATE INDEX IF NOT EXISTS idx_users_lower_email ON users (LOWER(email));
CREATE INDEX IF NOT EXISTS idx_users_lower_username ON users (LOWER(username));

-- migrate:down
DROP INDEX IF EXISTS idx_users_lower_email;
DROP INDEX IF EXISTS idx_users_lower_username;
