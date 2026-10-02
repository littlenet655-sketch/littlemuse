-- migrate:up
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_account_status_check;
ALTER TABLE users ADD CONSTRAINT users_account_status_check
  CHECK (account_status IN ('PENDING_APPROVAL','ACTIVE','REJECTED','SUSPENDED','DEACTIVATED'));

-- migrate:down
UPDATE users SET account_status='SUSPENDED' WHERE account_status='DEACTIVATED';
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_account_status_check;
ALTER TABLE users ADD CONSTRAINT users_account_status_check
  CHECK (account_status IN ('PENDING_APPROVAL','ACTIVE','REJECTED','SUSPENDED'));
