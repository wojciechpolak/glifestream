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

import getopt
import logging
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Sequence

from django.conf import settings
from django.db import connections

from glifestream.apis import mail
from glifestream.fetching import DEFAULT_WORKER_POOL_SIZE, run_services
from glifestream.stream import websub
from glifestream.stream.models import Service
from glifestream.worker.daemon import WorkerDaemon
from glifestream.worker.init_files import init_files_dirs
from glifestream.worker.maintenance import (
    MaintenanceCommand,
    build_maintenance_command,
    execute_maintenance_command,
)

NOISY_LIBRARY_LOGGERS = (
    'httpx',
    'httpcore',
)


class WorkerCommandKind(str, Enum):
    USAGE = 'usage'
    DAEMON = 'daemon'
    FETCH = 'fetch'
    CLEANUP = 'cleanup'
    WEBSUB = 'websub'
    EMAIL2POST = 'email2post'
    INIT_FILES = 'init_files'
    LIST_SERVICES = 'list_services'


@dataclass(frozen=True)
class WorkerCommand:
    kind: WorkerCommandKind
    filters: dict[str, Any] = field(default_factory=dict)
    verbose: int = 0
    lifecycle_logs: bool = True
    daemon_workers: int = 0
    force_check: bool = False
    force_overwrite: bool = False
    cleanup_command: MaintenanceCommand | None = None
    websub_action: str | None = None
    usage_exit_code: int = 0


def _print_usage(prog_name: str) -> None:
    print('Usage: %s [OPTION...]' % prog_name)
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
        % prog_name
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


def _normalize_fetch_filters(fs: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(fs)
    if 'id' in normalized and ',' in str(normalized['id']):
        normalized['id__in'] = [int(item) for item in str(normalized['id']).split(',')]
        del normalized['id']
    if 'api' in normalized and ',' in str(normalized['api']):
        normalized['api__in'] = [item.strip() for item in str(normalized['api']).split(',')]
        del normalized['api']
    return normalized


def parse_legacy_command(argv: Sequence[str]) -> WorkerCommand:
    verbose = 0
    lifecycle_logs = True
    list_services = False
    force_check = False
    force_overwrite = False
    list_old: int | None = None
    delete_old: int | None = None
    only_inactive = False
    thumbs: str | None = None
    websub_cmd: str | None = None
    daemon = False
    email_to_post = False
    init_files = False
    daemon_workers = int(
        getattr(
            settings,
            'WORKER_POOL_SIZE',
            DEFAULT_WORKER_POOL_SIZE,
        )
    )
    filters: dict[str, Any] = {}

    try:
        opts, args = getopt.getopt(
            _preprocess_cli_args(argv),
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
    except getopt.GetoptError:
        return WorkerCommand(kind=WorkerCommandKind.USAGE, usage_exit_code=0)

    for option, arg in opts:
        if option in ('-a', '--api'):
            filters['api'] = arg
        elif option in ('-i', '--id'):
            filters['id'] = arg
        elif option in ('-l', '--list'):
            list_services = True
        elif option in ('-v', '--verbose'):
            if arg:
                verbose = int(arg)
                lifecycle_logs = verbose > 0
            else:
                verbose += 1
        elif option == '--silent':
            lifecycle_logs = False
        elif option in ('-f', '--force-check'):
            force_check = True
        elif option == '--daemon':
            daemon = True
        elif option == '--workers':
            daemon_workers = int(arg)
        elif option == '--force-overwrite':
            force_overwrite = True
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
        elif option == '--websub':
            websub_cmd = arg
        elif option == '--email2post':
            email_to_post = True
        elif option == '--init-files-dirs':
            init_files = True

    if args:
        return WorkerCommand(kind=WorkerCommandKind.USAGE, usage_exit_code=1)

    cleanup_command: MaintenanceCommand | None = None
    if list_old is not None or delete_old is not None or thumbs is not None:
        cleanup_command = build_maintenance_command(
            filters=filters,
            list_old_days=list_old,
            delete_old_days=delete_old,
            only_inactive=only_inactive,
            thumbs=thumbs,
        )

    if email_to_post:
        kind = WorkerCommandKind.EMAIL2POST
    elif init_files:
        kind = WorkerCommandKind.INIT_FILES
    elif list_services:
        kind = WorkerCommandKind.LIST_SERVICES
    elif daemon:
        kind = WorkerCommandKind.DAEMON
    elif websub_cmd:
        kind = WorkerCommandKind.WEBSUB
    elif cleanup_command is not None:
        kind = WorkerCommandKind.CLEANUP
    else:
        kind = WorkerCommandKind.FETCH
        if not force_check or 'id' not in filters:
            filters['active'] = True
        filters = _normalize_fetch_filters(filters)

    return WorkerCommand(
        kind=kind,
        filters=filters,
        verbose=verbose,
        lifecycle_logs=lifecycle_logs,
        daemon_workers=daemon_workers,
        force_check=force_check,
        force_overwrite=force_overwrite,
        cleanup_command=cleanup_command,
        websub_action=websub_cmd,
    )


def handle_daemon(command: WorkerCommand) -> int:
    daemon_runner = WorkerDaemon(
        max_workers=command.daemon_workers,
        verbose=command.verbose,
        lifecycle_logs=command.lifecycle_logs,
    )
    try:
        daemon_runner.serve()
    except KeyboardInterrupt:
        if command.lifecycle_logs:
            daemon_runner._verbose_print('shutdown requested, exiting')
    return 0


def handle_fetch(command: WorkerCommand) -> int:
    if command.force_overwrite:
        sel = input('WARNING: This may create thumbnail orphans! Continue Y/N? ').strip()
        if sel != 'Y':
            return 0

    run_services(
        command.filters,
        force_check=command.force_check,
        force_overwrite=command.force_overwrite,
        verbose=command.verbose,
    )
    return 0


def handle_cleanup(command: WorkerCommand) -> int:
    assert command.cleanup_command is not None
    execute_maintenance_command(command.cleanup_command, verbose=command.verbose)
    return 0


def handle_websub(command: WorkerCommand, *, prog_name: str) -> int:
    action = command.websub_action
    if action == 'subscribe' and 'id' in command.filters:
        service = Service.objects.get(id=command.filters['id'])
        result = websub.subscribe(service, command.verbose)
        if result['rc'] == 1:
            print('%s: %s' % (prog_name, result['error']))
        elif result['rc'] == 2:
            print('%s: Hub not found.' % prog_name)
        elif result['rc'] == 202:
            print('hub=%s: Accepted for verification.' % result['hub'])
        elif result['rc'] == 204:
            print('hub=%s: Subscription verified.' % result['hub'])
        return 0
    if action == 'unsubscribe' and 'id' in command.filters:
        result = websub.unsubscribe(command.filters['id'], command.verbose)
        if result['rc'] == 1:
            print('%s: No subscription found.' % prog_name)
        elif result['rc'] == 202:
            print('hub=%s: Accepted for verification.' % result['hub'])
        elif result['rc'] == 204:
            print('hub=%s: Unsubscribed.' % result['hub'])
        else:
            print('hub=%s: %s.' % (result['hub'], result['rc']))
        return 0
    if action == 'renew':
        websub.renew_subscriptions(force=command.force_check, verbose=command.verbose)
        return 0
    if action == 'list':
        websub.list_subs()
        return 0
    if action == 'publish':
        websub.publish(verbose=command.verbose)
        return 0
    print('%s: Unknown "%s" action.' % (prog_name, action))
    return 1


def handle_email2post() -> int:
    api = mail.MailService()
    return api.share(sys.stdin)


def handle_init_files() -> int:
    return init_files_dirs()


def handle_list_services() -> int:
    for service in Service.objects.all().order_by('id'):
        print('%4d "%s"  API=%s' % (service.pk, service.name, service.api))
    return 0


def execute_command(command: WorkerCommand, *, prog_name: str) -> int:
    if command.kind == WorkerCommandKind.USAGE:
        _print_usage(prog_name)
        return command.usage_exit_code
    if command.kind == WorkerCommandKind.DAEMON:
        return handle_daemon(command)
    if command.kind == WorkerCommandKind.FETCH:
        return handle_fetch(command)
    if command.kind == WorkerCommandKind.CLEANUP:
        return handle_cleanup(command)
    if command.kind == WorkerCommandKind.WEBSUB:
        return handle_websub(command, prog_name=prog_name)
    if command.kind == WorkerCommandKind.EMAIL2POST:
        return handle_email2post()
    if command.kind == WorkerCommandKind.INIT_FILES:
        return handle_init_files()
    if command.kind == WorkerCommandKind.LIST_SERVICES:
        return handle_list_services()
    raise ValueError('Unsupported worker command kind: %s' % command.kind)


def main(argv: Sequence[str] | None = None, *, prog_name: str | None = None) -> int:
    actual_argv = list(argv if argv is not None else sys.argv[1:])
    actual_prog_name = prog_name or sys.argv[0]
    command = parse_legacy_command(actual_argv)
    _configure_library_logging(verbose=command.verbose)
    try:
        return execute_command(command, prog_name=actual_prog_name)
    finally:
        connections.close_all()


def run() -> None:
    actual_argv = sys.argv[1:]
    command = parse_legacy_command(actual_argv)
    exit_code = main(actual_argv, prog_name=sys.argv[0])
    if command.kind == WorkerCommandKind.FETCH:
        return
    raise SystemExit(exit_code)
