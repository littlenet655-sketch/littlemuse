-- migrate:up
-- password_reset_otps was previously created lazily at request time by
-- auth/password_reset.py::_ensure_table(). dbmate is the single migration
-- owner, so the table is created here. The request-time
-- CREATE TABLE IF NOT EXISTS remains only as a defensive fallback and must
-- never diverge from this definition.
CREATE TABLE IF NOT EXISTS password_reset_otps (
    user_id INTEGER PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    code_hash TEXT NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    sent_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- migrate:down
DROP TABLE IF EXISTS password_reset_otps;
