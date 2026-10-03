-- migrate:up
-- Password reset security hardening:
-- 1. Opaque reset transactions with uniform responses across existing and decoy accounts.
-- 2. Durable email outbox so HTTP requests do not block on SMTP/Resend transport or scale-to-zero.
CREATE TABLE IF NOT EXISTS password_reset_transactions (
    reset_token TEXT PRIMARY KEY,
    user_id INTEGER REFERENCES users(user_id) ON DELETE CASCADE,
    code_hash TEXT NOT NULL,
    request_ip TEXT,
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    max_attempts INTEGER NOT NULL DEFAULT 5,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_decoy BOOLEAN NOT NULL DEFAULT FALSE,
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'COMPLETED', 'EXPIRED', 'REVOKED'))
);

CREATE INDEX IF NOT EXISTS idx_pw_reset_tx_expires_status
    ON password_reset_transactions(expires_at, status);

CREATE INDEX IF NOT EXISTS idx_pw_reset_tx_user_status
    ON password_reset_transactions(user_id, status);

CREATE INDEX IF NOT EXISTS idx_pw_reset_tx_ip_created
    ON password_reset_transactions(request_ip, created_at);

CREATE TABLE IF NOT EXISTS password_reset_email_outbox (
    outbox_id BIGSERIAL PRIMARY KEY,
    reset_token TEXT NOT NULL REFERENCES password_reset_transactions(reset_token) ON DELETE CASCADE,
    recipient TEXT NOT NULL,
    subject TEXT NOT NULL,
    body_html TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    max_attempts INTEGER NOT NULL DEFAULT 5,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_reset_email_outbox_pending
    ON password_reset_email_outbox(created_at)
    WHERE completed_at IS NULL AND attempts < 5;

-- migrate:down
DROP TABLE IF EXISTS password_reset_email_outbox;
DROP TABLE IF EXISTS password_reset_transactions;
