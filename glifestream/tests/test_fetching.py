from __future__ import annotations

from datetime import timedelta
import threading
from unittest.mock import Mock, patch

import pytest
from django.db import DatabaseError
from django.utils import timezone

from glifestream.fetching import (
    FetchWorker,
    claim_runnable_jobs,
    enqueue_manual_fetch,
    get_effective_interval_sec,
    get_next_wait_timeout,
    initialize_missing_schedules,
    ProcessedFetchJob,
    run_service_fetch,
    send_worker_wake_signal,
    sync_service_schedule,
)
from glifestream.stream.models import Service, ServiceFetchState


@pytest.mark.django_db
def test_effective_interval_uses_override_and_default(settings, service):
    settings.FETCH_DEFAULT_INTERVAL_SEC = 7200
    service.api = 'atproto'
    service.fetch_interval_sec = None
    assert get_effective_interval_sec(service) == 7200

    service.api = 'webfeed'
    service.fetch_interval_sec = None
    assert get_effective_interval_sec(service) == 7200

    service.fetch_interval_sec = 1800
    assert get_effective_interval_sec(service) == 1800


@pytest.mark.django_db
def test_effective_interval_uses_global_default_setting(settings, service):
    settings.FETCH_DEFAULT_INTERVAL_SEC = 14400
    service.api = 'webfeed'
    service.fetch_interval_sec = None
    assert get_effective_interval_sec(service) == 14400


@pytest.mark.django_db
def test_sync_service_schedule_uses_last_checked(settings, service):
    settings.FETCH_DEFAULT_INTERVAL_SEC = 7200
    now = timezone.now()
    service.api = 'webfeed'
    service.active = True
    service.fetch_interval_sec = 7200
    service.last_checked = now - timedelta(minutes=30)
    service.save()

    sync_service_schedule(service, now=now)
    service.refresh_from_db()

    assert service.next_fetch_at == service.last_checked + timedelta(seconds=7200)


@pytest.mark.django_db
def test_initialize_missing_schedules_recomputes_existing_cadence(settings, service):
    settings.FETCH_DEFAULT_INTERVAL_SEC = 7200
    now = timezone.now()
    service.api = 'atproto'
    service.active = True
    service.last_checked = now - timedelta(minutes=5)
    service.next_fetch_at = service.last_checked + timedelta(seconds=120)
    service.save()

    initialize_missing_schedules(now=now)
    service.refresh_from_db()

    assert service.next_fetch_at == service.last_checked + timedelta(seconds=7200)


@pytest.mark.django_db
def test_initialize_missing_schedules_does_not_move_retry_backwards(
    settings, service
):
    settings.FETCH_DEFAULT_INTERVAL_SEC = 7200
    now = timezone.now()
    service.api = 'atproto'
    service.active = True
    service.last_checked = now - timedelta(days=3)
    service.next_fetch_at = now + timedelta(hours=2)
    service.save()

    initialize_missing_schedules(now=now)
    service.refresh_from_db()

    assert service.next_fetch_at == now + timedelta(hours=2)


@pytest.mark.django_db
def test_enqueue_manual_fetch_deduplicates(service):
    service.api = 'webfeed'
    service.save()

    with patch('glifestream.fetching.send_worker_wake_signal', return_value=True):
        first = enqueue_manual_fetch(service)
        second = enqueue_manual_fetch(service)

    assert first.queued is True
    assert second.queued is False
    state = ServiceFetchState.objects.get(service=service)
    assert state.status == ServiceFetchState.STATUS_QUEUED
    assert state.trigger == ServiceFetchState.TRIGGER_MANUAL


@pytest.mark.django_db
def test_enqueue_manual_fetch_preserves_last_completed_summary(service):
    now = timezone.now()
    state = ServiceFetchState.objects.create(
        service=service,
        status=ServiceFetchState.STATUS_FAILED,
        finished_at=now,
        last_succeeded_at=now - timedelta(hours=2),
        last_failed_at=now,
        last_result='Fetch failed.',
        last_error='connection timeout',
    )

    with patch('glifestream.fetching.send_worker_wake_signal', return_value=True):
        result = enqueue_manual_fetch(service)

    state.refresh_from_db()
    assert result.queued is True
    assert state.status == ServiceFetchState.STATUS_QUEUED
    assert state.finished_at == now
    assert state.last_succeeded_at == now - timedelta(hours=2)
    assert state.last_failed_at == now
    assert state.last_result == 'Fetch failed.'
    assert state.last_error == 'connection timeout'


@pytest.mark.django_db
def test_claim_runnable_jobs_returns_due_scheduled_service(service):
    service.api = 'webfeed'
    service.active = True
    service.fetch_interval_sec = 10
    service.last_checked = timezone.now() - timedelta(minutes=5)
    service.save()
    sync_service_schedule(service)
    service.next_fetch_at = timezone.now() - timedelta(seconds=1)
    service.save(update_fields=['next_fetch_at'])

    claimed = claim_runnable_jobs('worker-token')

    assert claimed == [(ServiceFetchState.objects.get(service=service).pk, service.pk)]
    state = ServiceFetchState.objects.get(service=service)
    assert state.status == ServiceFetchState.STATUS_RUNNING
    assert state.worker_token == 'worker-token'


@pytest.mark.django_db
def test_claim_runnable_jobs_preserves_last_completed_summary(service):
    now = timezone.now()
    service.api = 'webfeed'
    service.active = True
    service.fetch_interval_sec = 10
    service.last_checked = now - timedelta(minutes=5)
    service.next_fetch_at = now - timedelta(seconds=1)
    service.save()
    state = ServiceFetchState.objects.create(
        service=service,
        status=ServiceFetchState.STATUS_FAILED,
        finished_at=now - timedelta(minutes=1),
        last_succeeded_at=now - timedelta(hours=3),
        last_failed_at=now - timedelta(minutes=1),
        last_result='Fetch failed.',
        last_error='feed offline',
    )

    claimed = claim_runnable_jobs('worker-token', now=now)

    assert claimed == [(state.pk, service.pk)]
    state.refresh_from_db()
    assert state.status == ServiceFetchState.STATUS_RUNNING
    assert state.started_at == now
    assert state.finished_at == now - timedelta(minutes=1)
    assert state.last_succeeded_at == now - timedelta(hours=3)
    assert state.last_failed_at == now - timedelta(minutes=1)
    assert state.last_result == 'Fetch failed.'
    assert state.last_error == 'feed offline'


@pytest.mark.django_db
def test_claim_runnable_jobs_recovers_abandoned_running_service(service):
    now = timezone.now()
    service.api = 'webfeed'
    service.active = True
    service.fetch_interval_sec = 10
    service.last_checked = now - timedelta(days=3)
    service.next_fetch_at = now - timedelta(seconds=1)
    service.save()
    state = ServiceFetchState.objects.create(
        service=service,
        status=ServiceFetchState.STATUS_RUNNING,
        started_at=now - timedelta(minutes=2),
        worker_token='stale-worker-token',
    )

    claimed = claim_runnable_jobs('worker-token', now=now)

    assert claimed == [(state.pk, service.pk)]
    state.refresh_from_db()
    assert state.status == ServiceFetchState.STATUS_RUNNING
    assert state.worker_token == 'worker-token'
    assert state.last_failed_at == now
    assert state.last_result == 'Fetch interrupted.'


@pytest.mark.django_db
def test_get_next_wait_timeout_ignores_running_service(service):
    now = timezone.now()
    service.api = 'webfeed'
    service.active = True
    service.next_fetch_at = now - timedelta(seconds=1)
    service.save()
    ServiceFetchState.objects.create(
        service=service,
        status=ServiceFetchState.STATUS_RUNNING,
        worker_token='stale-worker-token',
    )
    later_service = Service.objects.create(
        api='webfeed',
        name='Later service',
        url='http://example.com/later-feed',
        active=True,
        next_fetch_at=now + timedelta(seconds=30),
    )

    timeout = get_next_wait_timeout(now=now)

    assert later_service.pk is not None
    assert timeout == 30.0


@pytest.mark.django_db
def test_fetch_worker_run_ready_jobs_processes_queued_manual_job(service):
    service.api = 'webfeed'
    service.active = True
    service.save()
    enqueue_manual_fetch(service, wake_worker=False)

    ran = threading.Event()

    def _run_service_fetch(service_arg, **kwargs):
        del kwargs
        assert service_arg.pk == service.pk
        ran.set()

    fetch_worker = FetchWorker(socket_path='.gls-worker.sock', max_workers=1)
    with patch('glifestream.fetching.run_service_fetch', side_effect=_run_service_fetch):
        claimed = fetch_worker.run_ready_jobs()

    assert claimed == 1
    assert ran.is_set()
    assert fetch_worker.last_processed_jobs == [
        ProcessedFetchJob(
            service_id=service.pk,
            service_name=service.name,
            trigger=ServiceFetchState.TRIGGER_MANUAL,
        )
    ]


def test_fetch_worker_serve_wakes_on_ready_socket() -> None:
    fake_socket = Mock()
    fetch_worker = FetchWorker(socket_path='.gls-worker.sock', max_workers=1)
    stop_event = threading.Event()
    calls: list[str] = []

    def _run_ready_jobs() -> int:
        calls.append('run')
        stop_event.set()
        return 1

    with patch.object(fetch_worker, 'open_socket', return_value=fake_socket), patch.object(
        fetch_worker, 'close_socket', return_value=None
    ), patch.object(
        fetch_worker, 'run_ready_jobs', side_effect=_run_ready_jobs
    ), patch.object(fetch_worker, 'drain_socket', return_value=None), patch(
        'glifestream.fetching.initialize_missing_schedules', return_value=None
    ), patch('glifestream.fetching.get_next_wait_timeout', return_value=None), patch(
        'glifestream.fetching.select.select',
        return_value=([fake_socket], [], []),
    ):
        fetch_worker.serve(stop_event=stop_event)

    assert calls == ['run']


def test_fetch_worker_open_socket_replaces_stale_socket_file():
    fake_socket = Mock()
    fetch_worker = FetchWorker(socket_path='.gls-worker.sock', max_workers=1)

    with patch('glifestream.fetching.os.path.exists', return_value=True), patch(
        'glifestream.fetching.os.unlink'
    ) as unlink, patch('glifestream.fetching.os.chmod') as chmod, patch(
        'glifestream.fetching.socket.socket',
        return_value=fake_socket,
    ):
        sock = fetch_worker.open_socket()

    assert sock is fake_socket
    unlink.assert_called_once_with('.gls-worker.sock')
    fake_socket.bind.assert_called_once_with('.gls-worker.sock')
    chmod.assert_called_once_with('.gls-worker.sock', 0o666)


@pytest.mark.django_db
def test_fetch_worker_run_ready_jobs_handles_database_error():
    fetch_worker = FetchWorker(socket_path='.gls-worker.sock', max_workers=1)

    with patch(
        'glifestream.fetching.claim_runnable_jobs',
        side_effect=DatabaseError('database is locked'),
    ):
        assert fetch_worker.run_ready_jobs() == 0


@pytest.mark.django_db
def test_send_worker_wake_signal_uses_socket_path(settings):
    settings.WORKER_SOCKET = '.gls-worker.sock'
    fake_socket = Mock()

    with patch('glifestream.fetching.socket.socket', return_value=fake_socket):
        result = send_worker_wake_signal()

    assert result is True
    fake_socket.connect.assert_called_once_with('.gls-worker.sock')
    fake_socket.send.assert_called_once()


@pytest.mark.django_db
def test_fetch_worker_wake_flow_smoke(settings):
    settings.WORKER_SOCKET = '.gls-worker.sock'
    service = Service.objects.create(
        api='webfeed',
        name='Wake test',
        url='http://example.com/feed',
        active=True,
    )

    ran = threading.Event()

    def _run_service_fetch(service_arg, **kwargs):
        del service_arg, kwargs
        ran.set()

    fetch_worker = FetchWorker(socket_path='.gls-worker.sock', max_workers=1)

    with patch('glifestream.fetching.run_service_fetch', side_effect=_run_service_fetch):
        enqueue_manual_fetch(service, wake_worker=False)
        assert fetch_worker.run_ready_jobs() == 1

    assert ran.is_set()


@pytest.mark.django_db
def test_run_service_fetch_records_success_timestamp(service):
    service.api = 'webfeed'
    service.save()
    previous_failure = timezone.now() - timedelta(days=1)
    state = ServiceFetchState.objects.create(
        service=service,
        status=ServiceFetchState.STATUS_RUNNING,
        worker_token='worker-token',
        last_failed_at=previous_failure,
        last_error='temporary error',
    )
    api = Mock()

    with patch('glifestream.fetching.ServiceFactory.create_service', return_value=api):
        run_service_fetch(service, state_id=state.pk, worker_token='worker-token')

    state.refresh_from_db()
    assert state.status == ServiceFetchState.STATUS_SUCCEEDED
    assert state.finished_at is not None
    assert state.last_succeeded_at == state.finished_at
    assert state.last_failed_at == previous_failure
    assert state.last_result == 'Fetch completed.'
    assert state.last_error == ''


@pytest.mark.django_db
def test_run_service_fetch_failure_preserves_last_success(service):
    service.api = 'webfeed'
    service.save()
    previous_success = timezone.now() - timedelta(days=1)
    state = ServiceFetchState.objects.create(
        service=service,
        status=ServiceFetchState.STATUS_RUNNING,
        worker_token='worker-token',
        last_succeeded_at=previous_success,
        finished_at=previous_success,
        last_result='Fetch completed.',
    )

    with patch(
        'glifestream.fetching.ServiceFactory.create_service',
        return_value=Mock(run=Mock(side_effect=RuntimeError('boom'))),
    ), pytest.raises(RuntimeError, match='boom'):
        run_service_fetch(service, state_id=state.pk, worker_token='worker-token')

    state.refresh_from_db()
    assert state.status == ServiceFetchState.STATUS_FAILED
    assert state.finished_at is not None
    assert state.last_failed_at == state.finished_at
    assert state.last_succeeded_at == previous_success
    assert state.last_result == 'Fetch failed.'
    assert state.last_error == 'boom'
