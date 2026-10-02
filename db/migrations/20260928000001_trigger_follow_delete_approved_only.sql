-- migrate:up
-- Defect fix (red-team hole): trg_littlenet_friendship_delete_pair used to
-- cascade the delete of ANY followers row onto its reciprocal row. That meant
-- deleting one child's pending outgoing follow request (e.g.
-- cancel_outgoing_follow) also deleted the other child's genuine incoming
-- request -- the Follow-Back deletion bug survived via the trigger.
--
-- The pair-cascade now fires ONLY for established friendships
-- (OLD.approved IS TRUE). Pending requests are cleaned up explicitly by the
-- application (cancel_outgoing_follow in child/service.py and the parent
-- reject paths in mobile/api.py / parent/routes.py), which delete the
-- handshake rows themselves.

DROP TRIGGER IF EXISTS trg_littlenet_friendship_delete_pair ON followers;
CREATE TRIGGER trg_littlenet_friendship_delete_pair
AFTER DELETE ON followers
FOR EACH ROW
WHEN (OLD.approved IS TRUE)
EXECUTE FUNCTION littlenet_friendship_delete_pair();

-- migrate:down
-- Restore the unconditional pair-cascade (reintroduces the Follow-Back bug;
-- kept only so the migration is reversible).
DROP TRIGGER IF EXISTS trg_littlenet_friendship_delete_pair ON followers;
CREATE TRIGGER trg_littlenet_friendship_delete_pair
AFTER DELETE ON followers
FOR EACH ROW
EXECUTE FUNCTION littlenet_friendship_delete_pair();
