"""
#  gLifestream Copyright (C) 2026 Wojciech Polak
#
#  This program is free software; you can redistribute it and/or modify it
#  under the terms of the GNU General Public License as published by the
#  Free Software Foundation; either version 3 of the License, or (at your
#  option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License along
#  with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

from __future__ import annotations

import logging
import os
import queue
import select
import socket
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from django.conf import settings
from django.contrib.auth.models import User
from django.db import DatabaseError, close_old_connections, connections, transaction
from django.db.models import F, Q
from django.utils import timezone
from django.utils.translation import ngettext

from glifestream.apis.factory import ServiceFactory
from glifestream.stream import websub
from glifestream.stream.models import Entry, Service, ServiceFetchState
from glifestream.utils import httpclient

logger = logging.getLogger(__name__)

WAKE_PAYLOAD = b'wake'
DEFAULT_WORKER_SOCKET = '/tmp/glifestream-worker.sock'
DEFAULT_WORKER_POOL_SIZE = 4
DEFAULT_FETCH_INTERVAL_SEC = 7200
DEFAULT_FETCH_RETRY_BASE_SEC = 60
DEFAULT_FETCH_TERMINAL_DELAY_SEC = 24 * 3600
DEFAULT_FETCH_JOB_TIMEOUT_SEC = 900
# Past this many doublings the retry delay has long hit the interval cap.
MAX_RETRY_DOUBLINGS = 20


@dataclass(slots=True)
class EnqueueResult:
    state: ServiceFetchState
    queued: bool
    wake_sent: bool


@dataclass(slots=True, frozen=True)
class FetchFailure:
    kind: str
    category: str
    retry_after_sec: int | None = None


@dataclass(slots=True, frozen=True)
class _FetchJob:
    state_id: int | None
    service: Service


@dataclass(slots=True, frozen=True)
class ProcessedFetchJob:
    service_id: int
    service_name: str
    trigger: str


def get_worker_socket() -> str:
    return getattr(
        settings,
        'WORKER_SOCKET',
        DEFAULT_WORKER_SOCKET,
    )


def get_worker_pool_size() -> int:
    return int(
        getattr(
            settings,
            'WORKER_POOL_SIZE',
            DEFAULT_WORKER_POOL_SIZE,
        )
    )


def get_default_fetch_interval_sec() -> int:
    return int(
        getattr(
            settings,
            'FETCH_DEFAULT_INTERVAL_SEC',
            DEFAULT_FETCH_INTERVAL_SEC,
        )
    )


def get_fetch_retry_base_sec() -> int:
    return int(getattr(settings, 'FETCH_RETRY_BASE_SEC', DEFAULT_FETCH_RETRY_BASE_SEC))


def get_fetch_terminal_delay_sec() -> int:
    return int(
        getattr(settings, 'FETCH_TERMINAL_DELAY_SEC', DEFAULT_FETCH_TERMINAL_DELAY_SEC)
    )


def get_fetch_job_timeout_sec() -> int:
    return int(
        getattr(settings, 'FETCH_JOB_TIMEOUT_SEC', DEFAULT_FETCH_JOB_TIMEOUT_SEC)
    )


def is_service_fetchable(service: Service) -> bool:
    if service.api == 'selfposts':
        return False
    try:
        ServiceFactory.get_service_class(service.api)
    except ValueError:
        return False
    return True


def get_effective_interval_sec(service: Service) -> int | None:
    if service.fetch_interval_sec is not None:
        return service.fetch_interval_sec

    if not is_service_fetchable(service):
        return None

    default_interval = get_default_fetch_interval_sec()
    service_class = ServiceFactory.get_service_class(service.api)
    limit_sec = getattr(service_class, 'limit_sec', None)
    if isinstance(limit_sec, int) and limit_sec >= 0:
        return max(default_interval, limit_sec)
    return default_interval


def compute_next_fetch_at(
    service: Service,
    *,
    now: Any | None = None,
    reference_time: Any | None = None,
) -> Any | None:
    if not service.active or not is_service_fetchable(service):
        return None

    interval_sec = get_effective_interval_sec(service)
    if interval_sec is None:
        return None

    base_time = reference_time or service.last_checked or now or timezone.now()
    return base_time + timedelta(seconds=interval_sec)


def classify_fetch_failure(error: Exception) -> FetchFailure:
    """Whether retrying soon can help, and why the fetch failed.

    A FetchError says so itself. Any other exception counts as retryable,
    because a provider bug may not trigger on the next payload.
    """
    if isinstance(error, httpclient.FetchError):
        kind = (
            ServiceFetchState.FAILURE_RETRYABLE
            if error.retryable
            else ServiceFetchState.FAILURE_TERMINAL
        )
        return FetchFailure(kind, error.category, error.retry_after_sec)
    return FetchFailure(ServiceFetchState.FAILURE_RETRYABLE, 'unexpected')


def compute_retry_at(
    service: Service,
    failure: FetchFailure,
    attempt: int,
    *,
    now: Any,
) -> Any | None:
    """When to fetch `service` again after its `attempt`-th failure in a row.

    A retryable failure waits base * 2^(attempt - 1) seconds, capped at the
    service's interval. A terminal failure waits the longer of the interval
    and the terminal delay. A longer Retry-After from the remote wins.
    """
    if not service.active or not is_service_fetchable(service):
        return None
    interval_sec = get_effective_interval_sec(service)
    if interval_sec is None:
        return None

    if failure.kind == ServiceFetchState.FAILURE_TERMINAL:
        delay_sec = max(interval_sec, get_fetch_terminal_delay_sec())
    else:
        doublings = min(max(attempt, 1) - 1, MAX_RETRY_DOUBLINGS)
        delay_sec = min(get_fetch_retry_base_sec() * 2**doublings, interval_sec)
    if failure.retry_after_sec is not None:
        delay_sec = max(delay_sec, failure.retry_after_sec)
    return now + timedelta(seconds=delay_sec)


def describe_failure_backoff(state: ServiceFetchState | None) -> str:
    """A status-tab note on how repeated failures change the schedule."""
    if state is None or not state.consecutive_failures:
        return ''
    count = state.consecutive_failures
    if state.failure_kind == ServiceFetchState.FAILURE_TERMINAL:
        return ngettext(
            'Failed %(count)d time in a row. The error does not look '
            'temporary, so fetches are slowed down.',
            'Failed %(count)d times in a row. The error does not look '
            'temporary, so fetches are slowed down.',
            count,
        ) % {'count': count}
    return ngettext(
        'Failed %(count)d time in a row. Retrying sooner than usual.',
        'Failed %(count)d times in a row. Retrying sooner than usual.',
        count,
    ) % {'count': count}


def ensure_fetch_state(service: Service) -> ServiceFetchState:
    state, _ = ServiceFetchState.objects.get_or_create(service=service)
    return state


def sync_service_schedule(service: Service, *, now: Any | None = None) -> Service:
    now = now or timezone.now()
    state = ensure_fetch_state(service)
    next_fetch_at = compute_next_fetch_at(service, now=now)

    service.next_fetch_at = next_fetch_at
    update_fields = ['next_fetch_at']

    if not service.active or not is_service_fetchable(service):
        if state.status not in (
            ServiceFetchState.STATUS_RUNNING,
            ServiceFetchState.STATUS_QUEUED,
        ):
            state.status = ServiceFetchState.STATUS_IDLE
            state.trigger = ''
            state.worker_token = ''
            state.triggered_by_user = None
            state.save(
                update_fields=['status', 'trigger', 'worker_token', 'triggered_by_user']
            )

    service.save(update_fields=update_fields)
    return service


def recover_abandoned_fetch_states(*, now: Any | None = None) -> None:
    now = now or timezone.now()
    ServiceFetchState.objects.filter(status=ServiceFetchState.STATUS_RUNNING).update(
        status=ServiceFetchState.STATUS_FAILED,
        finished_at=now,
        last_failed_at=now,
        last_result='Fetch interrupted.',
        last_error='Worker stopped before fetch completed.',
        consecutive_failures=F('consecutive_failures') + 1,
        failure_kind=ServiceFetchState.FAILURE_RETRYABLE,
        failure_category='interrupted',
        worker_token='',
    )


def initialize_missing_schedules(*, now: Any | None = None) -> None:
    now = now or timezone.now()
    recover_abandoned_fetch_states(now=now)
    for service in Service.objects.filter(active=True):
        if not is_service_fetchable(service):
            continue
        state = ensure_fetch_state(service)
        if state.status in (
            ServiceFetchState.STATUS_RUNNING,
            ServiceFetchState.STATUS_QUEUED,
        ):
            continue

        expected_next_fetch_at = compute_next_fetch_at(
            service,
            now=now,
            reference_time=service.last_checked or now,
        )
        # Do not move an already-scheduled retry backwards. A fetch completion
        # schedules from finished_at, which can legitimately be later than
        # last_checked when the underlying API did not advance last_checked.
        if service.next_fetch_at is None or (
            expected_next_fetch_at is not None
            and service.next_fetch_at < expected_next_fetch_at
        ):
            service.next_fetch_at = expected_next_fetch_at
            service.save(update_fields=['next_fetch_at'])


def send_worker_wake_signal() -> bool:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        socket_path = get_worker_socket()
        sock.connect(socket_path)
        sock.send(WAKE_PAYLOAD)
        return True
    except OSError as exc:
        logger.warning(
            'Unable to wake fetch worker at %s: %s',
            get_worker_socket(),
            exc,
        )
        return False
    finally:
        sock.close()


_STATE_TIMESTAMPS = (
    'requested_at',
    'started_at',
    'finished_at',
    'last_succeeded_at',
    'last_failed_at',
)


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def serialize_fetch_state(
    service: Service,
    state: ServiceFetchState | None = None,
) -> dict[str, Any]:
    if state is None:
        state = ServiceFetchState.objects.filter(service=service).first()

    payload: dict[str, Any] = {
        'service_id': service.pk,
        'can_fetch': is_service_fetchable(service),
        'status': state.status if state else ServiceFetchState.STATUS_IDLE,
        'trigger': state.trigger if state else '',
    }
    # getattr covers the no-state case: every timestamp reads back as None.
    payload.update(
        (name, _isoformat(getattr(state, name, None))) for name in _STATE_TIMESTAMPS
    )
    payload['last_result'] = state.last_result if state else ''
    payload['last_error'] = state.last_error if state else ''
    payload['consecutive_failures'] = state.consecutive_failures if state else 0
    payload['failure_kind'] = state.failure_kind if state else ''
    payload['failure_category'] = state.failure_category if state else ''
    payload['failure_note'] = describe_failure_backoff(state)
    payload['next_fetch_at'] = _isoformat(service.next_fetch_at)
    payload['effective_interval_sec'] = get_effective_interval_sec(service)
    return payload


def enqueue_manual_fetch(
    service: Service,
    *,
    triggered_by_user: User | None = None,
    wake_worker: bool = True,
) -> EnqueueResult:
    now = timezone.now()
    with transaction.atomic():
        state, _ = ServiceFetchState.objects.select_for_update().get_or_create(
            service=service
        )
        if state.status in (
            ServiceFetchState.STATUS_QUEUED,
            ServiceFetchState.STATUS_RUNNING,
        ):
            queued = False
        else:
            state.status = ServiceFetchState.STATUS_QUEUED
            state.trigger = ServiceFetchState.TRIGGER_MANUAL
            state.requested_at = now
            state.started_at = None
            state.triggered_by_user = triggered_by_user
            state.worker_token = ''
            state.save()
            queued = True

        if service.next_fetch_at is None and is_service_fetchable(service):
            service.next_fetch_at = compute_next_fetch_at(
                service,
                now=now,
                reference_time=service.last_checked or now,
            )
            service.save(update_fields=['next_fetch_at'])

    wake_sent = send_worker_wake_signal() if wake_worker else False
    return EnqueueResult(state=state, queued=queued, wake_sent=wake_sent)


def _get_public_latest_entry() -> Entry | None:
    return (
        Entry.objects.filter(service__public=True).order_by('-date_published').first()
    )


def _update_state_success(
    state_id: int | None,
    worker_token: str,
    service: Service,
    *,
    finished_at: Any,
) -> None:
    if not _record_outcome(
        state_id,
        worker_token,
        status=ServiceFetchState.STATUS_SUCCEEDED,
        finished_at=finished_at,
        last_succeeded_at=finished_at,
        last_result='Fetch completed.',
        last_error='',
        consecutive_failures=0,
        failure_kind='',
        failure_category='',
    ):
        return
    service.next_fetch_at = compute_next_fetch_at(
        service,
        now=finished_at,
        reference_time=finished_at,
    )
    service.save(update_fields=['next_fetch_at'])


def _update_state_failure(
    state_id: int | None,
    worker_token: str,
    service: Service,
    *,
    finished_at: Any,
    error: Exception,
) -> None:
    failure = classify_fetch_failure(error)
    last_result, last_error = _describe_fetch_failure(error)
    if not _record_outcome(
        state_id,
        worker_token,
        status=ServiceFetchState.STATUS_FAILED,
        finished_at=finished_at,
        last_failed_at=finished_at,
        last_result=last_result,
        last_error=last_error,
        consecutive_failures=F('consecutive_failures') + 1,
        failure_kind=failure.kind,
        failure_category=failure.category,
    ):
        return
    attempt = 1
    if state_id is not None:
        attempt = ServiceFetchState.objects.values_list(
            'consecutive_failures', flat=True
        ).get(id=state_id)
    service.next_fetch_at = compute_retry_at(service, failure, attempt, now=finished_at)
    service.save(update_fields=['next_fetch_at'])


def _record_outcome(state_id: int | None, worker_token: str, **fields: Any) -> bool:
    """Store a job's outcome, and say whether the job may reschedule its service.

    The UPDATE matches only while the job still holds its worker token, and
    clears the token. The worker clears it itself when it gives up on a job,
    for example after a timeout, so a fetch that finishes after that changes
    nothing. One UPDATE statement, rather than a read then a write, also waits
    for SQLite's write lock instead of failing with "database is locked".
    A fetch without a state, as run from the command line, always reschedules.
    """
    if state_id is None:
        return True
    return bool(
        ServiceFetchState.objects.filter(id=state_id, worker_token=worker_token).update(
            worker_token='', **fields
        )
    )


def _describe_fetch_failure(error: Exception) -> tuple[str, str]:
    if isinstance(error, httpclient.FetchError):
        return error.user_message, error.detail
    detail = str(error) or 'Unexpected fetch error.'
    return 'Unexpected fetch error.', detail


def run_service_fetch(
    service: Service,
    *,
    state_id: int | None = None,
    worker_token: str = '',
    trigger: str = ServiceFetchState.TRIGGER_MANUAL,
    verbose: int = 0,
    force_overwrite: bool = False,
) -> None:
    close_old_connections()
    before = _get_public_latest_entry()
    try:
        api = ServiceFactory.create_service(service, verbose, force_overwrite)
        api.run()
        logger.info(
            'Imported service %s (%s): %s',
            service.pk,
            service.api,
            api.last_result.summary(),
        )
        service.refresh_from_db()
        finished_at = timezone.now()
        _update_state_success(state_id, worker_token, service, finished_at=finished_at)

        after = _get_public_latest_entry()
        if after and before != after:
            websub.publish(verbose=verbose)
    except Exception as exc:
        logger.exception('Fetch failed for service %s (%s).', service.pk, service.api)
        service.refresh_from_db()
        finished_at = timezone.now()
        _update_state_failure(
            state_id,
            worker_token,
            service,
            finished_at=finished_at,
            error=exc,
        )
        raise
    finally:
        connections.close_all()


def run_services(
    filters: dict[str, Any],
    *,
    force_check: bool = False,
    force_overwrite: bool = False,
    verbose: int = 0,
    max_workers: int = 10,
) -> None:
    services = list(Service.objects.filter(**filters))
    if not services:
        return

    def _should_run(service: Service) -> bool:
        if force_check:
            return True
        interval_sec = get_effective_interval_sec(service)
        if interval_sec is None or not service.last_checked:
            return True
        return timezone.now() >= service.last_checked + timedelta(seconds=interval_sec)

    runnable = [
        service
        for service in services
        if is_service_fetchable(service) and _should_run(service)
    ]
    if not runnable:
        return

    with ThreadPoolExecutor(max_workers=min(max_workers, len(runnable))) as executor:
        futures = [
            executor.submit(
                run_service_fetch,
                service,
                trigger=ServiceFetchState.TRIGGER_MANUAL,
                verbose=verbose,
                force_overwrite=force_overwrite,
            )
            for service in runnable
        ]
        wait(futures)
        for future in futures:
            future.result()


def get_fetch_status_payload(service_ids: list[int] | None = None) -> dict[str, Any]:
    services = Service.objects.all().order_by('id')
    if service_ids is not None:
        services = services.filter(id__in=service_ids)
    services = services.select_related('fetch_state')
    return {
        'services': {
            str(service.pk): serialize_fetch_state(service) for service in services
        }
    }


def claim_runnable_jobs(
    worker_token: str,
    *,
    now: Any | None = None,
) -> list[tuple[int | None, int]]:
    now = now or timezone.now()
    initialize_missing_schedules(now=now)
    claimed: list[tuple[int | None, int]] = []

    with transaction.atomic():
        manual_states = list(
            ServiceFetchState.objects.select_for_update()
            .select_related('service')
            .filter(status=ServiceFetchState.STATUS_QUEUED)
            .order_by('requested_at', 'service_id')
        )
        for state in manual_states:
            if not is_service_fetchable(state.service):
                state.status = ServiceFetchState.STATUS_IDLE
                state.trigger = ''
                state.worker_token = ''
                state.save(update_fields=['status', 'trigger', 'worker_token'])
                continue

            state.status = ServiceFetchState.STATUS_RUNNING
            state.started_at = now
            state.worker_token = worker_token
            state.save(update_fields=['status', 'started_at', 'worker_token'])
            claimed.append((state.pk, state.service.pk))

        due_services = list(
            Service.objects.select_for_update()
            .filter(active=True)
            .exclude(api='selfposts')
            .filter(Q(next_fetch_at__lte=now))
            .order_by('next_fetch_at', 'id')
        )
        for service in due_services:
            state, _ = ServiceFetchState.objects.select_for_update().get_or_create(
                service=service
            )
            if state.status in (
                ServiceFetchState.STATUS_QUEUED,
                ServiceFetchState.STATUS_RUNNING,
            ):
                continue

            state.status = ServiceFetchState.STATUS_RUNNING
            state.trigger = ServiceFetchState.TRIGGER_SCHEDULE
            state.requested_at = now
            state.started_at = now
            state.triggered_by_user = None
            state.worker_token = worker_token
            state.save()
            claimed.append((state.pk, service.pk))

    unique_claimed: list[tuple[int | None, int]] = []
    seen: set[int] = set()
    for state_id, service_id in claimed:
        if service_id in seen:
            continue
        unique_claimed.append((state_id, service_id))
        seen.add(service_id)
    return unique_claimed


def get_next_wait_timeout(*, now: Any | None = None) -> float | None:
    now = now or timezone.now()
    if ServiceFetchState.objects.filter(
        status=ServiceFetchState.STATUS_QUEUED
    ).exists():
        return 0.0

    blocked_service_ids = ServiceFetchState.objects.filter(
        status__in=(
            ServiceFetchState.STATUS_QUEUED,
            ServiceFetchState.STATUS_RUNNING,
        )
    ).values_list('service_id', flat=True)

    next_due = (
        Service.objects.filter(active=True)
        .exclude(api='selfposts')
        .exclude(id__in=blocked_service_ids)
        .filter(next_fetch_at__isnull=False)
        .order_by('next_fetch_at')
        .values_list('next_fetch_at', flat=True)
        .first()
    )
    if next_due is None:
        return None

    delta = (next_due - now).total_seconds()
    return max(delta, 0.0)


class FetchWorker:
    def __init__(
        self,
        *,
        socket_path: str | None = None,
        max_workers: int | None = None,
        verbose: int = 0,
        job_timeout_sec: float | None = None,
    ):
        self.socket_path = socket_path or get_worker_socket()
        self.max_workers = max_workers or get_worker_pool_size()
        self.verbose = verbose
        self.job_timeout_sec = job_timeout_sec or get_fetch_job_timeout_sec()
        self.socket: socket.socket | None = None
        self.last_processed_jobs: list[ProcessedFetchJob] = []

    def open_socket(self) -> socket.socket:
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        sock.bind(self.socket_path)
        os.chmod(self.socket_path, 0o666)
        self.socket = sock
        return sock

    def close_socket(self) -> None:
        if self.socket is not None:
            self.socket.close()
            self.socket = None
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)

    def drain_socket(self) -> None:
        if self.socket is None:
            return
        while True:
            ready, _, _ = select.select([self.socket], [], [], 0)
            if not ready:
                return
            try:
                self.socket.recv(1024)
            except OSError:
                return

    def initialize_missing_schedules(self) -> None:
        initialize_missing_schedules()

    def get_next_wait_timeout(self) -> float | None:
        return get_next_wait_timeout()

    def run_ready_jobs(self) -> int:
        close_old_connections()
        worker_token = uuid.uuid4().hex
        self.last_processed_jobs = []
        try:
            claimed = claim_runnable_jobs(worker_token)
            if not claimed:
                return 0

            state_ids = [
                state_id for state_id, _service_id in claimed if state_id is not None
            ]
            state_map = {
                state.pk: state
                for state in ServiceFetchState.objects.select_related('service').filter(
                    id__in=state_ids
                )
                if state.pk is not None
            }
            self.last_processed_jobs = [
                ProcessedFetchJob(
                    service_id=service_id,
                    service_name=state_map[state_id].service.name,
                    trigger=state_map[state_id].trigger
                    or ServiceFetchState.TRIGGER_SCHEDULE,
                )
                for state_id, service_id in claimed
                if state_id is not None and state_id in state_map
            ]

            jobs = [
                _FetchJob(state_id, Service.objects.get(pk=service_id))
                for state_id, service_id in claimed
            ]
            self._run_jobs(jobs, worker_token)
            return len(claimed)
        except DatabaseError:
            logger.exception('Fetch worker database cycle failed.')
            return 0
        finally:
            connections.close_all()

    def _run_jobs(self, jobs: list[_FetchJob], worker_token: str) -> None:
        """Fetch `jobs`, at most `max_workers` at a time, each with a deadline.

        A job still running at its deadline is recorded as timed out and no
        longer counts toward `max_workers`. Python cannot stop its thread, so
        it keeps running in the background; it can no longer record anything.
        """
        finished: queue.Queue[tuple[int, BaseException | None]] = queue.Queue()
        waiting = list(jobs)
        running: dict[int, tuple[_FetchJob, float]] = {}
        while waiting or running:
            while waiting and len(running) < self.max_workers:
                job = waiting.pop(0)
                running[job.service.pk] = (
                    job,
                    time.monotonic() + self.job_timeout_sec,
                )
                self._start_job(job, worker_token, finished)
            next_deadline = min(deadline for _, deadline in running.values())
            try:
                service_id, error = finished.get(
                    timeout=max(next_deadline - time.monotonic(), 0)
                )
            except queue.Empty:
                self._abandon_overdue_jobs(running, worker_token)
                continue
            if running.pop(service_id, None) is not None and error is not None:
                # run_service_fetch already logged and recorded the failure,
                # so a failed service must not stop the worker for the others.
                logger.warning(
                    'Fetch job for service %s ended with %s: %s',
                    service_id,
                    type(error).__name__,
                    error,
                )

    def _start_job(
        self,
        job: _FetchJob,
        worker_token: str,
        finished: queue.Queue[tuple[int, BaseException | None]],
    ) -> None:
        def target() -> None:
            error: BaseException | None = None
            try:
                run_service_fetch(
                    job.service,
                    state_id=job.state_id,
                    worker_token=worker_token,
                    verbose=self.verbose,
                    trigger=ServiceFetchState.TRIGGER_MANUAL,
                )
            except Exception as exc:
                error = exc
            finally:
                finished.put((job.service.pk, error))

        threading.Thread(
            target=target,
            name='fetch-service-%s' % job.service.pk,
            daemon=True,
        ).start()

    def _abandon_overdue_jobs(
        self, running: dict[int, tuple[_FetchJob, float]], worker_token: str
    ) -> None:
        now = time.monotonic()
        for service_id, (job, deadline) in list(running.items()):
            if deadline > now:
                continue
            del running[service_id]
            logger.warning(
                'Fetch job for service %s did not finish within %g seconds.',
                service_id,
                self.job_timeout_sec,
            )
            _update_state_failure(
                job.state_id,
                worker_token,
                job.service,
                finished_at=timezone.now(),
                error=httpclient.build_fetch_error(
                    category='timeout',
                    detail='The fetch did not finish within %g seconds.'
                    % self.job_timeout_sec,
                    retryable=True,
                    user_message='Fetch timed out.',
                ),
            )

    def serve(self, stop_event: threading.Event | None = None) -> None:
        sock = self.open_socket()
        try:
            while True:
                if stop_event is not None and stop_event.is_set():
                    return
                self.initialize_missing_schedules()
                timeout = self.get_next_wait_timeout()
                ready, _, _ = select.select([sock], [], [], timeout)
                if ready:
                    self.drain_socket()
                if stop_event is not None and stop_event.is_set():
                    return
                self.run_ready_jobs()
        finally:
            self.close_socket()
