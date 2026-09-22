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
    WorkerAlreadyRunning,
    run_service_fetch,
    send_worker_wake_signal,
    serialize_fetch_state,
    sync_service_schedule,
)
from glifestream.stream.models import Service, ServiceFetchState
from glifestream.utils import httpclient


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
def test_initialize_missing_schedules_does_not_move_retry_backwards(settings, service):
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
    with patch(
        'glifestream.fetching.run_service_fetch', side_effect=_run_service_fetch
    ):
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


@pytest.mark.django_db
def test_fetch_worker_survives_a_failed_fetch_and_runs_the_rest(caplog):
    broken = Service.objects.create(name='Broken', api='webfeed', url='http://a')
    healthy = Service.objects.create(name='Healthy', api='webfeed', url='http://b')
    enqueue_manual_fetch(broken, wake_worker=False)
    enqueue_manual_fetch(healthy, wake_worker=False)
    ran = []

    def _run_service_fetch(service_arg, **kwargs):
        del kwargs
        ran.append(service_arg.name)
        if service_arg.pk == broken.pk:
            raise RuntimeError('provider exploded')

    fetch_worker = FetchWorker(socket_path='.gls-worker.sock', max_workers=1)
    with patch(
        'glifestream.fetching.run_service_fetch', side_effect=_run_service_fetch
    ):
        claimed = fetch_worker.run_ready_jobs()

    assert claimed == 2
    assert sorted(ran) == ['Broken', 'Healthy']
    assert (
        'Fetch job for service %d ended with RuntimeError: provider exploded'
        % broken.pk
    ) in caplog.text


def test_fetch_worker_serve_wakes_on_ready_socket() -> None:
    fake_socket = Mock()
    fetch_worker = FetchWorker(socket_path='.gls-worker.sock', max_workers=1)
    stop_event = threading.Event()
    calls: list[str] = []

    def _run_ready_jobs() -> int:
        calls.append('run')
        stop_event.set()
        return 1

    with (
        patch.object(fetch_worker, 'open_socket', return_value=fake_socket),
        patch.object(fetch_worker, 'close_socket', return_value=None),
        patch.object(fetch_worker, 'run_ready_jobs', side_effect=_run_ready_jobs),
        patch.object(fetch_worker, 'drain_socket', return_value=None),
        patch('glifestream.fetching.initialize_missing_schedules', return_value=None),
        patch('glifestream.fetching.get_next_wait_timeout', return_value=None),
        patch(
            'glifestream.fetching.select.select',
            return_value=([fake_socket], [], []),
        ),
    ):
        fetch_worker.serve(stop_event=stop_event)

    assert calls == ['run']


def test_fetch_worker_open_socket_replaces_stale_socket_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # for the lock file beside the socket
    fake_socket = Mock()
    fetch_worker = FetchWorker(socket_path='.gls-worker.sock', max_workers=1)

    with (
        patch('glifestream.fetching.os.path.exists', return_value=True),
        patch('glifestream.fetching.os.unlink') as unlink,
        patch('glifestream.fetching.os.chmod') as chmod,
        patch(
            'glifestream.fetching.socket.socket',
            return_value=fake_socket,
        ),
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

    with patch(
        'glifestream.fetching.run_service_fetch', side_effect=_run_service_fetch
    ):
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

    with (
        patch(
            'glifestream.fetching.ServiceFactory.create_service',
            return_value=Mock(run=Mock(side_effect=RuntimeError('boom'))),
        ),
        pytest.raises(RuntimeError, match='boom'),
    ):
        run_service_fetch(service, state_id=state.pk, worker_token='worker-token')

    state.refresh_from_db()
    assert state.status == ServiceFetchState.STATUS_FAILED
    assert state.finished_at is not None
    assert state.last_failed_at == state.finished_at
    assert state.last_succeeded_at == previous_success
    assert state.last_result == 'Unexpected fetch error.'
    assert state.last_error == 'boom'


@pytest.mark.django_db
def test_run_service_fetch_records_classified_fetch_failure(service):
    service.api = 'webfeed'
    service.save()
    state = ServiceFetchState.objects.create(
        service=service,
        status=ServiceFetchState.STATUS_RUNNING,
        worker_token='worker-token',
    )
    fetch_error = httpclient.build_fetch_error(
        category='timeout',
        detail='Request to http://example.com/feed timed out.',
        retryable=True,
        url='http://example.com/feed',
    )

    with (
        patch(
            'glifestream.fetching.ServiceFactory.create_service',
            return_value=Mock(run=Mock(side_effect=fetch_error)),
        ),
        pytest.raises(httpclient.FetchError),
    ):
        run_service_fetch(service, state_id=state.pk, worker_token='worker-token')

    state.refresh_from_db()
    assert state.status == ServiceFetchState.STATUS_FAILED
    assert state.last_result == 'Remote request timed out.'
    assert state.last_error == 'Request to http://example.com/feed timed out.'


@pytest.mark.django_db
def test_run_service_fetch_records_invalid_response_failure(service):
    service.api = 'webfeed'
    service.save()
    state = ServiceFetchState.objects.create(
        service=service,
        status=ServiceFetchState.STATUS_RUNNING,
        worker_token='worker-token',
    )
    fetch_error = httpclient.build_fetch_error(
        category='invalid_response',
        detail='Feed response from http://example.com/feed used unsupported content type image/png.',
        retryable=False,
        url='http://example.com/feed',
    )

    with (
        patch(
            'glifestream.fetching.ServiceFactory.create_service',
            return_value=Mock(run=Mock(side_effect=fetch_error)),
        ),
        pytest.raises(httpclient.FetchError),
    ):
        run_service_fetch(service, state_id=state.pk, worker_token='worker-token')

    state.refresh_from_db()
    assert state.status == ServiceFetchState.STATUS_FAILED
    assert (
        state.last_result
        == 'Remote service returned an invalid or unsupported response.'
    )
    assert 'unsupported content type image/png' in state.last_error


@pytest.mark.django_db
def test_serialize_fetch_state_without_a_state_row_reads_all_blanks(service):
    payload = serialize_fetch_state(service)

    assert payload['service_id'] == service.pk
    assert payload['status'] == ServiceFetchState.STATUS_IDLE
    assert payload['trigger'] == ''
    assert payload['last_result'] == ''
    assert payload['last_error'] == ''
    assert all(
        payload[name] is None
        for name in (
            'requested_at',
            'started_at',
            'finished_at',
            'last_succeeded_at',
            'last_failed_at',
            'next_fetch_at',
        )
    )


@pytest.mark.django_db
def test_serialize_fetch_state_renders_every_timestamp_it_has(service):
    service.api = 'webfeed'
    service.save(update_fields=['api'])
    now = timezone.now()
    state = ServiceFetchState.objects.create(
        service=service,
        status=ServiceFetchState.STATUS_FAILED,
        trigger=ServiceFetchState.TRIGGER_MANUAL,
        requested_at=now,
        started_at=now,
        finished_at=now,
        last_succeeded_at=now - timedelta(hours=1),
        last_failed_at=now,
        last_result='Remote request timed out.',
        last_error='timeout',
    )
    service.next_fetch_at = now + timedelta(hours=2)
    service.save(update_fields=['next_fetch_at'])

    payload = serialize_fetch_state(service, state)

    assert payload['status'] == ServiceFetchState.STATUS_FAILED
    assert payload['trigger'] == ServiceFetchState.TRIGGER_MANUAL
    assert payload['requested_at'] == now.isoformat()
    assert payload['last_succeeded_at'] == (now - timedelta(hours=1)).isoformat()
    assert payload['next_fetch_at'] == (now + timedelta(hours=2)).isoformat()
    assert payload['last_result'] == 'Remote request timed out.'
    assert payload['last_error'] == 'timeout'
    assert payload['can_fetch'] is True


@pytest.mark.django_db
def test_serialize_fetch_state_looks_the_row_up_when_not_given_one(service):
    ServiceFetchState.objects.create(
        service=service, status=ServiceFetchState.STATUS_QUEUED
    )

    assert serialize_fetch_state(service)['status'] == ServiceFetchState.STATUS_QUEUED


@pytest.mark.django_db
def test_serialize_fetch_state_marks_a_selfposts_service_unfetchable(db):
    notes = Service.objects.create(name='Notes', api='selfposts')

    payload = serialize_fetch_state(notes)

    assert payload['can_fetch'] is False
    assert payload['effective_interval_sec'] is None


def test_fetch_worker_drain_socket_empties_pending_signals():
    import socket as socket_mod

    reader, writer = socket_mod.socketpair(socket_mod.AF_UNIX, socket_mod.SOCK_DGRAM)
    fetch_worker = FetchWorker(socket_path='.gls-worker.sock', max_workers=1)
    fetch_worker.socket = reader
    try:
        for _ in range(3):
            writer.send(b'wake')
        fetch_worker.drain_socket()

        reader.setblocking(False)
        with pytest.raises(BlockingIOError):
            reader.recv(1024)
    finally:
        reader.close()
        writer.close()


def test_fetch_worker_drain_socket_stops_on_a_read_error():
    fetch_worker = FetchWorker(socket_path='.gls-worker.sock', max_workers=1)
    fetch_worker.socket = Mock()
    fetch_worker.socket.recv.side_effect = OSError('gone')

    with patch(
        'glifestream.fetching.select.select',
        return_value=([fetch_worker.socket], [], []),
    ):
        fetch_worker.drain_socket()

    fetch_worker.socket.recv.assert_called_once_with(1024)


def test_fetch_worker_drain_socket_without_a_socket_is_a_no_op():
    FetchWorker(socket_path='.gls-worker.sock', max_workers=1).drain_socket()


def test_fetch_worker_close_socket_removes_the_socket_file(tmp_path, monkeypatch):
    # A relative path: macOS rejects AF_UNIX paths as long as tmp_path.
    monkeypatch.chdir(tmp_path)
    path = tmp_path / 'worker.sock'
    fetch_worker = FetchWorker(socket_path='worker.sock', max_workers=1)
    sock = fetch_worker.open_socket()

    fetch_worker.close_socket()

    assert fetch_worker.socket is None
    assert sock.fileno() == -1
    assert not path.exists()
    fetch_worker.close_socket()


def test_second_fetch_worker_refuses_to_take_over_the_socket(tmp_path, monkeypatch):
    # A relative path: macOS rejects AF_UNIX paths as long as tmp_path.
    monkeypatch.chdir(tmp_path)
    first = FetchWorker(socket_path='worker.sock', max_workers=1)
    first.open_socket()
    second = FetchWorker(socket_path='worker.sock', max_workers=1)

    try:
        with pytest.raises(WorkerAlreadyRunning, match='worker.sock.lock'):
            second.open_socket()
        second.close_socket()

        # The first worker still owns its socket and can still be woken.
        assert (tmp_path / 'worker.sock').is_socket()
        with patch(
            'glifestream.fetching.get_worker_socket', return_value='worker.sock'
        ):
            assert send_worker_wake_signal() is True
    finally:
        first.close_socket()

    second.open_socket()
    second.close_socket()


def test_fetch_worker_releases_the_lock_when_bind_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fetch_worker = FetchWorker(socket_path='worker.sock', max_workers=1)

    with patch('glifestream.fetching.socket.socket') as socket_cls:
        socket_cls.return_value.bind.side_effect = OSError('address in use')
        with pytest.raises(OSError, match='address in use'):
            fetch_worker.open_socket()

    assert fetch_worker.lock_file is None
    fetch_worker.open_socket()
    fetch_worker.close_socket()


@pytest.mark.django_db
@pytest.mark.parametrize(
    'last_checked_ago, force_check, runs',
    [
        (None, False, True),
        (timedelta(hours=2), False, True),
        (timedelta(minutes=5), False, False),
        (timedelta(minutes=5), True, True),
    ],
)
def test_run_services_honours_the_fetch_interval(
    settings, service, last_checked_ago, force_check, runs
):
    from glifestream.fetching import run_services

    settings.FETCH_DEFAULT_INTERVAL_SEC = 3600
    service.api = 'webfeed'
    service.last_checked = (
        timezone.now() - last_checked_ago if last_checked_ago else None
    )
    service.save()

    with patch('glifestream.fetching.run_service_fetch') as fetch:
        run_services({'id': service.pk}, force_check=force_check)

    assert fetch.called is runs


@pytest.mark.django_db
def test_run_services_with_no_matching_services_does_nothing():
    from glifestream.fetching import run_services

    with patch('glifestream.fetching.run_service_fetch') as fetch:
        run_services({'id': 999})

    fetch.assert_not_called()
