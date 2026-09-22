"""How two writers behave on SQLite.

SQLite starts a transaction in DEFERRED mode: it takes a read lock first and
upgrades to a write lock on the first write. When two transactions have both
read and then both try to write, SQLite fails one at once with "database is
locked" instead of waiting for `timeout`, because waiting could only
deadlock. `transaction_mode: IMMEDIATE` takes the write lock up front, so the
second transaction waits its turn.

These tests use their own file-backed database: the test database is in
memory, where locking works differently.
"""

from __future__ import annotations

import threading
from typing import Any

import pytest
from django.conf import settings
from django.db import OperationalError, connections, transaction

ALIAS = 'locking'


def define_database(tmp_path, **options: Any) -> None:
    settings.DATABASES[ALIAS] = {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': str(tmp_path / 'locking.sqlite3'),
        'ATOMIC_REQUESTS': False,
        'AUTOCOMMIT': True,
        'CONN_MAX_AGE': 0,
        'CONN_HEALTH_CHECKS': False,
        'OPTIONS': options,
        'TIME_ZONE': None,
        'USER': '',
        'PASSWORD': '',
        'HOST': '',
        'PORT': '',
        'TEST': {},
    }
    with connections[ALIAS].cursor() as cursor:
        cursor.execute('CREATE TABLE IF NOT EXISTS counter (id INTEGER, value INTEGER)')
        cursor.execute('DELETE FROM counter')
        cursor.execute('INSERT INTO counter VALUES (1, 0)')


@pytest.fixture
def locking_db(tmp_path, django_db_blocker):
    # This database is the test's own file, not the test database, so
    # pytest-django's guard against stray database access does not apply.
    with django_db_blocker.unblock():

        def _define(**options: Any) -> None:
            define_database(tmp_path, **options)

        yield _define

        for conn in list(connections.all()):
            if conn.alias == ALIAS:
                conn.close()
        settings.DATABASES.pop(ALIAS, None)
        del connections[ALIAS]


def read_then_write(
    errors: list[Exception], mine: threading.Event, other: threading.Event
) -> None:
    """One transaction that reads a row, waits for the other, then writes.

    The wait gives the other transaction time to read before this one writes,
    which is what makes two DEFERRED transactions collide. It is a timeout,
    not a barrier: with IMMEDIATE the second transaction cannot even start
    until the first one commits.
    """
    try:
        with transaction.atomic(using=ALIAS):
            with connections[ALIAS].cursor() as cursor:
                cursor.execute('SELECT value FROM counter WHERE id = 1')
                value = cursor.fetchone()[0]
                mine.set()
                other.wait(1)
                cursor.execute(
                    'UPDATE counter SET value = %s WHERE id = 1', [value + 1]
                )
    except Exception as exc:  # noqa: BLE001 - reported through `errors`
        errors.append(exc)
    finally:
        connections[ALIAS].close()


def run_both() -> list[Exception]:
    errors: list[Exception] = []
    first, second = threading.Event(), threading.Event()
    threads = [
        threading.Thread(target=read_then_write, args=(errors, first, second)),
        threading.Thread(target=read_then_write, args=(errors, second, first)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
        assert not thread.is_alive()
    return errors


def test_deferred_transactions_lose_one_of_two_writers(locking_db):
    locking_db(timeout=30)

    errors = run_both()

    assert [str(error) for error in errors] == ['database is locked']
    assert isinstance(errors[0], OperationalError)


def test_immediate_transactions_let_both_writers_through(locking_db):
    locking_db(timeout=30, transaction_mode='IMMEDIATE')

    errors = run_both()

    assert errors == []
    with connections[ALIAS].cursor() as cursor:
        cursor.execute('SELECT value FROM counter WHERE id = 1')
        assert cursor.fetchone()[0] in (1, 2)


def test_the_project_configures_sqlite_for_concurrent_writers():
    options = settings.DATABASES['default']['OPTIONS']

    if settings.DATABASES['default']['ENGINE'] != 'django.db.backends.sqlite3':
        pytest.skip('Not running on SQLite.')
    assert options['transaction_mode'] == 'IMMEDIATE'
    assert options['timeout'] >= 5
