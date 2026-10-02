from unittest.mock import Mock

import pytest
from psycopg2 import InterfaceError, OperationalError

from database import connection


class FakeCursor:
    def __init__(self, error=None):
        self.error = error
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=()):
        self.executed.append((sql, params))
        if self.error:
            raise self.error

    def fetchone(self):
        return {'ok': 1}


class FakeConnection:
    def __init__(self, *, closed=0, validation_error=None, rollback_error=None):
        self.closed = closed
        self.cursor_instance = FakeCursor(validation_error)
        self.rollback_error = rollback_error
        self.rollback_calls = 0
        self.close_calls = 0

    def cursor(self):
        return self.cursor_instance

    def rollback(self):
        self.rollback_calls += 1
        if self.rollback_error:
            raise self.rollback_error

    def close(self):
        self.close_calls += 1
        self.closed = 1


class FakePool:
    closed = False

    def __init__(self, *connections):
        self.connections = list(connections)
        self.returned = []
        self.discarded = []

    def getconn(self):
        return self.connections.pop(0)

    def putconn(self, conn, close=False):
        (self.discarded if close else self.returned).append(conn)


def test_healthy_pooled_connection_is_validated_and_reused(monkeypatch):
    raw = FakeConnection()
    pool = FakePool(raw, raw)
    monkeypatch.setattr(connection, '_get_pool', lambda: pool)
    monkeypatch.setattr(connection, '_VALIDATION_INTERVAL_SECONDS', 30)
    connection.reset_pool_metrics()

    wrapped = connection.get_db_connection()

    assert wrapped._conn is raw
    assert raw.cursor_instance.executed == [('SELECT 1', ())]
    wrapped.close()
    assert pool.returned == [raw]
    assert pool.discarded == []

    wrapped_again = connection.get_db_connection()
    wrapped_again.close()
    assert raw.cursor_instance.executed == [('SELECT 1', ())]
    assert connection.pool_metrics_snapshot()["counts"]["validation_selects"] == 1


@pytest.mark.parametrize('broken', [
    FakeConnection(closed=1),
    FakeConnection(validation_error=OperationalError('SSL connection has been closed unexpectedly')),
    FakeConnection(validation_error=OperationalError('server closed the connection unexpectedly')),
    FakeConnection(validation_error=InterfaceError('connection already closed')),
    FakeConnection(rollback_error=OperationalError('connection reset')),
])
def test_broken_connection_is_discarded_and_replaced(monkeypatch, broken):
    healthy = FakeConnection()
    pool = FakePool(broken, healthy)
    monkeypatch.setattr(connection, '_get_pool', lambda: pool)

    wrapped = connection.get_db_connection()

    assert wrapped._conn is healthy
    assert pool.discarded == [broken]
    assert broken not in pool.returned


def test_connection_broken_during_use_is_not_returned_for_reuse():
    raw = FakeConnection(rollback_error=RuntimeError('server closed the connection unexpectedly'))
    pool = FakePool()
    wrapped = connection.PooledConnectionWrapper(pool, raw)

    wrapped.close()

    assert pool.discarded == [raw]
    assert pool.returned == []


def test_failed_write_is_not_replayed(monkeypatch):
    cursor = FakeCursor(RuntimeError('connection reset'))
    raw = Mock()
    raw.cursor.return_value = cursor
    monkeypatch.setattr(connection, 'get_db_connection', lambda: raw)

    with pytest.raises(RuntimeError, match='connection reset'):
        connection.execute('INSERT INTO events(value) VALUES(%s)', ('once',))

    assert cursor.executed == [('INSERT INTO events(value) VALUES(%s)', ('once',))]
    raw.rollback.assert_called_once_with()
    raw.close.assert_called_once_with()
