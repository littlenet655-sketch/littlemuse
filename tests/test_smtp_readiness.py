import io
import json
import os
import urllib.error
from unittest.mock import MagicMock, patch

from mailg.send_email import (
    get_mail_status,
    send_email,
    send_parent_otp_email,
    validate_resend_production,
)


def test_send_email_fails_closed_when_resend_credentials_are_absent():
    with patch.dict(os.environ, {}, clear=True):
        assert send_email('test@example.com', 'Test Subject', '<h1>Hello</h1>') is False
        assert get_mail_status()['is_production_ready'] is False


def test_send_email_resend_delivery_success():
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__.return_value = mock_resp

    with patch.dict(os.environ, {
        'RESEND_API_KEY': 're_test_key_123',
        'RESEND_FROM_EMAIL': 'no-reply@littlenet.in',
        'RESEND_FROM_NAME': 'LittleNet Safety',
    }, clear=True):
        with patch('urllib.request.urlopen', return_value=mock_resp) as mock_urlopen:
            assert send_email('parent@example.com', 'Your OTP Code', '<p>Code: 123456</p>') is True
            req = mock_urlopen.call_args[0][0]
            assert req.full_url == 'https://api.resend.com/emails'
            assert req.headers.get('Authorization') == 'Bearer re_test_key_123'
            payload = json.loads(req.data.decode('utf-8'))
            assert payload['to'] == ['parent@example.com']
            assert payload['subject'] == 'Your OTP Code'
            assert payload['from'] == 'LittleNet Safety <no-reply@littlenet.in>'
            assert get_mail_status()['is_production_ready'] is True


def test_send_email_rejects_resend_sandbox_sender_without_fallback():
    with patch.dict(os.environ, {
        'RESEND_API_KEY': 're_test_key_123',
        'RESEND_FROM_EMAIL': 'onboarding@resend.dev',
    }, clear=True):
        with patch('urllib.request.urlopen') as mock_urlopen:
            assert send_email('parent@example.com', 'Your OTP Code', '<p>Code: 999999</p>') is False
            mock_urlopen.assert_not_called()
            assert get_mail_status()['is_production_ready'] is False


def test_parent_otp_uses_locked_littlenet_sender_identity():
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__.return_value = mock_resp

    with patch.dict(os.environ, {
        'RESEND_API_KEY': 'test-key',
        'RESEND_FROM_EMAIL': 'onboarding@resend.dev',
        'LITTLENET_RESEND_FROM_EMAIL': 'sender@unverified.example',
        'RESEND_FROM_NAME': 'Untrusted Environment Name',
    }, clear=True):
        with patch('urllib.request.urlopen', return_value=mock_resp) as mock_urlopen:
            assert send_parent_otp_email(
                'parent@example.com',
                'LittleNet parent verification',
                '<p>Your one-time verification code is protected.</p>',
            ) is True

    payload = json.loads(mock_urlopen.call_args[0][0].data.decode('utf-8'))
    assert payload['from'] == 'LittleNet <no-reply@littlenet.in>'
    assert payload['to'] == ['parent@example.com']
    assert 'onboarding@resend.dev' not in payload['from']
    assert 'sender@unverified.example' not in payload['from']
    assert 'Untrusted Environment Name' not in payload['from']


def test_send_email_resend_failure_does_not_fallback():
    err_stream = io.BytesIO(b'{"statusCode":400,"message":"The associated domain is not verified."}')
    http_err = urllib.error.HTTPError(
        url='https://api.resend.com/emails',
        code=400,
        msg='Bad Request',
        hdrs={},
        fp=err_stream,
    )
    with patch.dict(os.environ, {
        'RESEND_API_KEY': 're_test_key_123',
        'RESEND_FROM_EMAIL': 'no-reply@littlenet.in',
        'SMTP_USER': 'fallback@example.com',
        'SMTP_PASSWORD': 'should-not-be-used',
    }, clear=True):
        with patch('urllib.request.urlopen', side_effect=http_err) as mock_urlopen:
            assert send_email('parent@example.com', 'Your OTP Code', '<p>Code: 123456</p>') is False
            assert mock_urlopen.call_count == 1


def test_resend_failure_log_does_not_include_provider_response_body(capsys):
    error = urllib.error.HTTPError(
        url='https://api.resend.com/emails',
        code=400,
        msg='Bad Request',
        hdrs={},
        fp=io.BytesIO(b'provider response must not be logged'),
    )
    with patch.dict(os.environ, {
        'RESEND_API_KEY': 'test-key',
        'RESEND_FROM_EMAIL': 'no-reply@littlenet.in',
    }, clear=True):
        with patch('urllib.request.urlopen', side_effect=error):
            assert send_email('parent@example.com', 'Parent verification', '<p>body</p>') is False

    assert 'provider response must not be logged' not in capsys.readouterr().out


def test_resend_preflight_authenticates_and_checks_verified_littlenet_domain():
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.read.return_value = json.dumps({
        'data': [
            {'name': 'other.example', 'status': 'verified'},
            {'name': 'littlenet.in', 'status': 'verified'},
        ],
    }).encode('utf-8')

    with patch.dict(os.environ, {
        'RESEND_API_KEY': 're_test_key_123',
        'RESEND_FROM_EMAIL': 'no-reply@littlenet.in',
        'RESEND_WEBHOOK_SECRET': 'unit' + '-test-webhook-enabled',
    }, clear=True):
        with patch('urllib.request.urlopen', return_value=mock_resp) as mock_urlopen:
            result = validate_resend_production()

    assert result['ok'] is True
    assert result['authentication'] is True
    assert result['domain_status'] == 'verified'
    request = mock_urlopen.call_args[0][0]
    assert request.full_url == 'https://api.resend.com/domains'
    assert request.headers.get('Authorization') == 'Bearer re_test_key_123'



def test_resend_preflight_requires_delivery_webhook_secret():
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.read.return_value = json.dumps({
        'data': [{'name': 'littlenet.in', 'status': 'verified'}],
    }).encode('utf-8')

    with patch.dict(os.environ, {
        'RESEND_API_KEY': 're_test_key_123',
        'RESEND_FROM_EMAIL': 'no-reply@littlenet.in',
    }, clear=True):
        with patch('urllib.request.urlopen', return_value=mock_resp):
            result = validate_resend_production()

    assert result['ok'] is False
    assert result['authentication'] is True
    assert result['domain_status'] == 'verified'
    assert result['webhook_configured'] is False
    assert 'RESEND_WEBHOOK_SECRET' in result['error']


def test_resend_preflight_rejects_api_key_without_printing_it():
    error = urllib.error.HTTPError(
        url='https://api.resend.com/domains',
        code=401,
        msg='Unauthorized',
        hdrs={},
        fp=io.BytesIO(b'bad key re_test_key_123'),
    )
    with patch.dict(os.environ, {
        'RESEND_API_KEY': 're_test_key_123',
        'RESEND_FROM_EMAIL': 'no-reply@littlenet.in',
    }, clear=True):
        with patch('urllib.request.urlopen', side_effect=error):
            result = validate_resend_production()

    assert result['ok'] is False
    assert result['authentication'] is False
    assert 'refresh RESEND_API_KEY' in result['error']
    assert 're_test_key_123' not in str(result)


def test_resend_preflight_rejects_sender_mismatch_without_calling_provider():
    with patch.dict(os.environ, {
        'RESEND_API_KEY': 're_test_key_123',
        'RESEND_FROM_EMAIL': 'no-reply@other.example',
    }, clear=True):
        with patch('urllib.request.urlopen') as mock_urlopen:
            result = validate_resend_production()

    assert result['ok'] is False
    assert 'no-reply@littlenet.in' in result['error']
    mock_urlopen.assert_not_called()


def test_resend_preflight_rejects_unverified_littlenet_domain():
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.read.return_value = json.dumps({
        'data': [{'name': 'littlenet.in', 'status': 'pending'}],
    }).encode('utf-8')

    with patch.dict(os.environ, {
        'RESEND_API_KEY': 're_test_key_123',
        'RESEND_FROM_EMAIL': 'no-reply@littlenet.in',
    }, clear=True):
        with patch('urllib.request.urlopen', return_value=mock_resp):
            result = validate_resend_production()

    assert result['ok'] is False
    assert result['authentication'] is True
    assert 'not verified' in result['error']
