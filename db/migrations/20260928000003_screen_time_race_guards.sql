-- migrate:up
-- Race guard for the screen-time extension flow: exactly one PENDING request
-- per child, enforced by the database itself. The application also serializes
-- the check-then-insert with a transaction-scoped advisory lock; this index
-- is defense in depth so concurrent double-submits can never create two
-- PENDING rows (which the approve paths would otherwise stack into bonus
-- minutes twice).

CREATE UNIQUE INDEX IF NOT EXISTS idx_ster_one_pending_per_child
  ON screen_time_extension_requests(child_id)
  WHERE status = 'PENDING';

-- migrate:down
DROP INDEX IF EXISTS idx_ster_one_pending_per_child;
