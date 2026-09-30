"""Never let a local full-suite run inherit the production DATABASE_URL."""
import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

fixture = Path(__file__).resolve().parents[1] / '.env.disposable'
explicit = os.getenv('DISPOSABLE_DATABASE_URL') or (dotenv_values(fixture).get('DATABASE_URL') if fixture.exists() else None)
current = os.getenv('DATABASE_URL', '')
local = urlsplit(current).hostname in {'localhost', '127.0.0.1', '::1'}
if explicit:
    os.environ['DATABASE_URL'] = explicit
    os.environ['DISPOSABLE_DATABASE_URL'] = explicit
elif local:
    os.environ['DISPOSABLE_DATABASE_URL'] = current
elif not local:
    # Mock-only tests work without PostgreSQL. Database integration requires
    # explicit disposable configuration or the localhost CI service.
    os.environ['DATABASE_URL'] = 'postgresql://invalid:invalid@127.0.0.1:1/invalid?connect_timeout=1'

# A database clone must not send real email or touch production media/models.
for key in ('RESEND_API_KEY', 'SMTP_HOST', 'AI_SERVICE_URL', 'POSTHOG_API_KEY', 'K2_HORIZON_API_KEY',
            'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_BUCKET'):
    os.environ[key] = ''
for key in ('LITTLENET_USE_MODAL_IMAGE_CPU', 'LITTLENET_USE_MODAL_TEXT_CPU',
            'LITTLENET_ALLOW_IMAGE_GPU_FALLBACK', 'LITTLENET_ALLOW_TEXT_GPU_FALLBACK'):
    os.environ[key] = '0'
