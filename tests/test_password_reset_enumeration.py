import time
import statistics
import pytest
import bcrypt
from auth.password_reset import (
    request_password_reset,
    verify_and_reset_password_by_token,
    check_ip_reset_rate_limit,
    reap_expired_reset_transactions,
    process_password_reset_email_outbox,
    UNIFORM_RESET_MESSAGE,
    OTP_MAX_ATTEMPTS,
)
from database.connection import execute, fetch_one

@pytest.fixture(scope='module')
def setup_users():
    prefix = 'enum_test_v5_'
    execute('DELETE FROM users WHERE username LIKE %s OR email LIKE %s', (prefix + '%', prefix + '%'))
    execute('DELETE FROM password_reset_transactions WHERE request_ip LIKE %s', ('198.51.100.%',))
    execute('DELETE FROM password_reset_email_outbox WHERE recipient LIKE %s', (prefix + '%',))
    p_hash = bcrypt.hashpw(b'SafeEnumPass123!', bcrypt.gensalt()).decode('utf-8')
    existing = []
    for i in range(30):
        uname = f'{prefix}user_{i:02d}'
        email = f'{prefix}user_{i:02d}' + '@example.test'
        execute(
            'INSERT INTO users(username, full_name, email, password_hash, role, account_status) VALUES(%s, %s, %s, %s, %s, %s)',
            (uname, 'Enum User', email, p_hash, 'PARENT', 'ACTIVE'),
        )
        existing.append({'username': uname, 'email': email})
    unknown = [f'{prefix}ghost_{i:02d}' for i in range(30)]
    yield existing, unknown
    execute('DELETE FROM users WHERE username LIKE %s OR email LIKE %s', (prefix + '%', prefix + '%'))
    execute('DELETE FROM password_reset_transactions WHERE request_ip LIKE %s', ('198.51.100.%',))
    execute('DELETE FROM password_reset_email_outbox WHERE recipient LIKE %s', (prefix + '%',))

def test_payload_uniformity(setup_users):
    existing, unknown = setup_users
    for i, u in enumerate(existing):
        ok, msg, det = request_password_reset(u['email'], request_ip=f'198.51.100.{100+i}')
        assert ok is True
        assert msg == UNIFORM_RESET_MESSAGE
        assert isinstance(det, dict)
        assert det['reset_token'].startswith('prt_')
        assert len(det['reset_token']) >= 32
    for i, unk in enumerate(unknown):
        ok, msg, det = request_password_reset(unk, request_ip=f'198.51.100.{150+i}')
        assert ok is True
        assert msg == UNIFORM_RESET_MESSAGE
        assert isinstance(det, dict)
        assert det['reset_token'].startswith('prt_')
        assert len(det['reset_token']) >= 32
        assert det.get('is_decoy') is True

def test_oracle_indistinguishability(setup_users):
    existing, unknown = setup_users
    ok1, _, det1 = request_password_reset(existing[0]['email'], request_ip='198.51.100.10')
    real_tok = det1['reset_token']
    ok2, _, det2 = request_password_reset(unknown[0], request_ip='198.51.100.11')
    decoy_tok = det2['reset_token']
    for attempt in range(1, OTP_MAX_ATTEMPTS + 1):
        ok_r, msg_r = verify_and_reset_password_by_token(real_tok, '000000', 'NewValidPass123!')
        ok_d, msg_d = verify_and_reset_password_by_token(decoy_tok, '000000', 'NewValidPass123!')
        assert ok_r is False and ok_d is False
        assert msg_r == msg_d
    ok_r, msg_r = verify_and_reset_password_by_token(real_tok, '000000', 'NewValidPass123!')
    ok_d, msg_d = verify_and_reset_password_by_token(decoy_tok, '000000', 'NewValidPass123!')
    assert ok_r is False and ok_d is False
    assert 'Too many incorrect attempts' in msg_r
    assert msg_r == msg_d

def test_timing_distribution(setup_users):
    existing, unknown = setup_users
    request_password_reset(existing[0]['email'], request_ip='198.51.100.20')
    request_password_reset(unknown[0], request_ip='198.51.100.21')
    exist_times = []
    for i in range(1, 30):
        t0 = time.perf_counter()
        request_password_reset(existing[i]['email'], request_ip='198.51.100.30')
        t1 = time.perf_counter()
        exist_times.append((t1 - t0) * 1000)
    unk_times = []
    for i in range(1, 30):
        t0 = time.perf_counter()
        request_password_reset(unknown[i], request_ip='198.51.100.40')
        t1 = time.perf_counter()
        unk_times.append((t1 - t0) * 1000)
    med_exist = statistics.median(exist_times)
    med_unk = statistics.median(unk_times)
    delta_ms = abs(med_exist - med_unk)
    assert delta_ms < 150.0, f'Timing delta too large: {delta_ms:.2f}ms'

def test_ip_rate_limiting_and_reaper():
    test_ip = '198.51.100.250'
    execute('DELETE FROM password_reset_transactions WHERE request_ip = %s', (test_ip,))
    for _ in range(5):
        assert check_ip_reset_rate_limit(test_ip, max_per_window=5, window_minutes=15) is True
        request_password_reset('rate_limit_test', request_ip=test_ip)
    assert check_ip_reset_rate_limit(test_ip, max_per_window=5, window_minutes=15) is False
    reaped = reap_expired_reset_transactions()
    assert isinstance(reaped, int)

def test_durable_outbox_processing(monkeypatch, setup_users):
    monkeypatch.setattr('auth.password_reset.send_email', lambda *a, **k: True)
    existing, _ = setup_users
    ok, _, det = request_password_reset(existing[5]['email'], request_ip='198.51.100.222')
    assert ok is True
    row = fetch_one('SELECT outbox_id, completed_at FROM password_reset_email_outbox WHERE recipient = %s', (existing[5]['email'],))
    assert row is not None
    assert row['completed_at'] is None
    sent = process_password_reset_email_outbox(batch_size=10)
    assert sent >= 1
    row_after = fetch_one('SELECT completed_at FROM password_reset_email_outbox WHERE recipient = %s', (existing[5]['email'],))
    assert row_after['completed_at'] is not None
