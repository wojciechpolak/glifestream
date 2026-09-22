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
from typing import cast
from unittest.mock import patch

import pytest

from glifestream.fetching import WorkerAlreadyRunning
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
    with patch(
        'glifestream.worker.cli.handle_cleanup', return_value=3
    ) as handle_cleanup:
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


def parse(*argv: str) -> cli.WorkerCommand:
    return cli.parse_legacy_command(list(argv))


def test_parse_bad_option_prints_usage_with_zero_exit():
    command = parse('--no-such-option')

    assert command.kind == cli.WorkerCommandKind.USAGE
    assert command.usage_exit_code == 0


def test_parse_stray_positional_argument_is_a_usage_error():
    command = parse('--list', 'leftover')

    assert command.kind == cli.WorkerCommandKind.USAGE
    assert command.usage_exit_code == 1


def test_parse_bare_verbose_flags_stack():
    assert parse('-v', '-v', '-v').verbose == 3


def test_parse_numeric_verbose_shorthand_is_normalized():
    command = parse('-v3')

    assert command.verbose == 3
    assert command.lifecycle_logs is True


def test_parse_zero_verbosity_disables_lifecycle_logs():
    command = parse('--verbose=0')

    assert command.verbose == 0
    assert command.lifecycle_logs is False


def test_parse_silent_disables_lifecycle_logs():
    assert parse('--silent').lifecycle_logs is False


def test_parse_short_flags_map_to_their_commands():
    assert parse('-l').kind == cli.WorkerCommandKind.LIST_SERVICES
    assert parse('--email2post').kind == cli.WorkerCommandKind.EMAIL2POST
    assert parse('--init-files-dirs').kind == cli.WorkerCommandKind.INIT_FILES
    assert parse('--websub=list').kind == cli.WorkerCommandKind.WEBSUB
    assert parse('--websub=list').websub_action == 'list'


def test_parse_command_kind_precedence_prefers_email2post():
    command = parse('--email2post', '--init-files-dirs', '--list', '--daemon')

    assert command.kind == cli.WorkerCommandKind.EMAIL2POST


def test_parse_thumbs_options_build_a_cleanup_command():
    for option, expected in (
        ('--thumbs-list-orphans', 'list-orphans'),
        ('--thumbs-delete-orphans', 'delete-orphans'),
    ):
        command = parse(option)
        assert command.kind == cli.WorkerCommandKind.CLEANUP
        assert command.cleanup_command is not None
        assert command.cleanup_command.thumbs == expected


def test_parse_list_old_builds_a_cleanup_command():
    command = parse('--list-old=7')

    assert command.cleanup_command is not None
    assert command.cleanup_command.list_old_days == 7


def test_parse_fetch_defaults_to_active_services():
    assert parse('--api=webfeed').filters == {'api': 'webfeed', 'active': True}


def test_parse_force_check_by_id_drops_the_active_filter():
    command = parse('--id=4', '--force-check')

    assert command.force_check is True
    assert command.filters == {'id': '4'}


def test_parse_force_check_without_id_keeps_the_active_filter():
    assert parse('--force-check').filters == {'active': True}


def test_parse_splits_comma_separated_ids_and_apis():
    command = parse('--id=1,2,3', '--api=webfeed, mastodon', '--force-check')

    assert command.filters['id__in'] == [1, 2, 3]
    assert command.filters['api__in'] == ['webfeed', 'mastodon']
    assert 'id' not in command.filters
    assert 'api' not in command.filters


def test_parse_force_overwrite_is_carried_through():
    assert parse('--force-overwrite').force_overwrite is True


def test_parse_workers_overrides_the_configured_pool_size():
    assert parse('--workers=11').daemon_workers == 11


def websub_command(action: str, **filters: object) -> cli.WorkerCommand:
    return cli.WorkerCommand(
        kind=cli.WorkerCommandKind.WEBSUB,
        websub_action=action,
        filters=dict(filters),
    )


def test_handle_websub_rejects_an_unknown_action(capsys):
    exit_code = cli.handle_websub(websub_command('bogus'), prog_name='worker.py')

    assert exit_code == 1
    assert 'Unknown "bogus" action.' in capsys.readouterr().out


def test_handle_websub_subscribe_without_an_id_is_an_unknown_action(capsys):
    exit_code = cli.handle_websub(websub_command('subscribe'), prog_name='worker.py')

    assert exit_code == 1
    assert 'Unknown "subscribe" action.' in capsys.readouterr().out


def test_handle_websub_unsubscribe_without_an_id_is_an_unknown_action(capsys):
    exit_code = cli.handle_websub(websub_command('unsubscribe'), prog_name='worker.py')

    assert exit_code == 1
    assert 'Unknown "unsubscribe" action.' in capsys.readouterr().out


@pytest.mark.django_db
@pytest.mark.parametrize(
    'result,expected',
    [
        ({'rc': 1, 'error': 'boom'}, 'worker.py: boom'),
        ({'rc': 2}, 'worker.py: Hub not found.'),
        ({'rc': 202, 'hub': 'http://hub'}, 'Accepted for verification.'),
        ({'rc': 204, 'hub': 'http://hub'}, 'Subscription verified.'),
    ],
)
def test_handle_websub_subscribe_reports_each_outcome(
    service, capsys, result, expected
):
    command = websub_command('subscribe', id=service.pk)

    with patch('glifestream.stream.websub.subscribe', return_value=result):
        exit_code = cli.handle_websub(command, prog_name='worker.py')

    assert exit_code == 0
    assert expected in capsys.readouterr().out


@pytest.mark.django_db
def test_handle_websub_subscribe_with_an_unremarkable_code_stays_quiet(service, capsys):
    command = websub_command('subscribe', id=service.pk)

    with patch('glifestream.stream.websub.subscribe', return_value={'rc': 200}):
        assert cli.handle_websub(command, prog_name='worker.py') == 0

    assert capsys.readouterr().out == ''


@pytest.mark.parametrize(
    'result,expected',
    [
        ({'rc': 1}, 'worker.py: No subscription found.'),
        ({'rc': 202, 'hub': 'http://hub'}, 'Accepted for verification.'),
        ({'rc': 204, 'hub': 'http://hub'}, 'Unsubscribed.'),
        ({'rc': 'timed out', 'hub': 'http://hub'}, 'hub=http://hub: timed out.'),
    ],
)
def test_handle_websub_unsubscribe_reports_each_outcome(capsys, result, expected):
    command = websub_command('unsubscribe', id=5)

    with patch('glifestream.stream.websub.unsubscribe', return_value=result):
        exit_code = cli.handle_websub(command, prog_name='worker.py')

    assert exit_code == 0
    assert expected in capsys.readouterr().out


def test_handle_websub_renew_forwards_force_check():
    command = cli.WorkerCommand(
        kind=cli.WorkerCommandKind.WEBSUB,
        websub_action='renew',
        force_check=True,
        verbose=2,
    )

    with patch('glifestream.stream.websub.renew_subscriptions') as renew:
        assert cli.handle_websub(command, prog_name='worker.py') == 0

    renew.assert_called_once_with(force=True, verbose=2)


def test_handle_websub_list_and_publish_delegate():
    with patch('glifestream.stream.websub.list_subs') as list_subs:
        assert cli.handle_websub(websub_command('list'), prog_name='worker.py') == 0
    list_subs.assert_called_once_with()

    with patch('glifestream.stream.websub.publish') as publish:
        assert cli.handle_websub(websub_command('publish'), prog_name='worker.py') == 0
    publish.assert_called_once_with(verbose=0)


def test_execute_command_rejects_an_unsupported_kind():
    command = cli.WorkerCommand(kind=cast(cli.WorkerCommandKind, 'nonsense'))

    with pytest.raises(ValueError, match='Unsupported worker command kind'):
        cli.execute_command(command, prog_name='worker.py')


def test_execute_command_prints_usage():
    command = cli.WorkerCommand(kind=cli.WorkerCommandKind.USAGE, usage_exit_code=1)

    assert cli.execute_command(command, prog_name='worker.py') == 1


def test_handle_fetch_aborts_a_force_overwrite_the_operator_declines():
    command = cli.WorkerCommand(kind=cli.WorkerCommandKind.FETCH, force_overwrite=True)

    with (
        patch('builtins.input', return_value='n'),
        patch('glifestream.worker.cli.run_services') as run_services,
    ):
        assert cli.handle_fetch(command) == 0

    run_services.assert_not_called()


def test_handle_fetch_runs_a_confirmed_force_overwrite():
    command = cli.WorkerCommand(
        kind=cli.WorkerCommandKind.FETCH, force_overwrite=True, filters={'id': 1}
    )

    with (
        patch('builtins.input', return_value='Y'),
        patch('glifestream.worker.cli.run_services') as run_services,
    ):
        assert cli.handle_fetch(command) == 0

    run_services.assert_called_once()


@pytest.mark.django_db
def test_handle_list_services_prints_every_service(service, capsys):
    assert cli.handle_list_services() == 0

    assert 'Test Service' in capsys.readouterr().out


def test_handle_daemon_survives_a_keyboard_interrupt(capsys):
    with patch('glifestream.worker.cli.WorkerDaemon') as daemon_cls:
        daemon_cls.return_value.serve.side_effect = KeyboardInterrupt
        command = cli.WorkerCommand(kind=cli.WorkerCommandKind.DAEMON)

        assert cli.handle_daemon(command, prog_name='worker.py') == 0

    daemon_cls.return_value._verbose_print.assert_called_once()


def test_handle_daemon_refuses_to_run_beside_another_worker(capsys):
    with patch('glifestream.worker.cli.WorkerDaemon') as daemon_cls:
        daemon_cls.return_value.serve.side_effect = WorkerAlreadyRunning('taken')
        command = cli.WorkerCommand(kind=cli.WorkerCommandKind.DAEMON)

        assert cli.handle_daemon(command, prog_name='worker.py') == 1

    assert capsys.readouterr().err == 'worker.py: taken\n'


def test_handle_email2post_and_init_files_delegate():
    with patch('glifestream.apis.mail.MailService') as mail_service:
        mail_service.return_value.share.return_value = 0
        assert cli.handle_email2post() == 0

    with patch('glifestream.worker.cli.init_files_dirs', return_value=4):
        assert cli.handle_init_files() == 4


def test_parse_long_verbose_flags_stack():
    """--verbose has no argument and stacks, --verbose=N assigns."""
    assert parse('--verbose', '--verbose').verbose == 2
    assert parse('--verbose=5').verbose == 5
