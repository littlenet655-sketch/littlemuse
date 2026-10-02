import os
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

csrf = CSRFProtect()
storage_uri = os.getenv("LIMITER_STORAGE_URI") or os.getenv("REDIS_URL") or "memory://"
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["300 per hour"],
    storage_uri=storage_uri,
)
