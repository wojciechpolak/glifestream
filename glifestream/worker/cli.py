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
from typing import Any, Callable, Sequence

from django.conf import settings
from django.db import connections

from glifestream.apis import mail
from glifestream.fetching import (
    DEFAULT_WORKER_POOL_SIZE,
    WorkerAlreadyRunning,
    run_services,
)
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
    """Normalize the verbosity spellings getopt cannot express itself.

    getopt has no optional-argument long option, so the option table carries
    only `verbose=` and bare `--verbose` is rewritten to `-v`, which stacks.
    """
    normalized: list[str] = []
    for arg in args:
        if re.fullmatch(r'-v\d+', arg):
            normalized.append('--verbose=%s' % arg[2:])
        elif arg == '--verbose':
            normalized.append('-v')
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
        normalized['api__in'] = [
            item.strip() for item in str(normalized['api']).split(',')
        ]
        del normalized['api']
    return normalized


@dataclass
class _ParsedOptions:
    """Everything the option loop can set, before it becomes a WorkerCommand."""

    filters: dict[str, Any] = field(default_factory=dict)
    verbose: int = 0
    lifecycle_logs: bool = True
    list_services: bool = False
    force_check: bool = False
    force_overwrite: bool = False
    list_old: int | None = None
    delete_old: int | None = None
    only_inactive: bool = False
    thumbs: str | None = None
    websub_cmd: str | None = None
    daemon: bool = False
    email_to_post: bool = False
    init_files: bool = False
    daemon_workers: int = 0


# Option tables, in the same dict-dispatch style as execute_command below.
_FILTER_OPTIONS: dict[str, str] = {
    '-a': 'api',
    '--api': 'api',
    '-i': 'id',
    '--id': 'id',
}

_FLAG_OPTIONS: dict[str, str] = {
    '-l': 'list_services',
    '--list': 'list_services',
    '-f': 'force_check',
    '--force-check': 'force_check',
    '--daemon': 'daemon',
    '--force-overwrite': 'force_overwrite',
    '--only-inactive': 'only_inactive',
    '--email2post': 'email_to_post',
    '--init-files-dirs': 'init_files',
}

_CONST_OPTIONS: dict[str, tuple[str, Any]] = {
    '--silent': ('lifecycle_logs', False),
    '--thumbs-list-orphans': ('thumbs', 'list-orphans'),
    '--thumbs-delete-orphans': ('thumbs', 'delete-orphans'),
}

_VALUE_OPTIONS: dict[str, tuple[str, Callable[[str], Any]]] = {
    '--workers': ('daemon_workers', int),
    '--list-old': ('list_old', int),
    '--delete-old': ('delete_old', int),
    '--websub': ('websub_cmd', str),
}

_LONG_OPTIONS = (
    'id=',
    'api=',
    'list',
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
)


def _default_daemon_workers() -> int:
    return int(getattr(settings, 'WORKER_POOL_SIZE', DEFAULT_WORKER_POOL_SIZE))


def _parse_options(opts: Sequence[tuple[str, str]]) -> _ParsedOptions:
    parsed = _ParsedOptions(daemon_workers=_default_daemon_workers())
    for option, arg in opts:
        if option in _FILTER_OPTIONS:
            parsed.filters[_FILTER_OPTIONS[option]] = arg
        elif option in _FLAG_OPTIONS:
            setattr(parsed, _FLAG_OPTIONS[option], True)
        elif option in _CONST_OPTIONS:
            attribute, value = _CONST_OPTIONS[option]
            setattr(parsed, attribute, value)
        elif option in _VALUE_OPTIONS:
            attribute, convert = _VALUE_OPTIONS[option]
            setattr(parsed, attribute, convert(arg))
        elif option in ('-v', '--verbose'):
            # Bare -v stacks; --verbose=N assigns and decides lifecycle logs.
            if arg:
                parsed.verbose = int(arg)
                parsed.lifecycle_logs = parsed.verbose > 0
            else:
                parsed.verbose += 1
    return parsed


def _select_command_kind(
    parsed: _ParsedOptions, cleanup_command: MaintenanceCommand | None
) -> WorkerCommandKind:
    if parsed.email_to_post:
        return WorkerCommandKind.EMAIL2POST
    if parsed.init_files:
        return WorkerCommandKind.INIT_FILES
    if parsed.list_services:
        return WorkerCommandKind.LIST_SERVICES
    if parsed.daemon:
        return WorkerCommandKind.DAEMON
    if parsed.websub_cmd:
        return WorkerCommandKind.WEBSUB
    if cleanup_command is not None:
        return WorkerCommandKind.CLEANUP
    return WorkerCommandKind.FETCH


def parse_legacy_command(argv: Sequence[str]) -> WorkerCommand:
    try:
        opts, args = getopt.getopt(
            _preprocess_cli_args(argv), 'i:a:lvf', list(_LONG_OPTIONS)
        )
    except getopt.GetoptError:
        return WorkerCommand(kind=WorkerCommandKind.USAGE, usage_exit_code=0)

    parsed = _parse_options(opts)

    if args:
        return WorkerCommand(kind=WorkerCommandKind.USAGE, usage_exit_code=1)

    cleanup_command: MaintenanceCommand | None = None
    if (
        parsed.list_old is not None
        or parsed.delete_old is not None
        or parsed.thumbs is not None
    ):
        cleanup_command = build_maintenance_command(
            filters=parsed.filters,
            list_old_days=parsed.list_old,
            delete_old_days=parsed.delete_old,
            only_inactive=parsed.only_inactive,
            thumbs=parsed.thumbs,
        )

    kind = _select_command_kind(parsed, cleanup_command)
    filters = parsed.filters
    if kind == WorkerCommandKind.FETCH:
        if not parsed.force_check or 'id' not in filters:
            filters['active'] = True
        filters = _normalize_fetch_filters(filters)

    return WorkerCommand(
        kind=kind,
        filters=filters,
        verbose=parsed.verbose,
        lifecycle_logs=parsed.lifecycle_logs,
        daemon_workers=parsed.daemon_workers,
        force_check=parsed.force_check,
        force_overwrite=parsed.force_overwrite,
        cleanup_command=cleanup_command,
        websub_action=parsed.websub_cmd,
    )


def handle_daemon(command: WorkerCommand, *, prog_name: str) -> int:
    daemon_runner = WorkerDaemon(
        max_workers=command.daemon_workers,
        verbose=command.verbose,
        lifecycle_logs=command.lifecycle_logs,
    )
    try:
        daemon_runner.serve()
    except WorkerAlreadyRunning as exc:
        print('%s: %s' % (prog_name, exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        if command.lifecycle_logs:
            daemon_runner._verbose_print('shutdown requested, exiting')
    return 0


def handle_fetch(command: WorkerCommand) -> int:
    if command.force_overwrite:
        sel = input(
            'WARNING: This may create thumbnail orphans! Continue Y/N? '
        ).strip()
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


def _report_subscribe_result(result: dict[str, Any], *, prog_name: str) -> None:
    rc = result['rc']
    if rc == 1:
        print('%s: %s' % (prog_name, result['error']))
    elif rc == 2:
        print('%s: Hub not found.' % prog_name)
    elif rc == 202:
        print('hub=%s: Accepted for verification.' % result['hub'])
    elif rc == 204:
        print('hub=%s: Subscription verified.' % result['hub'])


def _report_unsubscribe_result(result: dict[str, Any], *, prog_name: str) -> None:
    rc = result['rc']
    if rc == 1:
        print('%s: No subscription found.' % prog_name)
    elif rc == 202:
        print('hub=%s: Accepted for verification.' % result['hub'])
    elif rc == 204:
        print('hub=%s: Unsubscribed.' % result['hub'])
    else:
        print('hub=%s: %s.' % (result['hub'], rc))


def _websub_subscribe(command: WorkerCommand, *, prog_name: str) -> int | None:
    if 'id' not in command.filters:
        return None
    service = Service.objects.get(id=command.filters['id'])
    _report_subscribe_result(
        websub.subscribe(service, command.verbose), prog_name=prog_name
    )
    return 0


def _websub_unsubscribe(command: WorkerCommand, *, prog_name: str) -> int | None:
    if 'id' not in command.filters:
        return None
    _report_unsubscribe_result(
        websub.unsubscribe(command.filters['id'], command.verbose), prog_name=prog_name
    )
    return 0


def _websub_renew(command: WorkerCommand, *, prog_name: str) -> int | None:
    del prog_name
    websub.renew_subscriptions(force=command.force_check, verbose=command.verbose)
    return 0


def _websub_list(command: WorkerCommand, *, prog_name: str) -> int | None:
    del command, prog_name
    websub.list_subs()
    return 0


def _websub_publish(command: WorkerCommand, *, prog_name: str) -> int | None:
    del prog_name
    websub.publish(verbose=command.verbose)
    return 0


WEBSUB_ACTIONS: dict[str, Callable[..., int | None]] = {
    'subscribe': _websub_subscribe,
    'unsubscribe': _websub_unsubscribe,
    'renew': _websub_renew,
    'list': _websub_list,
    'publish': _websub_publish,
}


def handle_websub(command: WorkerCommand, *, prog_name: str) -> int:
    handler = WEBSUB_ACTIONS.get(command.websub_action or '')
    if handler is not None:
        # A handler returns None when it cannot act, e.g. (un)subscribe
        # without --id, which reports as an unknown action like it always has.
        exit_code = handler(command, prog_name=prog_name)
        if exit_code is not None:
            return exit_code
    print('%s: Unknown "%s" action.' % (prog_name, command.websub_action))
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
        return handle_daemon(command, prog_name=prog_name)
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
