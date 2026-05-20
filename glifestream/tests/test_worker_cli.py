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

import sys
from unittest.mock import patch

from glifestream.worker import cli
import worker


def test_main_dispatches_legacy_daemon_command():
    with patch('glifestream.worker.cli.handle_daemon', return_value=7) as handle_daemon:
        result = cli.main(['--daemon', '--workers=2'], prog_name='worker.py')

    assert result == 7
    command = handle_daemon.call_args.args[0]
    assert command.kind == cli.WorkerCommandKind.DAEMON
    assert command.daemon_workers == 2


def test_main_dispatches_legacy_cleanup_command():
    with patch('glifestream.worker.cli.handle_cleanup', return_value=3) as handle_cleanup:
        result = cli.main(
            ['--delete-old=30', '--only-inactive', '--api=webfeed'],
            prog_name='worker.py',
        )

    assert result == 3
    command = handle_cleanup.call_args.args[0]
    assert command.kind == cli.WorkerCommandKind.CLEANUP
    assert command.cleanup_command is not None
    assert command.cleanup_command.delete_old_days == 30
    assert command.cleanup_command.only_inactive is True
    assert command.cleanup_command.filters == {'api': 'webfeed'}


def test_legacy_run_fetch_path_does_not_raise_system_exit(monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['worker.py', '--api=webfeed', '--force-check'])

    with patch('glifestream.worker.cli.handle_fetch', return_value=0) as handle_fetch:
        worker.run()

    handle_fetch.assert_called_once()
