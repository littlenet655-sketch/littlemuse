import threading
import os
import time
from collections import Counter
from dotenv import load_dotenv
load_dotenv()

_pool = None
_pool_lock = threading.Lock()
_validation_lock = threading.Lock()
_validation_cache = {}
_pool_metrics = Counter()
_pool_metric_seconds = Counter()
_VALIDATION_INTERVAL_SECONDS = max(
    0.0, float(os.getenv("DB_POOL_VALIDATION_INTERVAL_SECONDS", "30"))
)


def _metric(name, elapsed=None, amount=1):
    with _validation_lock:
        _pool_metrics[name] += amount
        if elapsed is not None:
            _pool_metric_seconds[name] += elapsed


def pool_metrics_snapshot():
    """Return connection-pool timing counters without query parameters or secrets."""
    with _validation_lock:
        counts = dict(_pool_metrics)
        seconds = dict(_pool_metric_seconds)
    return {
        "counts": counts,
        "seconds": seconds,
        "validation_interval_seconds": _VALIDATION_INTERVAL_SECONDS,
    }


def reset_pool_metrics():
    """Reset disposable/test diagnostics and cached validation state."""
    with _validation_lock:
        _pool_metrics.clear()
        _pool_metric_seconds.clear()
        _validation_cache.clear()


def _validation_is_recent(raw_conn):
    if _VALIDATION_INTERVAL_SECONDS <= 0:
        return False
    with _validation_lock:
        entry = _validation_cache.get(id(raw_conn))
        if not entry or entry[0] is not raw_conn:
            return False
        return time.monotonic() - entry[1] < _VALIDATION_INTERVAL_SECONDS


def _remember_validation(raw_conn):
    with _validation_lock:
        _validation_cache[id(raw_conn)] = (raw_conn, time.monotonic())


def _forget_validation(raw_conn):
    with _validation_lock:
        entry = _validation_cache.get(id(raw_conn))
        if entry and entry[0] is raw_conn:
            _validation_cache.pop(id(raw_conn), None)


def _database_url():
    # Config enforces explicit DATABASE_URL for HTTPS/production deployments.
    from config import Config
    return Config.DATABASE_URL


def _database_timezone() -> str:
    """Return a validated IANA timezone for every PostgreSQL session.

    Screen-time accounting uses CURRENT_DATE/NOW() in SQL while quiet hours use
    APP_TIMEZONE in Python. Setting the DB session timezone centrally keeps both
    policies on the same local day boundary instead of silently using the
    provider's default (commonly UTC).
    """
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    raw = (os.getenv("APP_TIMEZONE") or "Asia/Kolkata").strip() or "Asia/Kolkata"
    try:
        ZoneInfo(raw)
    except (ZoneInfoNotFoundError, ValueError):
        return "UTC"
    return raw


def _connect_kwargs() -> dict:
    return {
        "cursor_factory": __import__("psycopg2.extras", fromlist=["RealDictCursor"]).RealDictCursor,
        "options": f"-c timezone={_database_timezone()}",
    }


def _get_pool():
    global _pool
    if _pool is None or _pool.closed:
        with _pool_lock:
            if _pool is None or _pool.closed:
                try:
                    from psycopg2.pool import ThreadedConnectionPool
                    from psycopg2.extras import RealDictCursor
                except ImportError as exc:
                    raise RuntimeError('psycopg2 is required. Install requirements-core.txt') from exc
                started = time.monotonic()
                minconn = max(1, int(os.getenv("DB_POOL_MIN_CONNECTIONS", "2")))
                maxconn = max(minconn, int(os.getenv("DB_POOL_MAX_CONNECTIONS", "20")))
                _pool = ThreadedConnectionPool(minconn, maxconn, _database_url(), cursor_factory=RealDictCursor, options=f"-c timezone={_database_timezone()}")
                _metric("pool_creations", time.monotonic() - started)
                _metric("connection_creations", amount=minconn)
    return _pool


def _discard_connection(pool, conn):
    _forget_validation(conn)
    try:pool.putconn(conn, close=True)
    except Exception:
        try:conn.close()
        except Exception:pass
    _metric("connection_discards")


def _connection_is_usable(conn):
    if conn.closed:return False
    try:
        started = time.monotonic()
        conn.rollback()
        with conn.cursor() as cur:cur.execute('SELECT 1')
        conn.rollback()
        _metric("validation_selects", time.monotonic() - started)
        _remember_validation(conn)
        return True
    except Exception:
        _metric("validation_failures")
        return False


class PooledConnectionWrapper:
    def __init__(self, pool, conn):self._pool=pool;self._conn=conn;self._closed=False
    def close(self):
        if self._closed:return
        self._closed=True
        if not self._pool or self._pool.closed:
            try:self._conn.close()
            except Exception:pass
            return
        try:
            started = time.monotonic()
            if self._conn.closed:raise RuntimeError('connection is closed')
            self._conn.rollback()
            _metric("connection_returns", time.monotonic() - started)
        except Exception:_discard_connection(self._pool,self._conn)
        else:self._pool.putconn(self._conn)
    def __getattr__(self,name):return getattr(self._conn,name)
    def __enter__(self):
        self._conn.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            return self._conn.__exit__(exc_type, exc_val, exc_tb)
        finally:
            self.close()


class PoolExhaustedError(RuntimeError):
    """Raised when the connection pool cannot serve a connection.

    Fail closed: the pool is the ONLY connection path. The previous code fell
    back to an unrestricted psycopg2.connect() here, silently bypassing
    DB_POOL_MAX_CONNECTIONS and defeating the pool under load.
    """


def get_db_connection():
    pool = _get_pool()
    maxconn = max(1, int(os.getenv("DB_POOL_MAX_CONNECTIONS", "20")))
    last_error: Exception | None = None
    for _ in range(2):
        try:
            started = time.monotonic()
            raw_conn = pool.getconn()
        except Exception as exc:
            # Pool exhausted (psycopg2.pool.PoolError) or pool broken: never
            # bypass the pool with a direct connection; fail closed instead.
            last_error = exc
            _metric("pool_checkout_failures")
            break
        _metric("pool_checkouts", time.monotonic() - started)
        if raw_conn.closed:
            _discard_connection(pool, raw_conn)
            continue
        if _validation_is_recent(raw_conn):
            _metric("validation_skips")
            return PooledConnectionWrapper(pool, raw_conn)
        if _connection_is_usable(raw_conn):
            return PooledConnectionWrapper(pool, raw_conn)
        _discard_connection(pool, raw_conn)
        last_error = RuntimeError("pooled database connections failed validation")
    detail = f"{type(last_error).__name__}: {last_error}" if last_error else "no usable connection"
    raise PoolExhaustedError(
        f"database connection pool exhausted (DB_POOL_MAX_CONNECTIONS={maxconn}): {detail}"
    ) from last_error


def fetch_one(sql, params=()):
    conn=get_db_connection()
    try:
        started = time.monotonic()
        with conn.cursor() as cur:cur.execute(sql,params);row=cur.fetchone()
        _metric("sql_calls", time.monotonic() - started)
        return row
    finally:conn.close()


def fetch_all(sql, params=()):
    conn=get_db_connection()
    try:
        started = time.monotonic()
        with conn.cursor() as cur:cur.execute(sql,params);rows=cur.fetchall()
        _metric("sql_calls", time.monotonic() - started)
        return rows
    finally:conn.close()


def execute(sql, params=(), returning=False):
    conn=get_db_connection()
    try:
        started = time.monotonic()
        with conn.cursor() as cur:
            cur.execute(sql,params);row=cur.fetchone() if returning else None
        _metric("sql_calls", time.monotonic() - started)
        started = time.monotonic()
        conn.commit()
        _metric("commits", time.monotonic() - started)
        return row
    except Exception:
        started = time.monotonic()
        try:
            conn.rollback()
        finally:
            _metric("rollbacks", time.monotonic() - started)
        raise
    finally:conn.close()


def execute_count(sql, params=()):
    """Execute one mutation and return PostgreSQL's authoritative affected-row count."""
    conn=get_db_connection()
    try:
        started = time.monotonic()
        with conn.cursor() as cur:cur.execute(sql,params);count=cur.rowcount
        _metric("sql_calls", time.monotonic() - started)
        started = time.monotonic()
        conn.commit()
        _metric("commits", time.monotonic() - started)
        return count
    except Exception:
        started = time.monotonic()
        try:
            conn.rollback()
        finally:
            _metric("rollbacks", time.monotonic() - started)
        raise
    finally:conn.close()
