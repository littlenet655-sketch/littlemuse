import os
import random
import pytest
from unittest.mock import patch
from database.connection import execute

from app import app
from mobile.api import _issue_pending_parent


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_parent_resend_email_contracts(client):
    if not os.environ.get('DATABASE_URL'):
        pytest.skip('No DATABASE_URL configured')
    uid = random.randint(900000, 999999)
    email = 'parent_' + str(uid) + '@example.com'
    execute(
        'INSERT INTO users (user_id, role, account_status, email, username, full_name, password_hash) VALUES (%s, %s, %s, %s, %s, %s, %s)',
        (uid, 'PARENT', 'PENDING_APPROVAL', email, 'parent_' + str(uid), 'Parent Tester', 'hash_dummy')
    )
    execute(
        "INSERT INTO parent_email_otps (user_id, code_hash, sent_at, expires_at, attempts) VALUES (%s, %s, NOW(), NOW() + INTERVAL '15 minutes', 0)",
        (uid, 'dummy_hash')
    )

    pending_token = _issue_pending_parent(uid, email)

    # 1. Cooldown test: 429
    res = client.post('/api/mobile/v1/auth/parent/resend-email', json={'pending_token': pending_token})
    assert res.status_code == 429


    # 2. Reset cooldown in DB, mock email success and test 200
    execute("UPDATE parent_email_otps SET sent_at = NOW() - INTERVAL '120 seconds' WHERE user_id = %s", (uid,))
    with patch('auth.parent_email_otp._send_code', return_value=True):
        res = client.post('/api/mobile/v1/auth/parent/resend-email', json={'pending_token': pending_token})
    assert res.status_code == 200
    assert res.get_json().get('ok') is True


    # 3. Test mail transport failure returns 503
    execute("UPDATE parent_email_otps SET sent_at = NOW() - INTERVAL '120 seconds' WHERE user_id = %s", (uid,))
    with patch('auth.parent_email_otp._send_code', return_value=False):
        res = client.post('/api/mobile/v1/auth/parent/resend-email', json={'pending_token': pending_token})
    assert res.status_code == 503


    # 4. Already verified: 409
    execute("UPDATE parent_email_otps SET verified_at = NOW() WHERE user_id = %s", (uid,))
    execute("UPDATE users SET account_status = 'ACTIVE' WHERE user_id = %s", (uid,))
    res = client.post('/api/mobile/v1/auth/parent/resend-email', json={'pending_token': pending_token})
    assert res.status_code == 409


    # 5. Unknown/No pending user: 404
    uid_fake = random.randint(800000, 899999)
    fake_token = _issue_pending_parent(uid_fake, 'fake@example.com')
    res = client.post('/api/mobile/v1/auth/parent/resend-email', json={'pending_token': fake_token})
    assert res.status_code == 404
