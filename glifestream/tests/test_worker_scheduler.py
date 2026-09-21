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
import logging
import sys
from unittest.mock import patch

import pytest
from django.utils import timezone

from glifestream.fetching import ProcessedFetchJob
from glifestream.worker import cli as worker_cli
from glifestream.worker.daemon import WorkerDaemon
from glifestream.worker.maintenance import run_maintenance_args
from glifestream.worker.schedule import CronSchedule
import worker
from glifestream.stream.models import Entry, Service, ServiceFetchState


def _aware(
    year: int, month: int, day: int, hour: int, minute: int
) -> datetime.datetime:
    return timezone.make_aware(datetime.datetime(year, month, day, hour, minute))


def test_cron_schedule_matches_old_sunday_cleanup_slot():
    schedule = CronSchedule.parse('5 9 * * 0')

    assert schedule.matches(_aware(2026, 5, 17, 9, 5))
    assert not schedule.matches(_aware(2026, 5, 17, 9, 6))
    assert not schedule.matches(_aware(2026, 5, 18, 9, 5))


def test_cron_schedule_next_after_supports_names_and_steps():
    schedule = CronSchedule.parse('*/15 9-10 * jan mon-fri')

    assert schedule.next_after(_aware(2026, 1, 5, 9, 0)) == _aware(2026, 1, 5, 9, 15)


def test_preprocess_cli_args_supports_compact_verbose_level():
    assert worker_cli._preprocess_cli_args(['--daemon', '-v0']) == [
        '--daemon',
        '--verbose=0',
    ]
    assert worker_cli._preprocess_cli_args(['-v', '--silent']) == ['-v', '--silent']


def test_configure_library_logging_quiet_by_default():
    httpx_logger = logging.getLogger('httpx')
    httpcore_logger = logging.getLogger('httpcore')
    httpx_previous = httpx_logger.level
    httpcore_previous = httpcore_logger.level

    try:
        worker_cli._configure_library_logging(verbose=0)

        assert httpx_logger.level == logging.WARNING
        assert httpcore_logger.level == logging.WARNING
    finally:
        httpx_logger.setLevel(httpx_previous)
        httpcore_logger.setLevel(httpcore_previous)


def test_configure_library_logging_enables_http_details_with_verbose():
    httpx_logger = logging.getLogger('httpx')
    httpcore_logger = logging.getLogger('httpcore')
    httpx_previous = httpx_logger.level
    httpcore_previous = httpcore_logger.level

    try:
        worker_cli._configure_library_logging(verbose=1)

        assert httpx_logger.level == logging.INFO
        assert httpcore_logger.level == logging.INFO
    finally:
        httpx_logger.setLevel(httpx_previous)
        httpcore_logger.setLevel(httpcore_previous)


@pytest.mark.django_db
def test_run_maintenance_args_deletes_old_inactive_entries(service):
    service.api = 'webfeed'
    service.public = False
    service.save()
    old_entry = Entry.objects.create(
        service=service,
        title='old',
        link='http://example.com/old',
        guid='old-guid',
        active=False,
    )
    old_entry.date_published = timezone.now() - datetime.timedelta(days=120)
    old_entry.date_inserted = timezone.now() - datetime.timedelta(days=120)
    old_entry.save(update_fields=['date_published', 'date_inserted'])

    run_maintenance_args(['--only-inactive', '--delete-old=80'])

    assert not Entry.objects.filter(pk=old_entry.pk).exists()


def test_worker_daemon_runs_due_maintenance_job(settings):
    settings.WORKER_MAINTENANCE_JOBS = [
        {
            'name': 'cleanup',
            'schedule': '0 0 * * *',
            'args': ['--delete-old=365'],
        }
    ]
    daemon = WorkerDaemon(max_workers=1, verbose=0)
    now = timezone.now().replace(second=0, microsecond=0)
    daemon.maintenance_jobs[0].next_run_at = now - datetime.timedelta(minutes=1)

    with patch(
        'glifestream.worker.daemon.run_maintenance_args'
    ) as run_maintenance_mock:
        count = daemon._run_due_maintenance_jobs(now=now)

    assert count == 1
    run_maintenance_mock.assert_called_once_with(('--delete-old=365',), verbose=0)
    assert daemon.maintenance_jobs[0].next_run_at > now


def test_worker_daemon_respects_lifecycle_logs_flag(settings, capsys):
    settings.WORKER_MAINTENANCE_JOBS = []
    WorkerDaemon(max_workers=1, verbose=0, lifecycle_logs=False)

    captured = capsys.readouterr()
    assert captured.out == ''


def test_worker_daemon_describes_processed_fetch_job(settings):
    settings.WORKER_MAINTENANCE_JOBS = []
    daemon = WorkerDaemon(max_workers=1, verbose=0, lifecycle_logs=False)
    daemon.fetch_worker.last_processed_jobs = [
        ProcessedFetchJob(
            service_id=24,
            service_name='Bluesky',
            trigger='manual',
        )
    ]

    assert (
        daemon._describe_processed_fetch_jobs()
        == 'processed fetch job: #24 "Bluesky" (manual)'
    )


def test_worker_daemon_logs_next_maintenance_only_when_plan_changes(settings, capsys):
    settings.WORKER_MAINTENANCE_JOBS = [
        {
            'name': 'cleanup',
            'schedule': '0 0 * * *',
            'args': ['--delete-old=365'],
        }
    ]
    daemon = WorkerDaemon(max_workers=1, verbose=0, lifecycle_logs=True)
    capsys.readouterr()

    daemon._maybe_log_next_maintenance_plan()
    first = capsys.readouterr()
    assert 'next maintenance: cleanup at ' in first.out

    daemon._maybe_log_next_maintenance_plan()
    second = capsys.readouterr()
    assert second.out == ''

    daemon.maintenance_jobs[0].next_run_at += datetime.timedelta(days=1)
    daemon._maybe_log_next_maintenance_plan()
    third = capsys.readouterr()
    assert 'next maintenance: cleanup at ' in third.out


def test_worker_daemon_sleep_log_does_not_repeat_socket_path(settings):
    settings.WORKER_MAINTENANCE_JOBS = []
    daemon = WorkerDaemon(max_workers=1, verbose=0, lifecycle_logs=False)
    now = _aware(2026, 5, 15, 18, 57)

    message = daemon._describe_sleep(15.3, now=now)

    expected_wake_at = timezone.localtime(
        now + datetime.timedelta(seconds=15.3)
    ).strftime('%Y-%m-%d %H:%M:%S %Z')
    assert message == f'sleeping for 15.3s until {expected_wake_at}'
    assert daemon.fetch_worker.socket_path not in message


def test_run_daemon_handles_keyboard_interrupt_cleanly(monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['worker.py', '--daemon'])
    monkeypatch.setenv('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')

    with patch('glifestream.worker.cli.WorkerDaemon') as daemon_cls:
        daemon = daemon_cls.return_value
        daemon.serve.side_effect = KeyboardInterrupt

        with pytest.raises(SystemExit) as excinfo:
            worker.run()

    assert excinfo.value.code == 0
    daemon._verbose_print.assert_called_once_with('shutdown requested, exiting')
    captured = capsys.readouterr()
    assert 'KeyboardInterrupt' not in captured.err


def make_daemon(settings) -> WorkerDaemon:
    settings.WORKER_MAINTENANCE_JOBS = []
    return WorkerDaemon(max_workers=1, verbose=0, lifecycle_logs=False)


@pytest.mark.django_db
def test_next_fetch_plan_reports_nothing_to_do(settings):
    assert make_daemon(settings)._describe_next_fetch_plan() == 'no scheduled fetches'


@pytest.mark.django_db
def test_next_fetch_plan_announces_a_queued_manual_fetch(settings, service):
    ServiceFetchState.objects.create(
        service=service,
        status=ServiceFetchState.STATUS_QUEUED,
        requested_at=timezone.now(),
    )

    plan = make_daemon(settings)._describe_next_fetch_plan()

    assert plan == 'manual fetch queued: #%d "Test Service"' % service.pk


@pytest.mark.django_db
def test_next_fetch_plan_prefers_the_earliest_queued_request(settings, service):
    later = Service.objects.create(name='Later', api='webfeed', url='http://l/f')
    now = timezone.now()
    ServiceFetchState.objects.create(
        service=later,
        status=ServiceFetchState.STATUS_QUEUED,
        requested_at=now,
    )
    ServiceFetchState.objects.create(
        service=service,
        status=ServiceFetchState.STATUS_QUEUED,
        requested_at=now - datetime.timedelta(minutes=5),
    )

    plan = make_daemon(settings)._describe_next_fetch_plan()

    assert 'Test Service' in plan


@pytest.mark.django_db
def test_next_fetch_plan_describes_the_soonest_schedule(settings, service):
    now = timezone.now()
    service.next_fetch_at = now + datetime.timedelta(minutes=30)
    service.save(update_fields=['next_fetch_at'])

    plan = make_daemon(settings)._describe_next_fetch_plan(now=now)

    assert plan.startswith('next fetch: #%d "Test Service" at ' % service.pk)
    assert '(in 30m 0s)' in plan


@pytest.mark.django_db
def test_next_fetch_plan_clamps_an_overdue_schedule_to_zero(settings, service):
    now = timezone.now()
    service.next_fetch_at = now - datetime.timedelta(hours=1)
    service.save(update_fields=['next_fetch_at'])

    assert '(in 0.000s)' in make_daemon(settings)._describe_next_fetch_plan(now=now)


@pytest.mark.django_db
def test_next_fetch_plan_skips_selfposts_services(settings):
    now = timezone.now()
    notes = Service.objects.create(name='Notes', api='selfposts')
    notes.next_fetch_at = now + datetime.timedelta(minutes=1)
    notes.save(update_fields=['next_fetch_at'])

    assert make_daemon(settings)._describe_next_fetch_plan() == 'no scheduled fetches'


@pytest.mark.django_db
def test_next_fetch_plan_ignores_inactive_services(settings, service):
    service.active = False
    service.next_fetch_at = timezone.now() + datetime.timedelta(minutes=1)
    service.save(update_fields=['active', 'next_fetch_at'])

    assert make_daemon(settings)._describe_next_fetch_plan() == 'no scheduled fetches'


@pytest.mark.parametrize(
    'fetch, maintenance, expected',
    [(None, None, None), (30.0, None, 30.0), (None, 5.0, 5.0), (30.0, 5.0, 5.0)],
)
def test_select_timeout_is_the_nearest_deadline(settings, fetch, maintenance, expected):
    daemon = make_daemon(settings)
    with (
        patch.object(daemon.fetch_worker, 'get_next_wait_timeout', return_value=fetch),
        patch.object(daemon, '_get_next_maintenance_timeout', return_value=maintenance),
    ):
        assert daemon._select_timeout() == expected


@pytest.mark.django_db
@pytest.mark.parametrize('signalled', [True, False])
def test_serve_once_runs_ready_work(settings, signalled):
    daemon = make_daemon(settings)
    worker_ = daemon.fetch_worker
    sock = object()
    with (
        patch.object(worker_, 'initialize_missing_schedules') as init,
        patch.object(worker_, 'get_next_wait_timeout', return_value=1.0),
        patch(
            'glifestream.worker.daemon.select.select',
            return_value=([sock] if signalled else [], [], []),
        ) as select_,
        patch.object(worker_, 'drain_socket') as drain,
        patch.object(worker_, 'run_ready_jobs', return_value=1) as run_jobs,
        patch.object(daemon, '_run_due_maintenance_jobs', return_value=1) as run_mnt,
    ):
        daemon.serve_once(sock)

    init.assert_called_once_with()
    select_.assert_called_once_with([sock], [], [], 1.0)
    assert drain.called is signalled
    run_jobs.assert_called_once_with()
    run_mnt.assert_called_once_with()


def test_serve_closes_the_socket_when_the_loop_stops(settings):
    daemon = make_daemon(settings)
    worker_ = daemon.fetch_worker
    sock = object()
    with (
        patch.object(worker_, 'open_socket', return_value=sock),
        patch.object(worker_, 'close_socket') as close,
        patch.object(
            daemon, 'serve_once', side_effect=[None, None, KeyboardInterrupt]
        ) as serve_once,
    ):
        with pytest.raises(KeyboardInterrupt):
            daemon.serve()

    assert serve_once.call_count == 3
    serve_once.assert_called_with(sock)
    close.assert_called_once_with()


@pytest.mark.parametrize(
    'expression, dow',
    [
        ('0 3 * * 7', {0}),
        ('0 3 * * 5-7', {0, 5, 6}),
        ('0 3 * * 1-7', {0, 1, 2, 3, 4, 5, 6}),
        ('0 3 * * 0,7', {0}),
    ],
)
def test_cron_day_of_week_seven_is_sunday(expression, dow):
    assert CronSchedule.parse(expression).day_of_week.values == frozenset(dow)


@pytest.mark.parametrize(
    'expression',
    [
        '0 3 * *',
        '*/0 * * * *',
        '60 * * * *',
        '5-1 * * * *',
        ', * * * *',
        'x * * * *',
        '0 3 * * fri-sun',
    ],
)
def test_cron_rejects_invalid_expressions(expression):
    with pytest.raises(ValueError):
        CronSchedule.parse(expression)


@pytest.mark.parametrize(
    'expression, when, matches',
    [
        # Both day fields restricted: either one is enough.
        ('0 0 13 * fri', (2026, 2, 13, 0, 0), True),  # Friday the 13th
        ('0 0 13 * fri', (2026, 3, 13, 0, 0), True),  # the 13th, a Friday too
        ('0 0 13 * fri', (2026, 3, 20, 0, 0), True),  # a Friday
        ('0 0 13 * fri', (2026, 3, 14, 0, 0), False),  # neither
        # One restricted: only that one counts.
        ('0 0 13 * *', (2026, 3, 20, 0, 0), False),
        ('0 0 * * fri', (2026, 3, 13, 0, 0), True),
        ('0 0 * * fri', (2026, 3, 14, 0, 0), False),
        ('0 0 * * *', (2026, 3, 14, 0, 0), True),
        ('0 0 * * *', (2026, 3, 14, 0, 1), False),
    ],
)
def test_cron_day_matching_follows_cron_rules(expression, when, matches):
    assert CronSchedule.parse(expression).matches(_aware(*when)) is matches


@pytest.mark.parametrize(
    'args, expected',
    [
        ('--thumbs-list-orphans  --verbose', ('--thumbs-list-orphans', '--verbose')),
        (['--delete-old', 30], ('--delete-old', '30')),
        (None, None),
    ],
)
def test_maintenance_job_from_config_args(args, expected):
    from glifestream.worker.schedule import MaintenanceJob

    config = {'schedule': '0 3 * * *', 'args': args}
    if expected is None:
        with pytest.raises(ValueError, match='list or string'):
            MaintenanceJob.from_config(config, now=timezone.now())
        return

    job = MaintenanceJob.from_config(config, now=timezone.now())
    assert job.args == expected
    assert job.name == '0 3 * * *'


@pytest.mark.parametrize('schedule', [None, '', '   ', 5])
def test_maintenance_job_from_config_needs_a_schedule(schedule):
    from glifestream.worker.schedule import MaintenanceJob

    with pytest.raises(ValueError, match='schedule'):
        MaintenanceJob.from_config({'schedule': schedule}, now=timezone.now())
