import time
import threading
from typing import Optional

class CircuitBreakerOpenException(Exception):
    """Raised when request is attempted while circuit breaker is OPEN."""
    pass

class CircuitBreaker:
    """Thread-safe circuit breaker pattern to prevent cascading failures."""
    def __init__(self, *args, failure_threshold: int = 5, reset_timeout: float = 60.0, **kwargs):
        # Handle optional positional name: CircuitBreaker("service_name", failure_threshold=...)
        if args and isinstance(args[0], str):
            self.name = args[0]
            if len(args) > 1 and isinstance(args[1], int):
                failure_threshold = args[1]
            if len(args) > 2 and isinstance(args[2], (int, float)):
                reset_timeout = float(args[2])
        else:
            self.name = kwargs.get("name", "ai_service")

        self.failure_threshold = kwargs.get("failure_threshold", failure_threshold)
        self.reset_timeout = kwargs.get("reset_timeout_seconds", kwargs.get("reset_timeout", reset_timeout))
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self._lock = threading.Lock()

    def allow_request(self) -> bool:
        with self._lock:
            now = time.time()
            if self.state == "OPEN":
                if now - self.last_failure_time > self.reset_timeout:
                    self.state = "HALF_OPEN"
                    return True
                return False
            return True

    def can_execute(self) -> bool:
        return self.allow_request()

    def record_success(self):
        with self._lock:
            self.failure_count = 0
            self.state = "CLOSED"

    def record_failure(self):
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"

    def get_status(self) -> dict:
        with self._lock:
            return {
                "name": self.name,
                "state": self.state,
                "failure_count": self.failure_count,
                "last_failure_time": self.last_failure_time
            }

    def __enter__(self):
        if not self.allow_request():
            raise CircuitBreakerOpenException(f"Circuit breaker '{self.name}' is OPEN")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.record_failure()
        else:
            self.record_success()
        return False
