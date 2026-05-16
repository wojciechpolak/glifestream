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
import select
import socket
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.contrib.auth.models import User
from django.db import DatabaseError, close_old_connections, connections, transaction
from django.db.models import Q
from django.utils import timezone

from glifestream.apis.factory import ServiceFactory
from glifestream.stream import websub
from glifestream.stream.models import Entry, Service, ServiceFetchState

logger = logging.getLogger(__name__)

WAKE_PAYLOAD = b'wake'
DEFAULT_WORKER_SOCKET = '/tmp/glifestream-worker.sock'
DEFAULT_WORKER_POOL_SIZE = 4
DEFAULT_FETCH_INTERVAL_SEC = 7200


@dataclass(slots=True)
class EnqueueResult:
    state: ServiceFetchState
    queued: bool
    wake_sent: bool


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


def initialize_missing_schedules(*, now: Any | None = None) -> None:
    now = now or timezone.now()
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
        if service.next_fetch_at != expected_next_fetch_at:
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


def serialize_fetch_state(
    service: Service,
    state: ServiceFetchState | None = None,
) -> dict[str, Any]:
    if state is None:
        state = ServiceFetchState.objects.filter(service=service).first()

    effective_interval_sec = get_effective_interval_sec(service)
    status = state.status if state else ServiceFetchState.STATUS_IDLE
    trigger = state.trigger if state else ''

    return {
        'service_id': service.pk,
        'can_fetch': is_service_fetchable(service),
        'status': status,
        'trigger': trigger,
        'requested_at': (
            state.requested_at.isoformat()
            if state and state.requested_at
            else None
        ),
        'started_at': state.started_at.isoformat() if state and state.started_at else None,
        'finished_at': (
            state.finished_at.isoformat() if state and state.finished_at else None
        ),
        'last_succeeded_at': (
            state.last_succeeded_at.isoformat()
            if state and state.last_succeeded_at
            else None
        ),
        'last_failed_at': (
            state.last_failed_at.isoformat() if state and state.last_failed_at else None
        ),
        'last_result': state.last_result if state else '',
        'last_error': state.last_error if state else '',
        'next_fetch_at': (
            service.next_fetch_at.isoformat() if service.next_fetch_at else None
        ),
        'effective_interval_sec': effective_interval_sec,
    }


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
        Entry.objects.filter(service__public=True)
        .order_by('-date_published')
        .first()
    )


def _update_state_success(
    state_id: int | None,
    worker_token: str,
    service: Service,
    *,
    finished_at: Any,
) -> None:
    service.next_fetch_at = compute_next_fetch_at(
        service,
        now=finished_at,
        reference_time=finished_at,
    )
    service.save(update_fields=['next_fetch_at'])

    if state_id is None:
        return

    ServiceFetchState.objects.filter(
        id=state_id, worker_token=worker_token
    ).update(
        status=ServiceFetchState.STATUS_SUCCEEDED,
        finished_at=finished_at,
        last_succeeded_at=finished_at,
        last_result='Fetch completed.',
        last_error='',
        worker_token='',
    )


def _update_state_failure(
    state_id: int | None,
    worker_token: str,
    service: Service,
    *,
    finished_at: Any,
    error: Exception,
) -> None:
    service.next_fetch_at = compute_next_fetch_at(
        service,
        now=finished_at,
        reference_time=finished_at,
    )
    service.save(update_fields=['next_fetch_at'])

    if state_id is None:
        return

    ServiceFetchState.objects.filter(
        id=state_id, worker_token=worker_token
    ).update(
        status=ServiceFetchState.STATUS_FAILED,
        finished_at=finished_at,
        last_failed_at=finished_at,
        last_result='Fetch failed.',
        last_error=str(error),
        worker_token='',
    )


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
            state.save(
                update_fields=['status', 'started_at', 'worker_token']
            )
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
    if ServiceFetchState.objects.filter(status=ServiceFetchState.STATUS_QUEUED).exists():
        return 0.0

    next_due = (
        Service.objects.filter(active=True)
        .exclude(api='selfposts')
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
    ):
        self.socket_path = socket_path or get_worker_socket()
        self.max_workers = max_workers or get_worker_pool_size()
        self.verbose = verbose
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

            state_ids = [state_id for state_id, _service_id in claimed if state_id is not None]
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
                    trigger=state_map[state_id].trigger or ServiceFetchState.TRIGGER_SCHEDULE,
                )
                for state_id, service_id in claimed
                if state_id is not None and state_id in state_map
            ]

            with ThreadPoolExecutor(
                max_workers=min(self.max_workers, len(claimed))
            ) as executor:
                futures = [
                    executor.submit(
                        run_service_fetch,
                        Service.objects.get(pk=service_id),
                        state_id=state_id,
                        worker_token=worker_token,
                        verbose=self.verbose,
                        trigger=ServiceFetchState.TRIGGER_MANUAL,
                    )
                    for state_id, service_id in claimed
                ]
                wait(futures)
                for future in futures:
                    future.result()
            return len(claimed)
        except DatabaseError:
            logger.exception('Fetch worker database cycle failed.')
            return 0
        finally:
            connections.close_all()

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
