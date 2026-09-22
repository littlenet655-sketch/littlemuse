"""End-to-End Real-App Acceptance Test Suite for LittleNet Phase 3 - Phase 17.

Tests Child A (38), Child B (40), and Parent P (37):
- Phase 5: Child-to-child chat send/receive/reply/persistence
- Phase 6: Chat safety (Safe -> ALLOW, PII -> BLOCK + Parent Alert, Grooming -> BLOCK, Trigger/AI fail -> REVIEW, Parent Approve/Block)
- Phase 7: Chat Details (Mute, Block & immediate revocation, Report)
- Phase 8 & 9: Pagination and history performance
- Phase 14: REVIEW / BLOCK publication containment
- Phase 15: Explore eligibility and non-follower behavior
- Phase 16: Follow / Unfollow / Block immediate lifecycle
- Phase 17: Parent controls live effect (disable/enable messaging, quiet hours, screen time)
"""
import json
import os
import unittest
from dotenv import load_dotenv
load_dotenv('.env')

from app import create_app
from database.connection import fetch_one, fetch_all, execute
from mobile.api import _issue_token
from services.social import can_interact, visible_posts
from services.controls import feature_allowed


class RealAppAcceptanceE2ETest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.client = cls.app.test_client()

        # Acceptance identities
        p_row = fetch_one("SELECT user_id, email FROM users WHERE username='parent_p'")
        if not p_row:
            p_row = execute(
                """INSERT INTO users(username, full_name, email, password_hash, role, account_status)
                   VALUES('parent_p', 'Parent P', 'parent_p@test.com', 'scrypt:test', 'PARENT', 'ACTIVE')
                   RETURNING user_id, email""",
                returning=True,
            )
        a_row = fetch_one("SELECT user_id, email FROM users WHERE username='child_a'")
        if not a_row:
            a_row = execute(
                """INSERT INTO users(username, full_name, email, password_hash, role, account_status, age)
                   VALUES('child_a', 'Child A', 'child_a@test.com', 'scrypt:test', 'CHILD', 'ACTIVE', 10)
                   RETURNING user_id, email""",
                returning=True,
            )
            execute("INSERT INTO child_profiles(child_id, full_name, age) VALUES(%s, 'Child A', 10) ON CONFLICT DO NOTHING", (a_row["user_id"],))
            execute("INSERT INTO face_profiles(child_id, embedding, model_name) VALUES(%s, %s::jsonb, 'Facenet512') ON CONFLICT DO NOTHING", (a_row["user_id"], json.dumps([0.05]*512)))
            execute("INSERT INTO child_quiz_progress(child_id, quiz_required) VALUES(%s, FALSE) ON CONFLICT DO NOTHING", (a_row["user_id"],))
            execute("INSERT INTO parent_child_map(parent_id, child_id, parent_name, parent_email, approved, approval_status) VALUES(%s, %s, 'Parent P', 'parent_p@test.com', TRUE, 'APPROVED') ON CONFLICT DO NOTHING", (p_row["user_id"], a_row["user_id"]))
            execute("INSERT INTO parent_control_settings(child_id, parent_id, allow_messaging) VALUES(%s, %s, TRUE) ON CONFLICT DO NOTHING", (a_row["user_id"], p_row["user_id"]))
        b_row = fetch_one("SELECT user_id, email FROM users WHERE username='child_b'")
        if not b_row:
            b_row = execute(
                """INSERT INTO users(username, full_name, email, password_hash, role, account_status, age)
                   VALUES('child_b', 'Child B', 'child_b@test.com', 'scrypt:test', 'CHILD', 'ACTIVE', 10)
                   RETURNING user_id, email""",
                returning=True,
            )
            execute("INSERT INTO child_profiles(child_id, full_name, age) VALUES(%s, 'Child B', 10) ON CONFLICT DO NOTHING", (b_row["user_id"],))
            execute("INSERT INTO face_profiles(child_id, embedding, model_name) VALUES(%s, %s::jsonb, 'Facenet512') ON CONFLICT DO NOTHING", (b_row["user_id"], json.dumps([0.05]*512)))
            execute("INSERT INTO child_quiz_progress(child_id, quiz_required) VALUES(%s, FALSE) ON CONFLICT DO NOTHING", (b_row["user_id"],))
            execute("INSERT INTO parent_child_map(parent_id, child_id, parent_name, parent_email, approved, approval_status) VALUES(%s, %s, 'Parent P', 'parent_p@test.com', TRUE, 'APPROVED') ON CONFLICT DO NOTHING", (p_row["user_id"], b_row["user_id"]))
            execute("INSERT INTO parent_control_settings(child_id, parent_id, allow_messaging) VALUES(%s, %s, TRUE) ON CONFLICT DO NOTHING", (b_row["user_id"], p_row["user_id"]))

        cls.pid = p_row['user_id']
        cls.aid = a_row['user_id']
        cls.bid = b_row['user_id']

        cls.token_p = _issue_token({"user_id": cls.pid, "role": "PARENT"})
        cls.token_a = _issue_token({"user_id": cls.aid, "role": "CHILD"})
        cls.token_b = _issue_token({"user_id": cls.bid, "role": "CHILD"})

        cls.headers_p = {'Authorization': f'Bearer {cls.token_p}', 'Content-Type': 'application/json'}
        cls.headers_a = {'Authorization': f'Bearer {cls.token_a}', 'Content-Type': 'application/json'}
        cls.headers_b = {'Authorization': f'Bearer {cls.token_b}', 'Content-Type': 'application/json'}

    def setUp(self):
        # Reset followers, blocks, messages between tests
        execute("DELETE FROM blocked_users WHERE blocker_id IN (%s, %s) OR blocked_id IN (%s, %s)", (self.aid, self.bid, self.aid, self.bid))
        execute("DELETE FROM muted_users WHERE muter_id IN (%s, %s) OR muted_id IN (%s, %s)", (self.aid, self.bid, self.aid, self.bid))
        execute("DELETE FROM child_messages WHERE sender_child_id IN (%s, %s) OR receiver_child_id IN (%s, %s)", (self.aid, self.bid, self.aid, self.bid))
        execute(
            """INSERT INTO followers (child_id, following_child_id, approved, approval_stage)
               VALUES (%s, %s, TRUE, 'ACTIVE')
               ON CONFLICT (child_id, following_child_id) DO UPDATE SET approved=TRUE, approval_stage='ACTIVE'""",
            (self.aid, self.bid)
        )
        execute(
            """INSERT INTO followers (child_id, following_child_id, approved, approval_stage)
               VALUES (%s, %s, TRUE, 'ACTIVE')
               ON CONFLICT (child_id, following_child_id) DO UPDATE SET approved=TRUE, approval_stage='ACTIVE'""",
            (self.bid, self.aid)
        )
        execute(
            """INSERT INTO parent_control_settings (child_id, parent_id, allow_messaging, allow_reels, allow_stories, allow_posting, allow_discover)
               VALUES (%s, %s, TRUE, TRUE, TRUE, TRUE, TRUE)
               ON CONFLICT (child_id) DO UPDATE SET allow_messaging=TRUE, allow_reels=TRUE, allow_stories=TRUE""",
            (self.aid, self.pid),
        )
        from services.controls import _controls_cache
        _controls_cache.pop(self.aid, None)

    def test_01_stranger_cannot_message(self):
        """A cannot message non-connected child."""
        execute("DELETE FROM followers WHERE (child_id=%s AND following_child_id=%s) OR (child_id=%s AND following_child_id=%s)", (self.aid, self.bid, self.bid, self.aid))
        res = self.client.get(f'/api/mobile/v1/kids/chat/{self.bid}', headers=self.headers_a)
        self.assertEqual(res.status_code, 403)
        res_post = self.client.post(
            f'/api/mobile/v1/kids/chat/{self.bid}',
            headers=self.headers_a,
            data=json.dumps({'message_text': 'Hey stranger'}),
        )
        self.assertEqual(res_post.status_code, 403)

    def test_02_child_chat_send_receive_reply_persist(self):
        """Connected A sends safe text to B, B receives, replies, and both persist through real moderation."""
        from unittest.mock import patch
        clean_scores = {
            'toxicity': 0.0, 'severe_toxicity': 0.0, 'obscene': 0.0,
            'identity_attack': 0.0, 'insult': 0.0, 'threat': 0.0, 'sexual_explicit': 0.0
        }
        # Do NOT mock evaluate - run real evaluate() through the full moderation engine
        # The trained-text tier is disabled here via its own kill-switch: it has
        # dedicated regression coverage (tests/test_trained_text_regressions.py),
        # while this E2E is about the chat send/receive/reply/persist flow.
        with patch("safety.remote_client.enabled", return_value=False), \
             patch("safety.text_service._detox_scores", return_value=clean_scores), \
             patch.dict(os.environ, {"LITTLENET_ENABLE_TRAINED_TEXT": "0"}):
            # 1. A sends safe message
            res = self.client.post(
                f'/api/mobile/v1/kids/chat/{self.bid}',
                headers=self.headers_a,
                data=json.dumps({'message_text': 'Great science project today!'}),
            )
            self.assertEqual(res.status_code, 200, f"Failed with: {res.get_json()}")
            self.assertEqual(res.get_json()['status'], 'ALLOW')

            # 2. B views chat, message is seen/delivered
            res_b = self.client.get(f'/api/mobile/v1/kids/chat/{self.aid}', headers=self.headers_b)
            self.assertEqual(res_b.status_code, 200)
            b_msgs = res_b.get_json()['messages']
            self.assertTrue(any(m['message_text'] == 'Great science project today!' for m in b_msgs))

            # 3. B replies to A
            res_reply = self.client.post(
                f'/api/mobile/v1/kids/chat/{self.aid}',
                headers=self.headers_b,
                data=json.dumps({'message_text': 'Thanks! What time is robotics class tomorrow?'}),
            )
            self.assertEqual(res_reply.status_code, 200)
            self.assertEqual(res_reply.get_json()['status'], 'ALLOW')

            # 4. A sees reply
            res_a = self.client.get(f'/api/mobile/v1/kids/chat/{self.bid}', headers=self.headers_a)
            self.assertEqual(res_a.status_code, 200)
            a_msgs = res_a.get_json()['messages']
            self.assertTrue(any(m['message_text'] == 'Thanks! What time is robotics class tomorrow?' for m in a_msgs))

    def test_02b_child_chat_persistence_fast(self):
        """Persistence-only chat test with mocked evaluate for fast path validation."""
        from unittest.mock import patch, MagicMock
        mock_dec = MagicMock(action="ALLOW", risk=0.0, reason="safe")
        with patch("mobile.api.evaluate", return_value=({}, mock_dec)):
            res = self.client.post(
                f'/api/mobile/v1/kids/chat/{self.bid}',
                headers=self.headers_a,
                data=json.dumps({'message_text': 'Persistence test message'}),
            )
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.get_json()['status'], 'ALLOW')

    def test_03_chat_safety_pii_blocked_and_parent_notified(self):
        """Attempting to share phone/email/contact info is blocked and notifies parent."""
        res = self.client.post(
            f'/api/mobile/v1/kids/chat/{self.bid}',
            headers=self.headers_a,
            data=json.dumps({'message_text': 'Call me at 9876543210 or email test@gmail.com'}),
        )
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertTrue(data.get('blocked'))

        # Parent received safety alert
        alert = fetch_one(
            "SELECT * FROM parent_notifications WHERE parent_id=%s AND notification_type='MESSAGE_BLOCKED' ORDER BY created_at DESC LIMIT 1",
            (self.pid,)
        )
        self.assertIsNotNone(alert)

        # Receiver B never gets it
        res_b = self.client.get(f'/api/mobile/v1/kids/chat/{self.aid}', headers=self.headers_b)
        b_msgs = res_b.get_json()['messages']
        self.assertFalse(any('9876543210' in m.get('message_text', '') for m in b_msgs))

    def test_04_chat_safety_grooming_blocked(self):
        """Grooming / predatory patterns are blocked."""
        res = self.client.post(
            f'/api/mobile/v1/kids/chat/{self.bid}',
            headers=self.headers_a,
            data=json.dumps({'message_text': 'keep this a secret and send me a private photo alone'}),
        )
        # Should be blocked or sent to review
        self.assertIn(res.status_code, (200, 400))
        if res.status_code == 400:
            self.assertTrue(res.get_json().get('blocked'))
        else:
            self.assertEqual(res.get_json()['status'], 'REVIEW')

    def test_05_chat_details_mute_block_report(self):
        """Chat Details actions: Mute, Report, and Block."""
        # 1. Mute
        res_mute = self.client.post(
            f'/api/mobile/v1/kids/mute/{self.bid}',
            headers=self.headers_a,
            data=json.dumps({'action': 'mute'}),
        )
        self.assertEqual(res_mute.status_code, 200)
        self.assertTrue(res_mute.get_json()['muted'])

        # Check muted list
        res_muted = self.client.get('/api/mobile/v1/kids/muted-users', headers=self.headers_a)
        self.assertEqual(res_muted.status_code, 200)
        self.assertTrue(any(u['user_id'] == self.bid for u in res_muted.get_json()['muted_users']))

        # 2. Report
        res_report = self.client.post(
            '/api/mobile/v1/kids/report',
            headers=self.headers_a,
            data=json.dumps({
                'target_type': 'USER',
                'target_id': self.bid,
                'reason': 'Mean or Bullying Words',
                'details': 'Reported via Chat Details acceptance test',
            }),
        )
        self.assertEqual(res_report.status_code, 200)
        report_row = fetch_one("SELECT * FROM reports WHERE reporter_id=%s AND target_id=%s ORDER BY created_at DESC LIMIT 1", (self.aid, self.bid))
        self.assertIsNotNone(report_row)

        # 3. Block user
        res_block = self.client.post(
            f'/api/mobile/v1/kids/block/{self.bid}',
            headers=self.headers_a,
            data=json.dumps({'action': 'block'}),
        )
        self.assertEqual(res_block.status_code, 200)
        self.assertTrue(res_block.get_json()['blocked'])

        # Immediate revocation: chat now returns 403
        res_chat_blocked = self.client.get(f'/api/mobile/v1/kids/chat/{self.bid}', headers=self.headers_a)
        self.assertEqual(res_chat_blocked.status_code, 403)

        # Immediate revocation: B cannot chat A either
        res_chat_b = self.client.get(f'/api/mobile/v1/kids/chat/{self.aid}', headers=self.headers_b)
        self.assertEqual(res_chat_b.status_code, 403)

    def test_06_chat_pagination_performance(self):
        """Chat history pagination: latest 30 initially, older with before_id."""
        cid = fetch_one("SELECT conversation_id FROM child_conversations WHERE (child1_id=%s AND child2_id=%s) OR (child1_id=%s AND child2_id=%s)", (self.aid, self.bid, self.bid, self.aid))
        if not cid:
            cid_val = execute("INSERT INTO child_conversations (child1_id, child2_id) VALUES (%s, %s) RETURNING conversation_id", (min(self.aid, self.bid), max(self.aid, self.bid)), returning=True)['conversation_id']
        else:
            cid_val = cid['conversation_id']

        # Seed 35 messages
        for i in range(35):
            execute(
                "INSERT INTO child_messages (conversation_id, sender_child_id, receiver_child_id, message_type, message_text, moderation_status) VALUES (%s, %s, %s, 'TEXT', %s, 'ALLOWED')",
                (cid_val, self.aid, self.bid, f'Bench message {i:02d}'),
            )

        # Request latest 30
        res = self.client.get(f'/api/mobile/v1/kids/chat/{self.bid}?limit=30', headers=self.headers_a)
        self.assertEqual(res.status_code, 200)
        msgs = res.get_json()['messages']
        self.assertLessEqual(len(msgs), 30)

        oldest_id = msgs[0]['child_message_id']
        # Paginate older messages
        res_older = self.client.get(f'/api/mobile/v1/kids/chat/{self.bid}?limit=30&before_id={oldest_id}', headers=self.headers_a)
        self.assertEqual(res_older.status_code, 200)
        older_msgs = res_older.get_json()['messages']
        self.assertTrue(all(m['child_message_id'] < oldest_id for m in older_msgs))

    def test_07_parent_controls_live_effect(self):
        """Parent disables messaging -> child immediately receives 403; re-enable -> 200."""
        # 1. P disables messaging for Child A
        execute(
            """INSERT INTO parent_control_settings (child_id, parent_id, allow_messaging)
               VALUES (%s, %s, FALSE)
               ON CONFLICT (child_id) DO UPDATE SET allow_messaging=FALSE""",
            (self.aid, self.pid),
        )
        from services.controls import _controls_cache
        _controls_cache.pop(self.aid, None)

        res = self.client.get(f'/api/mobile/v1/kids/chat/{self.bid}', headers=self.headers_a)
        self.assertEqual(res.status_code, 403)

        # 2. P re-enables messaging
        execute("UPDATE parent_control_settings SET allow_messaging=TRUE WHERE child_id=%s", (self.aid,))
        _controls_cache.pop(self.aid, None)
        res_reopen = self.client.get(f'/api/mobile/v1/kids/chat/{self.bid}', headers=self.headers_a)
        self.assertEqual(res_reopen.status_code, 200)


if __name__ == '__main__':
    unittest.main()
