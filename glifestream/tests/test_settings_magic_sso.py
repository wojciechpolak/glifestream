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

import os
from pathlib import Path

import pytest

from glifestream.settings_magic_sso import (
    apply_magic_sso_defaults,
    get_bool,
    get_env,
    get_int,
    get_list,
    load_env_defaults,
    validate_magic_sso_settings,
    validate_secret_value,
)


def test_apply_magic_sso_defaults_populates_required_settings() -> None:
    values: dict[str, object] = {}

    apply_magic_sso_defaults(values, {})

    assert values['MAGICSSO_ENABLED'] is False
    assert values['MAGICSSO_SERVER_URL'] == 'http://localhost:3000'
    assert values['MAGICSSO_JWT_SECRET'] == 'VERY-VERY-LONG-RANDOM-JWT-SECRET'
    assert values['MAGICSSO_PREVIEW_SECRET'] == 'VERY-VERY-LONG-RANDOM-PREVIEW-SECRET'
    assert values['MAGICSSO_COOKIE_NAME'] == 'magic-sso'
    assert values['MAGICSSO_PUBLIC_URLS'] == [
        'login',
        'logout',
        'change-password',
        'verify_email',
    ]


def test_apply_magic_sso_defaults_respects_existing_settings_and_env() -> None:
    values: dict[str, object] = {
        'MAGICSSO_COOKIE_NAME': 'custom-cookie',
        'MAGICSSO_DIRECT_USE': True,
    }

    apply_magic_sso_defaults(
        values,
        {
            'MAGICSSO_ENABLED': 'true',
            'MAGICSSO_SERVER_URL': 'https://sso.example.com',
            'MAGICSSO_COOKIE_SECURE': 'true',
            'MAGICSSO_REQUEST_TIMEOUT': '15',
        },
    )

    assert values['MAGICSSO_ENABLED'] is True
    assert values['MAGICSSO_SERVER_URL'] == 'https://sso.example.com'
    assert values['MAGICSSO_COOKIE_NAME'] == 'custom-cookie'
    assert values['MAGICSSO_DIRECT_USE'] is True
    assert values['MAGICSSO_COOKIE_SECURE'] is True
    assert values['MAGICSSO_REQUEST_TIMEOUT'] == 15


def test_load_env_defaults_sets_missing_values_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv('NEW_VALUE', raising=False)
    monkeypatch.setenv('EXISTING_VALUE', 'keep-me')

    env_path = tmp_path / '.env'
    env_path.write_text(
        '\n'.join(
            [
                '# comment',
                'NEW_VALUE=new',
                'EXISTING_VALUE=replace-me',
                'export QUOTED_VALUE="quoted text"',
            ]
        )
    )

    load_env_defaults(env_path)

    assert get_env({}, 'MISSING', default='fallback') == 'fallback'
    assert get_env(os.environ, 'NEW_VALUE') == 'new'
    assert get_env(os.environ, 'EXISTING_VALUE') == 'keep-me'
    assert get_env(os.environ, 'QUOTED_VALUE') == 'quoted text'


def test_env_accessors_parse_scalars_and_lists() -> None:
    environ = {
        'DEBUG': 'true',
        'TIMEOUT': '15',
        'HOSTS': ' localhost,127.0.0.1 ,,backend ',
    }

    assert get_bool(environ, 'DEBUG', default=False) is True
    assert get_int(environ, 'TIMEOUT', default=0) == 15
    assert get_list(environ, 'HOSTS', default=[]) == [
        'localhost',
        '127.0.0.1',
        'backend',
    ]


def test_validate_secret_value_rejects_placeholders_in_production() -> None:
    with pytest.raises(ValueError):
        validate_secret_value('SECRET_KEY', 'YOUR-SECRET-KEY', debug=False)


def test_validate_magic_sso_settings_rejects_placeholders_when_enabled() -> None:
    with pytest.raises(ValueError):
        validate_magic_sso_settings(
            {
                'MAGICSSO_ENABLED': True,
                'MAGICSSO_JWT_SECRET': 'VERY-VERY-LONG-RANDOM-JWT-SECRET',
                'MAGICSSO_PREVIEW_SECRET': 'VERY-VERY-LONG-RANDOM-PREVIEW-SECRET',
            },
            debug=False,
        )
