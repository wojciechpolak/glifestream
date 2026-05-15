from __future__ import annotations

import datetime
import sys
from unittest.mock import patch

import pytest
from django.utils import timezone

from glifestream.fetching import ProcessedFetchJob
import worker
from glifestream.stream.models import Entry


def _aware(year: int, month: int, day: int, hour: int, minute: int) -> datetime.datetime:
    return timezone.make_aware(datetime.datetime(year, month, day, hour, minute))


def test_cron_schedule_matches_old_sunday_cleanup_slot():
    schedule = worker.CronSchedule.parse('5 9 * * 0')

    assert schedule.matches(_aware(2026, 5, 17, 9, 5))
    assert not schedule.matches(_aware(2026, 5, 17, 9, 6))
    assert not schedule.matches(_aware(2026, 5, 18, 9, 5))


def test_cron_schedule_next_after_supports_names_and_steps():
    schedule = worker.CronSchedule.parse('*/15 9-10 * jan mon-fri')

    assert schedule.next_after(_aware(2026, 1, 5, 9, 0)) == _aware(2026, 1, 5, 9, 15)


def test_preprocess_cli_args_supports_compact_verbose_level():
    assert worker._preprocess_cli_args(['--daemon', '-v0']) == ['--daemon', '--verbose=0']
    assert worker._preprocess_cli_args(['-v', '--silent']) == ['-v', '--silent']


def test_configure_library_logging_quiet_by_default():
    httpx_logger = worker.logging.getLogger('httpx')
    httpcore_logger = worker.logging.getLogger('httpcore')
    httpx_previous = httpx_logger.level
    httpcore_previous = httpcore_logger.level

    try:
        worker._configure_library_logging(verbose=0)

        assert httpx_logger.level == worker.logging.WARNING
        assert httpcore_logger.level == worker.logging.WARNING
    finally:
        httpx_logger.setLevel(httpx_previous)
        httpcore_logger.setLevel(httpcore_previous)


def test_configure_library_logging_enables_http_details_with_verbose():
    httpx_logger = worker.logging.getLogger('httpx')
    httpcore_logger = worker.logging.getLogger('httpcore')
    httpx_previous = httpx_logger.level
    httpcore_previous = httpcore_logger.level

    try:
        worker._configure_library_logging(verbose=1)

        assert httpx_logger.level == worker.logging.INFO
        assert httpcore_logger.level == worker.logging.INFO
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

    worker.run_maintenance_args(['--only-inactive', '--delete-old=80'])

    assert not Entry.objects.filter(pk=old_entry.pk).exists()


def test_worker_daemon_runs_due_maintenance_job(settings):
    settings.WORKER_MAINTENANCE_JOBS = [
        {
            'name': 'cleanup',
            'schedule': '0 0 * * *',
            'args': ['--delete-old=365'],
        }
    ]
    daemon = worker.WorkerDaemon(max_workers=1, verbose=0)
    now = timezone.now().replace(second=0, microsecond=0)
    daemon.maintenance_jobs[0].next_run_at = now - datetime.timedelta(minutes=1)

    with patch('worker.run_maintenance_args') as run_maintenance_args:
        count = daemon._run_due_maintenance_jobs(now=now)

    assert count == 1
    run_maintenance_args.assert_called_once_with(('--delete-old=365',), verbose=0)
    assert daemon.maintenance_jobs[0].next_run_at > now


def test_worker_daemon_respects_lifecycle_logs_flag(settings, capsys):
    settings.WORKER_MAINTENANCE_JOBS = []
    worker.WorkerDaemon(max_workers=1, verbose=0, lifecycle_logs=False)

    captured = capsys.readouterr()
    assert captured.out == ''


def test_worker_daemon_describes_processed_fetch_job(settings):
    settings.WORKER_MAINTENANCE_JOBS = []
    daemon = worker.WorkerDaemon(max_workers=1, verbose=0, lifecycle_logs=False)
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
    daemon = worker.WorkerDaemon(max_workers=1, verbose=0, lifecycle_logs=True)
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
    daemon = worker.WorkerDaemon(max_workers=1, verbose=0, lifecycle_logs=False)
    now = _aware(2026, 5, 15, 18, 57)

    message = daemon._describe_sleep(15.3, now=now)

    assert message == 'sleeping for 15.3s until 2026-05-15 18:57:15 CEST'
    assert daemon.fetch_worker.socket_path not in message


def test_run_daemon_handles_keyboard_interrupt_cleanly(monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['worker.py', '--daemon'])
    monkeypatch.setenv('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')

    with patch('worker.WorkerDaemon') as daemon_cls:
        daemon = daemon_cls.return_value
        daemon.serve.side_effect = KeyboardInterrupt

        with pytest.raises(SystemExit) as excinfo:
            worker.run()

    assert excinfo.value.code == 0
    daemon._verbose_print.assert_called_once_with('shutdown requested, exiting')
    captured = capsys.readouterr()
    assert 'KeyboardInterrupt' not in captured.err
