"""The fetch queue under SQLite's real locking, with two threads at once.

`test_sqlite_locking.py` shows why the project runs SQLite transactions in
IMMEDIATE mode. These tests run the queue's own functions against a
file-backed database: the daemon claiming jobs, a "Run now" click queueing
one, and a finished fetch recording its outcome. One thread stops inside its
transaction, holding the write lock, while the other starts. The other must
wait for the lock and then act on what the first one committed, rather than
fail with "database is locked" or act on a stale read.

The test database is in memory, where SQLite locks tables in a shared cache
and never waits for `timeout`, so each test gets its own file instead.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
import shutil
import threading
import time
from typing import Any
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.db import connections
from django.utils import timezone

from glifestream.fetching import (
    _update_state_success,
    claim_runnable_jobs,
    enqueue_manual_fetch,
)
from glifestream.stream.models import Service, ServiceFetchState

HOLD_SEC = 0.3


@contextmanager
def database_file(path: Path) -> Iterator[None]:
    """Point the default database at `path`, in this thread and new ones.

    The current connection is set aside rather than closed: closing the
    in-memory test database would destroy it for the rest of the run.
    """
    previous = connections['default']
    config = {**connections.settings['default'], 'NAME': str(path)}
    with patch.dict(connections.settings, {'default': config}):
        connection = connections.create_connection('default')
        connections['default'] = connection
        try:
            yield
        finally:
            connection.close()
            connections['default'] = previous


@pytest.fixture(scope='module')
def migrated_file(tmp_path_factory: pytest.TempPathFactory, django_db_blocker) -> Path:
    path = tmp_path_factory.mktemp('fetch-queue') / 'migrated.sqlite3'
    with django_db_blocker.unblock(), database_file(path):
        call_command('migrate', run_syncdb=True, verbosity=0)
    return path


@pytest.fixture
def file_db(migrated_file, tmp_path, django_db_blocker) -> Iterator[None]:
    # The database is this test's own file, not the test database, so
    # pytest-django's guard against stray database access does not apply.
    path = tmp_path / 'db.sqlite3'
    shutil.copyfile(migrated_file, path)
    with django_db_blocker.unblock(), database_file(path):
        yield


class HoldTransaction:
    """An execute wrapper that parks its thread inside a transaction.

    BEGIN IMMEDIATE takes the write lock, so from the first statement inside
    the transaction on, every other writer queues behind this thread. It
    waits for the other thread to start, then keeps the lock for `seconds`.
    """

    def __init__(self, seconds: float) -> None:
        self.seconds = seconds
        self.holding = threading.Event()
        self.other_started = threading.Event()

    def __call__(self, execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        if context['connection'].in_atomic_block and not self.holding.is_set():
            self.holding.set()
            self.other_started.wait(5)
            time.sleep(self.seconds)
        return result


def run_overlapping(
    holder: Callable[[], Any], waiter: Callable[[], Any]
) -> tuple[Any, Any, float]:
    """Run `waiter` while `holder` sits inside its transaction.

    Returns both results and how long `waiter` took.
    """
    hold = HoldTransaction(HOLD_SEC)
    results: dict[str, Any] = {}
    errors: list[BaseException] = []

    def run_holder() -> None:
        try:
            with connections['default'].execute_wrapper(hold):
                results['holder'] = holder()
        except BaseException as exc:  # noqa: BLE001 - reported through `errors`
            errors.append(exc)
        finally:
            hold.holding.set()
            connections.close_all()

    def run_waiter() -> None:
        try:
            assert hold.holding.wait(5), 'holder never entered its transaction'
            hold.other_started.set()
            started = time.monotonic()
            results['waiter'] = waiter()
            results['waited'] = time.monotonic() - started
        except BaseException as exc:  # noqa: BLE001 - reported through `errors`
            errors.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=run_holder), threading.Thread(target=run_waiter)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
        assert not thread.is_alive()
    if errors:
        raise errors[0]
    return results['holder'], results['waiter'], results['waited']


def make_service(*, due: bool, status: str = ServiceFetchState.STATUS_IDLE) -> Service:
    now = timezone.now()
    service = Service.objects.create(
        api='webfeed',
        name='Feed',
        url='http://example.com/feed',
        active=True,
        fetch_interval_sec=3600,
        # Checked more than an interval ago, or the claim's schedule pass
        # would push next_fetch_at forward to last_checked + interval.
        last_checked=now - timedelta(hours=2),
        next_fetch_at=now + (timedelta(seconds=-1) if due else timedelta(hours=1)),
    )
    # The state exists up front, so get_or_create never opens a transaction
    # of its own that the holder would stop in by mistake.
    ServiceFetchState.objects.create(service=service, status=status)
    return service


def fetch_state(service: Service) -> ServiceFetchState:
    return ServiceFetchState.objects.get(service=service)


def test_run_now_waits_for_a_claim_in_progress(file_db):
    service = make_service(due=True)

    claimed, enqueued, waited = run_overlapping(
        lambda: claim_runnable_jobs('daemon'),
        lambda: enqueue_manual_fetch(service, wake_worker=False),
    )

    assert waited >= HOLD_SEC / 2
    assert [service_id for _, service_id in claimed] == [service.pk]
    # The click lands after the claim committed, so it sees the job running
    # and does not queue a second fetch.
    assert enqueued.queued is False
    state = fetch_state(service)
    assert state.status == ServiceFetchState.STATUS_RUNNING
    assert state.trigger == ServiceFetchState.TRIGGER_SCHEDULE
    assert state.worker_token == 'daemon'


def test_claim_waits_for_a_run_now_in_progress(file_db):
    service = make_service(due=False)

    enqueued, claimed, waited = run_overlapping(
        lambda: enqueue_manual_fetch(service, wake_worker=False),
        lambda: claim_runnable_jobs('daemon'),
    )

    assert waited >= HOLD_SEC / 2
    assert enqueued.queued is True
    # The service is not due, so only the committed click makes it runnable.
    assert claimed == [(fetch_state(service).pk, service.pk)]
    state = fetch_state(service)
    assert state.status == ServiceFetchState.STATUS_RUNNING
    assert state.trigger == ServiceFetchState.TRIGGER_MANUAL
    assert state.worker_token == 'daemon'


def test_finished_fetch_waits_for_a_run_now_in_progress(file_db):
    service = make_service(due=False, status=ServiceFetchState.STATUS_RUNNING)
    ServiceFetchState.objects.filter(service=service).update(worker_token='daemon')
    finished_at = timezone.now()

    enqueued, _, waited = run_overlapping(
        lambda: enqueue_manual_fetch(service, wake_worker=False),
        lambda: _update_state_success(
            fetch_state(service).pk, 'daemon', service, finished_at=finished_at
        ),
    )

    assert waited >= HOLD_SEC / 2
    assert enqueued.queued is False
    state = fetch_state(service)
    assert state.status == ServiceFetchState.STATUS_SUCCEEDED
    assert state.last_succeeded_at == finished_at
    assert state.worker_token == ''
    service.refresh_from_db()
    assert service.next_fetch_at == finished_at + timedelta(seconds=3600)
