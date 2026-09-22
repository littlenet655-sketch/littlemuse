import os
import secrets
from datetime import timedelta
from dotenv import load_dotenv
load_dotenv()


class Config:
    BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:5000").strip().rstrip("/")
    _ENVIRONMENT = os.getenv("LITTLENET_ENV", "").strip().lower()
    _PRODUCTION = _ENVIRONMENT in {"production", "prod"} or BASE_URL.startswith("https://")
    if _PRODUCTION and (
        not BASE_URL.startswith("https://")
        or "localhost" in BASE_URL.lower()
        or "127.0.0.1" in BASE_URL
        or "placeholder.invalid" in BASE_URL.lower()
    ):
        raise RuntimeError("Production BASE_URL must be an explicit public HTTPS URL")
    ENABLE_DEV_OTP = os.getenv("ENABLE_DEV_OTP", "0").strip().lower() in {"1", "true", "yes", "on"}
    if _PRODUCTION and ENABLE_DEV_OTP:
        raise RuntimeError("ENABLE_DEV_OTP must never be enabled in production")

    # Never use a publicly known Flask signing key. Local development may use an
    # ephemeral key, but any HTTPS deployment must provide a stable secret.
    _SECRET_ENV = (os.getenv("SECRET_KEY") or "").strip()
    if _PRODUCTION and (not _SECRET_ENV or _SECRET_ENV == "change-me-before-demo" or len(_SECRET_ENV) < 32):
        raise RuntimeError("Production SECRET_KEY must be explicitly configured with at least 32 random characters")
    SECRET_KEY = _SECRET_ENV or secrets.token_urlsafe(48)

    _DATABASE_ENV = (os.getenv("DATABASE_URL") or "").strip()
    if _PRODUCTION and not _DATABASE_ENV:
        raise RuntimeError("Production DATABASE_URL must be explicitly configured")
    DATABASE_URL = _DATABASE_ENV or "postgresql://postgres:littlenet@localhost:5432/safeconnect_db"

    MAX_CONTENT_LENGTH = 100 * 1024 * 1024
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("COOKIE_SECURE", "1" if _PRODUCTION else "0") == "1"
    WTF_CSRF_SSL_STRICT = False
    WTF_CSRF_TIME_LIMIT = None
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    ADULT_HARD_BLOCK_THRESHOLD = min(float(os.getenv("ADULT_HARD_BLOCK_THRESHOLD", "0.40")), 0.40)
    REEL_MAX_SECONDS = int(os.getenv("REEL_MAX_SECONDS", "180"))
    STORY_MAX_SECONDS = int(os.getenv("STORY_MAX_SECONDS", "60"))
    VIDEO_MAX_SECONDS = int(os.getenv("VIDEO_MAX_SECONDS", "600"))
    MESSAGE_MEDIA_MAX_MB = int(os.getenv("MESSAGE_MEDIA_MAX_MB", "40"))
    APP_TIMEZONE = os.getenv("APP_TIMEZONE", "Asia/Kolkata")

    AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "").strip()
    AI_SHARED_SECRET = os.getenv("AI_SHARED_SECRET", "").strip()
