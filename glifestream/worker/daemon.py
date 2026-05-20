"""
#  gLifestream Copyright (C) 2009-2026 Wojciech Polak
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

import datetime
import select

from django.conf import settings
from django.utils import timezone

from glifestream.fetching import (
    DEFAULT_FETCH_INTERVAL_SEC,
    FetchWorker,
)
from glifestream.stream.models import Service, ServiceFetchState
from glifestream.worker.config import DEFAULT_WORKER_MAINTENANCE_JOBS
from glifestream.worker.maintenance import run_maintenance_args
from glifestream.worker.schedule import MaintenanceJob


class WorkerDaemon:
    def __init__(
        self,
        *,
        max_workers: int,
        verbose: int = 0,
        lifecycle_logs: bool = True,
        socket_path: str | None = None,
    ):
        self.fetch_worker = FetchWorker(
            max_workers=max_workers,
            verbose=verbose,
            socket_path=socket_path,
        )
        self.verbose = verbose
        self.lifecycle_logs = lifecycle_logs
        self._last_logged_maintenance_plan: tuple[str, datetime.datetime] | None = None
        now = timezone.now()
        self.maintenance_jobs = [
            MaintenanceJob.from_config(config, now=now)
            for config in getattr(
                settings,
                'WORKER_MAINTENANCE_JOBS',
                [dict(job) for job in DEFAULT_WORKER_MAINTENANCE_JOBS],
            )
        ]
        self._verbose_print(
            'daemon started: socket=%s workers=%d default_fetch_interval=%ds maintenance_jobs=%d'
            % (
                self.fetch_worker.socket_path,
                max_workers,
                int(
                    getattr(
                        settings,
                        'FETCH_DEFAULT_INTERVAL_SEC',
                        DEFAULT_FETCH_INTERVAL_SEC,
                    )
                ),
                len(self.maintenance_jobs),
            )
        )
        for job in self.maintenance_jobs:
            self._verbose_print(
                'maintenance scheduled: %s at %s (%s)'
                % (
                    job.name,
                    self._format_dt(job.next_run_at),
                    ' '.join(job.args),
                )
            )

    def _verbose_print(self, message: str) -> None:
        if self.lifecycle_logs:
            print(
                '[%s] daemon: %s' % (self._format_dt(timezone.now()), message),
                flush=True,
            )

    def _format_dt(self, dt: datetime.datetime) -> str:
        return timezone.localtime(dt).strftime('%Y-%m-%d %H:%M:%S %Z')

    def _format_timeout(self, timeout: float | None) -> str:
        if timeout is None:
            return 'indefinitely'
        if timeout < 1:
            return '%.3fs' % timeout
        if timeout < 60:
            return '%.1fs' % timeout
        minutes, seconds = divmod(int(timeout), 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return '%dh %dm %ds' % (hours, minutes, seconds)
        return '%dm %ds' % (minutes, seconds)

    def _describe_next_fetch_plan(
        self, *, now: datetime.datetime | None = None
    ) -> str:
        now = now or timezone.now()
        queued_state = (
            ServiceFetchState.objects.select_related('service')
            .filter(status=ServiceFetchState.STATUS_QUEUED)
            .order_by('requested_at', 'service_id')
            .first()
        )
        if queued_state is not None:
            return 'manual fetch queued: #%d "%s"' % (
                queued_state.service.pk,
                queued_state.service.name,
            )

        next_fetchable: Service | None = None
        for service in (
            Service.objects.filter(active=True, next_fetch_at__isnull=False)
            .order_by('next_fetch_at', 'id')
            .iterator()
        ):
            if service.api == 'selfposts':
                continue
            next_fetchable = service
            break

        if next_fetchable is None or next_fetchable.next_fetch_at is None:
            return 'no scheduled fetches'

        timeout = max((next_fetchable.next_fetch_at - now).total_seconds(), 0.0)
        return 'next fetch: #%d "%s" at %s (in %s)' % (
            next_fetchable.pk,
            next_fetchable.name,
            self._format_dt(next_fetchable.next_fetch_at),
            self._format_timeout(timeout),
        )

    def _describe_next_maintenance_plan(self) -> str:
        next_job = self._get_next_maintenance_job()
        if next_job is None:
            return 'no maintenance jobs'
        timeout = self._get_next_maintenance_timeout()
        return 'next maintenance: %s at %s (in %s)' % (
            next_job.name,
            self._format_dt(next_job.next_run_at),
            self._format_timeout(timeout),
        )

    def _get_next_maintenance_job(self) -> MaintenanceJob | None:
        if not self.maintenance_jobs:
            return None
        return min(self.maintenance_jobs, key=lambda job: job.next_run_at)

    def _maybe_log_next_maintenance_plan(self) -> None:
        next_job = self._get_next_maintenance_job()
        if next_job is None:
            if self._last_logged_maintenance_plan is None:
                self._verbose_print('no maintenance jobs')
            self._last_logged_maintenance_plan = None
            return

        plan_key = (next_job.name, next_job.next_run_at)
        if plan_key == self._last_logged_maintenance_plan:
            return

        self._last_logged_maintenance_plan = plan_key
        self._verbose_print(self._describe_next_maintenance_plan())

    def _get_next_maintenance_timeout(
        self, *, now: datetime.datetime | None = None
    ) -> float | None:
        if not self.maintenance_jobs:
            return None
        now = now or timezone.now()
        next_run_at = min(job.next_run_at for job in self.maintenance_jobs)
        return max((next_run_at - now).total_seconds(), 0.0)

    def _run_due_maintenance_jobs(self, *, now: datetime.datetime | None = None) -> int:
        now = now or timezone.now()
        runs = 0
        for job in self.maintenance_jobs:
            while job.next_run_at <= now:
                self._verbose_print(
                    'running maintenance job: %s (%s)' % (job.name, ' '.join(job.args))
                )
                run_maintenance_args(job.args, verbose=self.verbose)
                job.mark_next_run()
                self._verbose_print(
                    'maintenance rescheduled: %s at %s'
                    % (job.name, self._format_dt(job.next_run_at))
                )
                runs += 1
        return runs

    def _select_timeout(self) -> float | None:
        fetch_timeout = self.fetch_worker.get_next_wait_timeout()
        maintenance_timeout = self._get_next_maintenance_timeout()
        timeouts = [
            timeout
            for timeout in (fetch_timeout, maintenance_timeout)
            if timeout is not None
        ]
        if not timeouts:
            return None
        return min(timeouts)

    def _describe_sleep(
        self,
        timeout: float | None,
        *,
        now: datetime.datetime | None = None,
    ) -> str:
        if timeout is None:
            return 'sleeping indefinitely'
        now = now or timezone.now()
        wake_at = now + datetime.timedelta(seconds=timeout)
        return 'sleeping for %s until %s' % (
            self._format_timeout(timeout),
            self._format_dt(wake_at),
        )

    def _describe_processed_fetch_jobs(self) -> str:
        jobs = self.fetch_worker.last_processed_jobs
        if not jobs:
            return 'processed fetch jobs, but no service details were recorded'
        if len(jobs) == 1:
            job = jobs[0]
            return 'processed fetch job: #%d "%s" (%s)' % (
                job.service_id,
                job.service_name,
                job.trigger or 'scheduled',
            )

        details = ', '.join(
            '#%d "%s" (%s)' % (
                job.service_id,
                job.service_name,
                job.trigger or 'scheduled',
            )
            for job in jobs
        )
        return 'processed %d fetch job(s): %s' % (len(jobs), details)

    def serve(self) -> None:
        sock = self.fetch_worker.open_socket()
        try:
            while True:
                self.fetch_worker.initialize_missing_schedules()
                self._verbose_print(self._describe_next_fetch_plan())
                self._maybe_log_next_maintenance_plan()
                timeout = self._select_timeout()
                self._verbose_print(self._describe_sleep(timeout))
                ready, _, _ = select.select([sock], [], [], timeout)
                if ready:
                    self._verbose_print('woken by socket signal')
                    self.fetch_worker.drain_socket()
                else:
                    self._verbose_print('woken by scheduler timeout')
                fetched = self.fetch_worker.run_ready_jobs()
                if fetched:
                    self._verbose_print(self._describe_processed_fetch_jobs())
                maintenance_runs = self._run_due_maintenance_jobs()
                if maintenance_runs:
                    self._verbose_print(
                        'processed %d maintenance job(s)' % maintenance_runs
                    )
        finally:
            self.fetch_worker.close_socket()
