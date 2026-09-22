from __future__ import annotations

import threading
import time
from datetime import timedelta
from unittest.mock import Mock, patch

import pytest
from django.utils import timezone

from glifestream.fetching import (
    FetchWorker,
    enqueue_manual_fetch,
    get_fetch_job_timeout_sec,
    recover_abandoned_fetch_states,
    run_service_fetch,
)
from glifestream.stream.models import Service, ServiceFetchState

RETRYABLE = ServiceFetchState.FAILURE_RETRYABLE


def feed(name: str) -> Service:
    return Service.objects.create(
        name=name,
        api='webfeed',
        url='http://%s.example/' % name,
        fetch_interval_sec=600,
    )


def wait_for_thread(name: str, timeout: float = 5.0) -> None:
    for thread in threading.enumerate():
        if thread.name == name:
            thread.join(timeout)
            assert not thread.is_alive()


@pytest.fixture
def hung():
    """A patch target whose fetch blocks until the test releases it."""
    release = threading.Event()
    yield release
    release.set()


@pytest.mark.django_db(transaction=True)
def test_a_hung_fetch_times_out_without_blocking_the_others(settings, hung):
    settings.FETCH_RETRY_BASE_SEC = 60
    stuck, healthy = feed('stuck'), feed('healthy')
    enqueue_manual_fetch(stuck, wake_worker=False)
    enqueue_manual_fetch(healthy, wake_worker=False)
    ran = []

    def fake_fetch(service, **kwargs):
        if service.pk == stuck.pk:
            hung.wait(10)
        ran.append(service.name)

    worker = FetchWorker(
        socket_path='.gls-worker.sock', max_workers=1, job_timeout_sec=0.2
    )
    started = time.monotonic()
    with patch('glifestream.fetching.run_service_fetch', side_effect=fake_fetch):
        assert worker.run_ready_jobs() == 2

    assert time.monotonic() - started < 5
    assert ran == ['healthy']
    state = ServiceFetchState.objects.get(service=stuck)
    assert state.status == ServiceFetchState.STATUS_FAILED
    assert state.last_result == 'Fetch timed out.'
    assert state.last_error == 'The fetch did not finish within 0.2 seconds.'
    assert (state.failure_kind, state.failure_category) == (RETRYABLE, 'timeout')
    assert (state.consecutive_failures, state.worker_token) == (1, '')
    stuck.refresh_from_db()
    assert stuck.next_fetch_at - state.finished_at <= timedelta(seconds=60)


@pytest.mark.django_db(transaction=True)
def test_a_fetch_finishing_after_its_timeout_changes_nothing(settings, hung):
    settings.FETCH_RETRY_BASE_SEC = 60
    service = feed('late')
    enqueue_manual_fetch(service, wake_worker=False)

    def slow_run():
        hung.wait(10)

    worker = FetchWorker(
        socket_path='.gls-worker.sock', max_workers=1, job_timeout_sec=0.2
    )
    with patch(
        'glifestream.fetching.ServiceFactory.create_service',
        return_value=Mock(run=Mock(side_effect=slow_run)),
    ):
        worker.run_ready_jobs()
        timed_out = ServiceFetchState.objects.get(service=service)
        service.refresh_from_db()
        scheduled = service.next_fetch_at

        hung.set()
        wait_for_thread('fetch-service-%d' % service.pk)

    state = ServiceFetchState.objects.get(service=service)
    assert (state.status, state.last_result) == (
        ServiceFetchState.STATUS_FAILED,
        'Fetch timed out.',
    )
    assert state.finished_at == timed_out.finished_at
    assert state.last_succeeded_at is None
    service.refresh_from_db()
    assert service.next_fetch_at == scheduled


@pytest.mark.django_db
def test_a_stale_success_leaves_the_schedule_alone(service):
    service.api = 'webfeed'
    service.next_fetch_at = timezone.now() + timedelta(minutes=1)
    service.save()
    scheduled = service.next_fetch_at
    state = ServiceFetchState.objects.create(
        service=service, status=ServiceFetchState.STATUS_FAILED, worker_token=''
    )

    with patch(
        'glifestream.fetching.ServiceFactory.create_service',
        return_value=Mock(run=Mock()),
    ):
        run_service_fetch(service, state_id=state.pk, worker_token='gone')

    service.refresh_from_db()
    state.refresh_from_db()
    assert service.next_fetch_at == scheduled
    assert state.status == ServiceFetchState.STATUS_FAILED


@pytest.mark.django_db
def test_recovering_an_abandoned_fetch_counts_as_a_failure(service):
    state = ServiceFetchState.objects.create(
        service=service,
        status=ServiceFetchState.STATUS_RUNNING,
        consecutive_failures=2,
        worker_token='crashed',
    )

    recover_abandoned_fetch_states()

    state.refresh_from_db()
    assert state.status == ServiceFetchState.STATUS_FAILED
    assert (state.consecutive_failures, state.worker_token) == (3, '')
    assert (state.failure_kind, state.failure_category) == (RETRYABLE, 'interrupted')


def test_the_job_timeout_setting(settings):
    del settings.FETCH_JOB_TIMEOUT_SEC
    assert get_fetch_job_timeout_sec() == 900

    settings.FETCH_JOB_TIMEOUT_SEC = 30
    assert get_fetch_job_timeout_sec() == 30
    assert FetchWorker(socket_path='.gls-worker.sock').job_timeout_sec == 30
