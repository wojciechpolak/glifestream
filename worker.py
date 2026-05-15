#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
#  gLifestream Copyright (C) 2009, 2010, 2014, 2015, 2021, 2023 Wojciech Polak
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

import datetime
import getopt
import logging
import os
import re
import select
import sys
import time
from dataclasses import dataclass
from typing import Any, Sequence

import django
from django.conf import settings
from django.db import connections
from django.utils import timezone

SITE_ROOT = os.path.dirname(os.path.realpath(__file__))
if 'DJANGO_SETTINGS_MODULE' not in os.environ:
    os.environ['DJANGO_SETTINGS_MODULE'] = 'glifestream.settings'

if hasattr(django, 'setup'):
    django.setup()

from glifestream.apis import mail  # noqa: E402
from glifestream.fetching import (  # noqa: E402
    DEFAULT_FETCH_INTERVAL_SEC,
    DEFAULT_WORKER_POOL_SIZE,
    FetchWorker,
    run_services,
)
from glifestream.stream import media, websub  # noqa: E402
from glifestream.stream.models import (  # noqa: E402
    Service,
    Entry,
    Favorite,
    ServiceFetchState,
)
from glifestream.utils.time import unixnow  # noqa: E402

logger = logging.getLogger(__name__)
NOISY_LIBRARY_LOGGERS = (
    'httpx',
    'httpcore',
)
DEFAULT_WORKER_MAINTENANCE_JOBS = (
    {
        'name': 'delete-inactive-old-entries',
        'schedule': '5 9 * * 0',
        'args': ['--only-inactive', '--delete-old=80'],
    },
    {
        'name': 'delete-old-entries',
        'schedule': '6 9 1 * *',
        'args': ['--delete-old=365'],
    },
    {
        'name': 'delete-orphan-thumbnails',
        'schedule': '7 9 1 * *',
        'args': ['--thumbs-delete-orphans'],
    },
)
CRON_MONTH_NAMES = {
    'jan': 1,
    'feb': 2,
    'mar': 3,
    'apr': 4,
    'may': 5,
    'jun': 6,
    'jul': 7,
    'aug': 8,
    'sep': 9,
    'oct': 10,
    'nov': 11,
    'dec': 12,
}
CRON_DOW_NAMES = {
    'sun': 0,
    'mon': 1,
    'tue': 2,
    'wed': 3,
    'thu': 4,
    'fri': 5,
    'sat': 6,
}


@dataclass(frozen=True)
class CronField:
    values: frozenset[int]
    any_value: bool = False


@dataclass(frozen=True)
class CronSchedule:
    minute: CronField
    hour: CronField
    day_of_month: CronField
    month: CronField
    day_of_week: CronField

    @classmethod
    def parse(cls, expression: str) -> 'CronSchedule':
        parts = expression.split()
        if len(parts) != 5:
            raise ValueError('Cron expression must have 5 fields.')

        return cls(
            minute=_parse_cron_field(parts[0], 0, 59),
            hour=_parse_cron_field(parts[1], 0, 23),
            day_of_month=_parse_cron_field(parts[2], 1, 31),
            month=_parse_cron_field(parts[3], 1, 12, names=CRON_MONTH_NAMES),
            day_of_week=_parse_cron_field(parts[4], 0, 7, names=CRON_DOW_NAMES, is_dow=True),
        )

    def matches(self, when: datetime.datetime) -> bool:
        local_when = timezone.localtime(when)
        cron_dow = (local_when.weekday() + 1) % 7
        dom_matches = local_when.day in self.day_of_month.values
        dow_matches = cron_dow in self.day_of_week.values

        if self.day_of_month.any_value and self.day_of_week.any_value:
            day_matches = True
        elif self.day_of_month.any_value:
            day_matches = dow_matches
        elif self.day_of_week.any_value:
            day_matches = dom_matches
        else:
            day_matches = dom_matches or dow_matches

        return (
            local_when.minute in self.minute.values
            and local_when.hour in self.hour.values
            and local_when.month in self.month.values
            and day_matches
        )

    def next_after(self, when: datetime.datetime) -> datetime.datetime:
        candidate = (when + datetime.timedelta(minutes=1)).replace(
            second=0, microsecond=0
        )
        limit = candidate + datetime.timedelta(days=366)
        while candidate <= limit:
            if self.matches(candidate):
                return candidate
            candidate += datetime.timedelta(minutes=1)
        raise ValueError('Unable to compute next cron occurrence within one year.')


@dataclass
class MaintenanceJob:
    name: str
    schedule: CronSchedule
    args: tuple[str, ...]
    next_run_at: datetime.datetime

    @classmethod
    def from_config(
        cls,
        config: dict[str, Any],
        *,
        now: datetime.datetime,
    ) -> 'MaintenanceJob':
        name = str(config.get('name') or config.get('schedule') or 'maintenance-job')
        schedule_expr = config.get('schedule')
        if not isinstance(schedule_expr, str) or not schedule_expr.strip():
            raise ValueError('Maintenance job schedule must be a non-empty string.')

        args_value = config.get('args', [])
        if isinstance(args_value, str):
            args = tuple(arg for arg in args_value.split() if arg.strip())
        elif isinstance(args_value, list):
            args = tuple(str(arg) for arg in args_value)
        else:
            raise ValueError('Maintenance job args must be a list or string.')

        schedule = CronSchedule.parse(schedule_expr)
        return cls(
            name=name,
            schedule=schedule,
            args=args,
            next_run_at=schedule.next_after(now),
        )

    def mark_next_run(self) -> None:
        self.next_run_at = self.schedule.next_after(self.next_run_at)


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
                DEFAULT_WORKER_MAINTENANCE_JOBS,
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
                    'running maintenance job: %s (%s)'
                    % (job.name, ' '.join(job.args))
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


def _normalize_fetch_filters(fs: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(fs)
    if 'id' in normalized and ',' in str(normalized['id']):
        normalized['id__in'] = [int(item) for item in str(normalized['id']).split(',')]
        del normalized['id']
    if 'api' in normalized and ',' in str(normalized['api']):
        normalized['api__in'] = [item.strip() for item in str(normalized['api']).split(',')]
        del normalized['api']
    return normalized


def _parse_cron_value(
    value: str,
    *,
    names: dict[str, int] | None = None,
    is_dow: bool = False,
) -> int:
    normalized = value.strip().lower()
    if names and normalized in names:
        parsed = names[normalized]
    else:
        parsed = int(normalized)

    if is_dow and parsed == 7:
        return 0
    return parsed


def _parse_cron_field(
    expression: str,
    minimum: int,
    maximum: int,
    *,
    names: dict[str, int] | None = None,
    is_dow: bool = False,
) -> CronField:
    expression = expression.strip()
    if expression == '*':
        return CronField(frozenset(range(minimum, maximum + 1)), any_value=True)

    values: set[int] = set()
    for part in expression.split(','):
        token = part.strip()
        if not token:
            continue
        step = 1
        if '/' in token:
            token, step_expr = token.split('/', 1)
            step = int(step_expr)
            if step <= 0:
                raise ValueError('Cron step must be positive.')

        if token == '*':
            start = minimum
            end = maximum
        elif '-' in token:
            start_expr, end_expr = token.split('-', 1)
            start = _parse_cron_value(
                start_expr, names=names, is_dow=is_dow
            )
            end = _parse_cron_value(end_expr, names=names, is_dow=is_dow)
        else:
            start = _parse_cron_value(token, names=names, is_dow=is_dow)
            end = start

        if start < minimum or end > maximum or start > end:
            raise ValueError('Cron value out of range.')

        values.update(range(start, end + 1, step))

    if not values:
        raise ValueError('Cron field cannot be empty.')

    return CronField(frozenset(values), any_value=False)


def _print_usage() -> None:
    print('Usage: %s [OPTION...]' % sys.argv[0])
    print(
        """%s -- gLifestream worker

  -a, --api=NAME               API name of services to update
  -i, --id=ID                  ID of the service to update
  -l, --list                   List service IDs
  -f, --force-check            Force service check for updates
  -v, --verbose                Increase per-service fetch verbosity
      --verbose=NUM            Set per-service fetch verbosity (0 disables)
      --silent                 Disable daemon lifecycle logs
      --daemon                 Run the long-lived background fetch worker
      --workers=NUM            Maximum concurrent fetches in daemon mode
                               including scheduled maintenance jobs
      --force-overwrite        Force overwriting unmodified entries
      --list-old=DAYS          List entries older than DAYS
      --delete-old=DAYS        Delete entries older than DAYS
      --only-inactive          Match only inactive entries (hidden)
      --thumbs-list-orphans    List orphaned thumbnails
      --thumbs-delete-orphans  Delete orphaned thumbnails
      --websub=ACTION          WebSub's actions: (un)subscribe, list, renew, publish
      --email2post             Post things using e-mail (from stdin)
      --init-files-dirs        Create initial upload/thumb directories and files
"""
        % sys.argv[0]
    )


def _preprocess_cli_args(args: Sequence[str]) -> list[str]:
    normalized: list[str] = []
    for arg in args:
        if re.fullmatch(r'-v\d+', arg):
            normalized.append('--verbose=%s' % arg[2:])
        else:
            normalized.append(arg)
    return normalized


def _configure_library_logging(*, verbose: int) -> None:
    level = logging.INFO if verbose > 0 else logging.WARNING
    for logger_name in NOISY_LIBRARY_LOGGERS:
        logging.getLogger(logger_name).setLevel(level)


def run() -> None:
    try:
        verbose = 0
        lifecycle_logs = True
        list_services = False
        force_check = False
        force_overwrite = False
        list_old: int | None = None
        delete_old: int | None = None
        only_inactive = False
        thumbs: str | None = None
        websub_cmd: str | bool = False
        daemon = False
        daemon_workers = int(
            getattr(
                settings,
                'WORKER_POOL_SIZE',
                DEFAULT_WORKER_POOL_SIZE,
            )
        )
        fs: dict[str, Any] = {}

        try:
            opts, args = getopt.getopt(
                _preprocess_cli_args(sys.argv[1:]),
                'i:a:lvf',
                [
                    'id=',
                    'api=',
                    'list',
                    'verbose',
                    'verbose=',
                    'silent',
                    'force-check',
                    'daemon',
                    'workers=',
                    'force-overwrite',
                    'delete-old=',
                    'list-old=',
                    'only-inactive',
                    'thumbs-list-orphans',
                    'thumbs-delete-orphans',
                    'websub=',
                    'email2post',
                    'init-files-dirs',
                ],
            )
            for o, arg in opts:
                if o in ('-a', '--api'):
                    fs['api'] = arg
                elif o in ('-i', '--id'):
                    fs['id'] = arg
                elif o in ('-l', '--list'):
                    list_services = True
                elif o in ('-v', '--verbose'):
                    if arg:
                        verbose = int(arg)
                        lifecycle_logs = verbose > 0
                    else:
                        verbose += 1
                elif o == '--silent':
                    lifecycle_logs = False
                elif o in ('-f', '--force-check'):
                    force_check = True
                elif o == '--daemon':
                    daemon = True
                elif o == '--workers':
                    daemon_workers = int(arg)
                elif o == '--force-overwrite':
                    force_overwrite = True
                elif o == '--list-old':
                    list_old = int(arg)
                elif o == '--delete-old':
                    delete_old = int(arg)
                elif o == '--only-inactive':
                    only_inactive = True
                elif o == '--thumbs-list-orphans':
                    thumbs = 'list-orphans'
                elif o == '--thumbs-delete-orphans':
                    thumbs = 'delete-orphans'
                elif o == '--websub':
                    websub_cmd = arg
                elif o == '--email2post':
                    sys.exit(email2post())
                elif o == '--init-files-dirs':
                    sys.exit(init_files_dirs())
        except getopt.GetoptError:
            _print_usage()
            sys.exit(0)

        if args:
            _print_usage()
            sys.exit(1)

        _configure_library_logging(verbose=verbose)

        if list_services:
            for service in Service.objects.all().order_by('id'):
                print('%4d "%s"  API=%s' % (service.pk, service.name, service.api))
            sys.exit(0)

        if daemon:
            daemon_runner = WorkerDaemon(
                max_workers=daemon_workers,
                verbose=verbose,
                lifecycle_logs=lifecycle_logs,
            )
            try:
                daemon_runner.serve()
            except KeyboardInterrupt:
                if lifecycle_logs:
                    daemon_runner._verbose_print('shutdown requested, exiting')
            sys.exit(0)

        if websub_cmd:
            if websub_cmd == 'subscribe' and 'id' in fs:
                service = Service.objects.get(id=fs['id'])
                r = websub.subscribe(service, verbose)
                if r['rc'] == 1:
                    print('%s: %s' % (sys.argv[0], r['error']))
                elif r['rc'] == 2:
                    print('%s: Hub not found.' % sys.argv[0])
                elif r['rc'] == 202:
                    print('hub=%s: Accepted for verification.' % r['hub'])
                elif r['rc'] == 204:
                    print('hub=%s: Subscription verified.' % r['hub'])
            elif websub_cmd == 'unsubscribe' and 'id' in fs:
                r = websub.unsubscribe(fs['id'], verbose)
                if r['rc'] == 1:
                    print('%s: No subscription found.' % sys.argv[0])
                elif r['rc'] == 202:
                    print('hub=%s: Accepted for verification.' % r['hub'])
                elif r['rc'] == 204:
                    print('hub=%s: Unsubscribed.' % r['hub'])
                else:
                    print('hub=%s: %s.' % (r['hub'], r['rc']))
            elif websub_cmd == 'renew':
                websub.renew_subscriptions(force=force_check, verbose=verbose)
            elif websub_cmd == 'list':
                websub.list_subs()
            elif websub_cmd == 'publish':
                websub.publish(verbose=verbose)
            else:
                print('%s: Unknown "%s" action.' % (sys.argv[0], websub_cmd))
                sys.exit(1)
            sys.exit(0)

        if thumbs in ('list-orphans', 'delete-orphans'):
            ths = list_orphan_thumbs()
            if thumbs == 'delete-orphans':
                if verbose:
                    print('Files to remove: %d' % len(ths))
                delete_thumb_files(ths)
            else:
                for file in ths:
                    print(file)
            sys.exit(0)

        if list_old or delete_old:
            days = list_old if list_old else delete_old
            assert days is not None
            entries = get_old_entries_queryset(days, only_inactive=only_inactive, filters=fs)
            if list_old:
                for entry in entries:
                    print('%4d "%s" by %s' % (entry.pk, entry.title, entry.author_name))
            elif delete_old:
                entries.delete()
            sys.exit(0)
        else:
            if not force_check or 'id' not in fs:
                fs['active'] = True

        if force_overwrite:
            sel = input(
                'WARNING: This may create thumbnail orphans! Continue Y/N? '
            ).strip()
            if sel != 'Y':
                sys.exit(0)

        fs = _normalize_fetch_filters(fs)
        run_services(
            fs,
            force_check=force_check,
            force_overwrite=force_overwrite,
            verbose=verbose,
        )
    finally:
        connections.close_all()


def email2post():
    api = mail.MailService()
    return api.share(sys.stdin)


def get_old_entries_queryset(
    days: int,
    *,
    only_inactive: bool = False,
    filters: dict[str, Any] | None = None,
):
    fs = dict(filters or {})
    n = time.mktime(unixnow()) - (86400 * days)
    rt = datetime.datetime.fromtimestamp(n, tz=datetime.timezone.utc)
    if 'id' in fs:
        lst = str(fs['id']).split(',')
        if len(lst) > 1:
            fs['service__id__in'] = lst
        else:
            fs['service__id'] = int(lst[0])
        del fs['id']
    elif 'api' in fs:
        lst = str(fs['api']).split(',')
        if len(lst) > 1:
            fs['service__api__in'] = lst
        else:
            fs['service__api'] = lst[0]
        del fs['api']
    fs['service__public'] = False
    fs['protected'] = False
    fs['date_published__lte'] = rt
    fs['date_inserted__lte'] = rt
    if only_inactive:
        fs['active'] = False
    favs = Favorite.objects.all().values('entry')
    return Entry.objects.filter(**fs).exclude(id__in=favs)


def list_orphan_thumbs() -> list[str]:
    ths: dict[str, bool] = {}
    for _root, _dirs, files in os.walk(os.path.join(settings.MEDIA_ROOT, 'thumbs')):
        for file in files:
            if file[0] != '.':
                ths[media.get_thumb_info(file, append_suffix=False)['rel']] = True
    entries = Entry.objects.all()
    for entry in entries:
        thumb_hash = media.get_thumb_hash(entry.link_image)
        t = (
            media.get_thumb_info(thumb_hash, append_suffix=False)['rel']
            if thumb_hash
            else ''
        )
        if t in ths:
            del ths[t]
        for thumb_hash in re.findall(r'\[GLS-THUMBS\]/([a-z0-9\.]+)', entry.content):
            t = media.get_thumb_info(thumb_hash, append_suffix=False)['rel']
            if t in ths:
                del ths[t]
    return sorted(ths)


def delete_thumb_files(files: Sequence[str]) -> None:
    for file in files:
        os.remove(os.path.join(settings.MEDIA_ROOT, file))


def run_maintenance_args(args: Sequence[str], *, verbose: int = 0) -> None:
    list_old: int | None = None
    delete_old: int | None = None
    only_inactive = False
    thumbs: str | None = None
    filters: dict[str, Any] = {}

    opts, extras = getopt.getopt(
        list(args),
        'i:a:',
        [
            'id=',
            'api=',
            'list-old=',
            'delete-old=',
            'only-inactive',
            'thumbs-list-orphans',
            'thumbs-delete-orphans',
        ],
    )
    if extras:
        raise ValueError('Unexpected maintenance args: %s' % ' '.join(extras))

    for option, arg in opts:
        if option in ('-a', '--api'):
            filters['api'] = arg
        elif option in ('-i', '--id'):
            filters['id'] = arg
        elif option == '--list-old':
            list_old = int(arg)
        elif option == '--delete-old':
            delete_old = int(arg)
        elif option == '--only-inactive':
            only_inactive = True
        elif option == '--thumbs-list-orphans':
            thumbs = 'list-orphans'
        elif option == '--thumbs-delete-orphans':
            thumbs = 'delete-orphans'

    if thumbs:
        files = list_orphan_thumbs()
        if thumbs == 'delete-orphans':
            if verbose:
                print('Files to remove: %d' % len(files))
            delete_thumb_files(files)
        else:
            for file in files:
                print(file)
        return

    if list_old or delete_old:
        days = list_old if list_old else delete_old
        assert days is not None
        queryset = get_old_entries_queryset(
            days,
            only_inactive=only_inactive,
            filters=filters,
        )
        if list_old:
            for entry in queryset:
                print('%4d "%s" by %s' % (entry.pk, entry.title, entry.author_name))
        else:
            queryset.delete()
        return

    raise ValueError('Maintenance job must specify a cleanup action.')


def init_files_dirs():
    """Create initial directories and files."""

    upload = os.path.join(settings.MEDIA_ROOT, 'upload')
    _create_dir(upload)

    thumbs = os.path.join(settings.MEDIA_ROOT, 'thumbs')
    _create_dir(thumbs)

    for i in range(0, 10):
        _create_dir(os.path.join(thumbs, str(i)))
    for i in 'abcdef':
        _create_dir(os.path.join(thumbs, i))

    print("""
Make sure that 'static/thumbs/*' and 'static/upload' directories exist
and all have write permissions by your webserver.
""")

    template_dir = settings.TEMPLATES[0]['DIRS'][0]
    template_files = (
        'user-about.html',
        'user-copyright.html',
        'user-scripts.js',
    )
    try:
        for i in template_files:
            file = os.path.join(template_dir, i)
            if not os.path.isfile(file):
                print("Creating empty file '%s'" % file)
                open(file, 'w', encoding='utf-8').close()
    except Exception as exc:
        print(exc)
        return 1

    return 0


def _create_dir(d, verbose=True):
    if not os.path.isdir(d):
        if verbose:
            print("Creating directory '%s'" % d)
        os.mkdir(d)


if __name__ == '__main__':
    run()
