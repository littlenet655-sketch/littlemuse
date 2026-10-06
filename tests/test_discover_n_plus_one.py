import os
import pytest
from child.service import batch_relationship_states, is_following, is_follow_pending
from database.connection import execute, fetch_all


@pytest.fixture(autouse=True)
def setup_db():
    if not os.environ.get('DATABASE_URL'):
        pytest.skip('An active DATABASE_URL is required')


def test_discover_relationship_query_count_batching():
    viewer_id = 999010
    execute("""
        INSERT INTO users (user_id, role, account_status, email, username, full_name, password_hash)
        VALUES (%s, 'CHILD', 'ACTIVE', 'k10@example.com', 'kid10', 'Kid 10', 'hash') ON CONFLICT DO NOTHING
    """, (viewer_id,))

    target_ids = []
    for i in range(1, 31):
        tid = 999010 + i
        target_ids.append(tid)
        execute("""
            INSERT INTO users (user_id, role, account_status, email, username, full_name, password_hash)
            VALUES (%s, 'CHILD', 'ACTIVE', %s, %s, %s, 'hash') ON CONFLICT DO NOTHING
        """, (tid, 'k' + str(tid) + '@example.com', 'k' + str(tid), 'Kid ' + str(tid)))

    for tid in target_ids[0:5]:
        execute("""
            INSERT INTO followers (child_id, following_child_id, approved, approval_stage)
            VALUES (%s, %s, TRUE, 'ACTIVE')
            ON CONFLICT (child_id, following_child_id) DO UPDATE SET approved = TRUE, approval_stage = 'ACTIVE'
        """, (viewer_id, tid))

    for tid in target_ids[5:10]:
        execute("""
            INSERT INTO followers (child_id, following_child_id, approved, approval_stage)
            VALUES (%s, %s, FALSE, 'REQUESTED')
            ON CONFLICT (child_id, following_child_id) DO UPDATE SET approved = FALSE, approval_stage = 'REQUESTED'
        """, (viewer_id, tid))

    from unittest.mock import patch

    for cohort_size in [1, 5, 15, 30]:
        subset = target_ids[slice(0, cohort_size)]
        batch_results = batch_relationship_states(viewer_id, subset)
        assert len(batch_results) == cohort_size

        for tid in subset:
            is_f = batch_results[tid]['is_following']
            is_p = batch_results[tid]['is_pending']
            assert is_f == is_following(viewer_id, tid)
            assert is_p == is_follow_pending(viewer_id, tid)

        query_counts = [0]
        orig_fetch_all = fetch_all
        def counted_fetch_all(*q, **args):
            query_counts[0] += 1
            return orig_fetch_all(*q, **args)

        with patch('child.service.fetch_all', side_effect=counted_fetch_all):
            batch_results = batch_relationship_states(viewer_id, subset)
            assert query_counts[0] == 1, f'Batched relationship check must execute exactly 1 SQL query for cohort {cohort_size}'
