-- migrate:up

CREATE TABLE IF NOT EXISTS demo_boost_state (
    state_id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (state_id = 1),
    status VARCHAR(16) NOT NULL DEFAULT 'OFF'
        CHECK (status IN ('OFF','WARMING','READY')),
    activated_by INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
    started_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    last_error TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO demo_boost_state(state_id, status)
VALUES (1, 'OFF')
ON CONFLICT (state_id) DO NOTHING;

-- migrate:down

DROP TABLE IF EXISTS demo_boost_state;
