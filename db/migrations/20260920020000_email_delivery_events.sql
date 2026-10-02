-- migrate:up
-- Track transactional email lifecycle without storing OTP bodies or secrets.
CREATE TABLE IF NOT EXISTS email_delivery_events (
  event_id BIGSERIAL PRIMARY KEY,
  provider_message_id TEXT UNIQUE NOT NULL,
  recipient TEXT NOT NULL,
  provider VARCHAR(32) NOT NULL DEFAULT 'RESEND',
  email_type VARCHAR(40) NOT NULL DEFAULT 'TRANSACTIONAL',
  status VARCHAR(30) NOT NULL DEFAULT 'ACCEPTED'
    CHECK (status IN ('ACCEPTED','SENT','DELIVERED','DELIVERY_DELAYED','BOUNCED','SUPPRESSED','FAILED','COMPLAINED')),
  failure_reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_event_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_email_delivery_recipient_status
  ON email_delivery_events(recipient, status, updated_at DESC);

-- migrate:down
DROP TABLE IF EXISTS email_delivery_events;
