import json
import os
import urllib.error
import urllib.request


EXPECTED_RESEND_FROM_EMAIL = 'no-reply@littlenet.in'
EXPECTED_RESEND_FROM_NAME = 'LittleNet'
EXPECTED_RESEND_DOMAIN = 'littlenet.in'
RESEND_API_BASE = 'https://api.resend.com'


def _email_type_for_subject(subject: str) -> str:
    subject_l = str(subject or '').lower()
    if 'parent verification code' in subject_l:
        return 'PARENT_OTP'
    if 'password reset' in subject_l:
        return 'PASSWORD_RESET'
    if 'safety' in subject_l:
        return 'SAFETY_NOTICE'
    return 'TRANSACTIONAL'


def _record_provider_acceptance(provider_message_id: str | None, receiver: str, subject: str) -> None:
    """Record provider acceptance without logging OTP bodies or secrets."""
    if not provider_message_id:
        return
    try:
        from database.connection import execute
        execute(
            """
            INSERT INTO email_delivery_events(
                provider_message_id, recipient, provider, email_type, status,
                created_at, updated_at, last_event_at
            )
            VALUES(%s,%s,'RESEND',%s,'ACCEPTED',NOW(),NOW(),NOW())
            ON CONFLICT(provider_message_id) DO UPDATE SET
                recipient=EXCLUDED.recipient,
                email_type=EXCLUDED.email_type,
                status='ACCEPTED',
                updated_at=NOW(),
                last_event_at=NOW()
            """,
            (provider_message_id, str(receiver).strip().lower(), _email_type_for_subject(subject)),
        )
    except Exception as exc:
        print(f'[RESEND WARNING] Delivery-state recording failed: {type(exc).__name__}.')


def _resend_from_email() -> str:
    """Return the configured LittleNet-owned Resend sender address."""
    return (
        os.getenv('LITTLENET_RESEND_FROM_EMAIL')
        or os.getenv('RESEND_FROM_EMAIL')
        or ''
    ).strip()


def _is_sandbox_sender(from_email: str) -> bool:
    return not from_email or from_email.lower().endswith('@resend.dev')


def validate_resend_production():
    """Validate the live Resend contract without sending an email.

    The domains endpoint authenticates the API key and reports the verification
    state of the LittleNet-owned domain. This deliberately does not send a
    message, so a release preflight cannot create a demo OTP or claim delivery
    based on a sandbox sender.
    """
    api_key = (os.getenv('RESEND_API_KEY') or '').strip()
    from_email = _resend_from_email().lower()
    result = {
        'ok': False,
        'configured': bool(api_key),
        'provider': 'resend' if api_key else None,
        'mail_mode': 'not_configured',
        'from_email': from_email or None,
        'domain': EXPECTED_RESEND_DOMAIN,
        'domain_status': None,
        'authentication': False,
        'webhook_configured': bool((os.getenv('RESEND_WEBHOOK_SECRET') or '').strip()),
        'is_production_ready': False,
    }

    if not api_key:
        result['error'] = 'RESEND_API_KEY is not configured.'
        return result
    if from_email != EXPECTED_RESEND_FROM_EMAIL:
        result['error'] = (
            'RESEND_FROM_EMAIL must be exactly '
            f'{EXPECTED_RESEND_FROM_EMAIL} for the LittleNet release.'
        )
        return result

    request = urllib.request.Request(
        f'{RESEND_API_BASE}/domains',
        headers={
            'Authorization': f'Bearer {api_key}',
            'Accept': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) LittleNet/1.0',
        },
        method='GET',
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            if response.status != 200:
                result['error'] = f'Resend domain check returned HTTP {response.status}.'
                return result
            payload = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        result['error'] = (
            'Resend authentication was rejected; refresh RESEND_API_KEY '
            f'(HTTP {exc.code}).'
            if exc.code in (401, 403)
            else f'Resend domain check failed with HTTP {exc.code}.'
        )
        return result
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        result['error'] = f'Resend domain check could not connect ({type(exc).__name__}).'
        return result
    except (ValueError, TypeError, AttributeError):
        result['error'] = 'Resend domain check returned an invalid response.'
        return result

    result['authentication'] = True
    domains = payload.get('data', []) if isinstance(payload, dict) else []
    if not isinstance(domains, list):
        result['error'] = 'Resend domain check returned an invalid domain list.'
        return result

    matching_domain = next(
        (
            domain for domain in domains
            if isinstance(domain, dict)
            and str(domain.get('name', '')).strip().lower() == EXPECTED_RESEND_DOMAIN
        ),
        None,
    )
    if matching_domain is None:
        result['error'] = (
            f'Resend domain {EXPECTED_RESEND_DOMAIN} is not configured for this API key.'
        )
        return result

    domain_status = str(matching_domain.get('status', '')).strip().lower()
    result['domain_status'] = domain_status or None
    if domain_status != 'verified':
        result['error'] = (
            f'Resend domain {EXPECTED_RESEND_DOMAIN} is not verified '
            f'(status: {domain_status or "unknown"}).'
        )
        return result

    if not result['webhook_configured']:
        result['error'] = (
            'RESEND_WEBHOOK_SECRET is required so LittleNet can distinguish '
            'provider acceptance from delivered, bounced, failed, or suppressed email.'
        )
        return result

    result.update({
        'ok': True,
        'mail_mode': 'resend_verified',
        'is_production_ready': True,
    })
    return result


def _send_via_resend(api_key, receiver, subject, body, from_email=None, from_name=None):
    """Deliver an HTML email through Resend without provider fallbacks.

    LittleNet uses this path for parent OTPs and safety notifications. A
    sandbox sender, SMTP fallback, or demo success would make an OTP appear
    deliverable when it is not, so every failure is explicit and fail-closed.
    """
    configured_from = (from_email or _resend_from_email()).strip()
    if _is_sandbox_sender(configured_from):
        print('[RESEND CONFIG ERROR] RESEND_FROM_EMAIL must be a verified LittleNet sender.')
        return False

    sender_name = from_name or os.getenv('RESEND_FROM_NAME') or 'LittleNet Safety'
    payload = {
        'from': f'{sender_name} <{configured_from}>',
        'to': [receiver],
        'subject': subject,
        'html': body,
    }
    request = urllib.request.Request(
        'https://api.resend.com/emails',
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) LittleNet/1.0',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            if response.status in (200, 201):
                provider_message_id = None
                try:
                    response_payload = json.loads(response.read().decode('utf-8'))
                    if isinstance(response_payload, dict):
                        provider_message_id = str(response_payload.get('id') or '').strip() or None
                except (ValueError, TypeError, UnicodeDecodeError, AttributeError):
                    provider_message_id = None
                _record_provider_acceptance(provider_message_id, receiver, subject)
                return True
            print(f'[RESEND WARNING] Unexpected status {response.status}.')
    except urllib.error.HTTPError as exc:
        # Provider responses can echo credentials or message content. Keep
        # delivery logs limited to a status code.
        print(f'[RESEND WARNING] Delivery failed: HTTP {exc.code}.')
    except Exception as exc:
        print(f'[RESEND WARNING] Delivery failed: {type(exc).__name__}.')
    return False


def get_mail_status():
    """Report whether the strict Resend production contract is configured."""
    resend_key = bool(os.getenv('RESEND_API_KEY'))
    from_email = _resend_from_email().lower()
    sender_is_production = bool(from_email) and not _is_sandbox_sender(from_email)
    configured = resend_key and sender_is_production
    return {
        'ok': configured,
        'configured': configured,
        'provider': 'resend' if resend_key else None,
        'mail_mode': 'resend_verified' if configured else 'not_configured',
        'from_email': from_email or None,
        'is_production_ready': configured,
    }


def send_email(receiver, subject, body):
    """Send transactional email through the verified Resend production sender."""
    resend_key = os.getenv('RESEND_API_KEY')
    if not resend_key:
        print('[RESEND CONFIG ERROR] RESEND_API_KEY is not configured.')
        return False
    return _send_via_resend(resend_key, receiver, subject, body)


def send_parent_otp_email(receiver, subject, body):
    """Send a parent OTP with the identity locked to the verified LittleNet sender.

    Parent verification is a release-critical path. It must not inherit a
    missing, sandbox, or unrelated RESEND_FROM_NAME/RESEND_FROM_EMAIL value
    from the deployment environment.
    """
    resend_key = os.getenv('RESEND_API_KEY')
    if not resend_key:
        print('[RESEND CONFIG ERROR] RESEND_API_KEY is not configured.')
        return False
    custom = _resend_from_email()
    from_email = (
        custom
        if (custom and not _is_sandbox_sender(custom) and not custom.endswith('.example'))
        else EXPECTED_RESEND_FROM_EMAIL
    )
    from_name = (
        os.getenv('RESEND_FROM_NAME')
        if (custom and not _is_sandbox_sender(custom) and not custom.endswith('.example'))
        else None
    ) or EXPECTED_RESEND_FROM_NAME
    return _send_via_resend(
        resend_key,
        receiver,
        subject,
        body,
        from_email=from_email,
        from_name=from_name,
    )
