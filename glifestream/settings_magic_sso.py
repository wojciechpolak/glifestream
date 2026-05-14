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
from collections.abc import Mapping, MutableMapping
from typing import Any


_TRUE_VALUES = {'1', 'true', 'yes', 'on'}
_FALSE_VALUES = {'0', 'false', 'no', 'off'}
_PLACEHOLDER_SECRET_VALUES = {
    'YOUR-SECRET-KEY',
    'VERY-VERY-LONG-RANDOM-JWT-SECRET',
    'VERY-VERY-LONG-RANDOM-PREVIEW-SECRET',
}


def load_env_defaults(path: str | os.PathLike[str]) -> None:
    env_path = Path(path)
    if not env_path.is_file():
        return

    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[7:].strip()
        if '=' not in line:
            continue

        name, value = line.split('=', 1)
        name = name.strip()
        value = value.strip()
        if not name:
            continue

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]

        os.environ.setdefault(name, value)


def get_env(
    environ: Mapping[str, str],
    *names: str,
    default: str | None = None,
) -> str | None:
    for name in names:
        value = environ.get(name)
        if value is not None and value != '':
            return value

    return default


def get_bool(environ: Mapping[str, str], *names: str, default: bool) -> bool:
    value = get_env(environ, *names)
    if value is None:
        return default

    normalised = value.strip().lower()
    if normalised in _TRUE_VALUES:
        return True
    if normalised in _FALSE_VALUES:
        return False
    return default


def get_int(environ: Mapping[str, str], *names: str, default: int) -> int:
    value = get_env(environ, *names)
    if value is None:
        return default

    try:
        return int(value)
    except ValueError:
        return default


def get_list(
    environ: Mapping[str, str],
    *names: str,
    default: list[str],
) -> list[str]:
    value = get_env(environ, *names)
    if value is None:
        return list(default)

    items = [item.strip() for item in value.split(',')]
    return [item for item in items if item]


def validate_secret_value(
    name: str,
    value: str | None,
    *,
    debug: bool,
    placeholders: set[str] | None = None,
) -> None:
    placeholder_values = _PLACEHOLDER_SECRET_VALUES.copy()
    if placeholders:
        placeholder_values.update(placeholders)

    if value and value not in placeholder_values:
        return

    if debug:
        return

    raise ValueError(f'{name} must be configured with a non-placeholder value.')


def apply_magic_sso_defaults(
    settings_values: MutableMapping[str, Any],
    environ: Mapping[str, str] | None = None,
) -> None:
    env = os.environ if environ is None else environ

    settings_values.setdefault(
        'MAGICSSO_ENABLED',
        get_bool(env, 'MAGICSSO_ENABLED', default=False),
    )
    settings_values.setdefault(
        'MAGICSSO_SERVER_URL',
        get_env(
            env,
            'MAGICSSO_SERVER_URL',
            default='http://localhost:3000',
        ),
    )
    settings_values.setdefault(
        'MAGICSSO_JWT_SECRET',
        get_env(
            env,
            'MAGICSSO_JWT_SECRET',
            default='VERY-VERY-LONG-RANDOM-JWT-SECRET',
        ),
    )
    settings_values.setdefault(
        'MAGICSSO_PREVIEW_SECRET',
        get_env(
            env,
            'MAGICSSO_PREVIEW_SECRET',
            default='VERY-VERY-LONG-RANDOM-PREVIEW-SECRET',
        ),
    )
    settings_values.setdefault(
        'MAGICSSO_COOKIE_NAME',
        get_env(env, 'MAGICSSO_COOKIE_NAME', default='magic-sso'),
    )
    settings_values.setdefault(
        'MAGICSSO_COOKIE_PATH',
        get_env(env, 'MAGICSSO_COOKIE_PATH', default='/'),
    )
    settings_values.setdefault(
        'MAGICSSO_COOKIE_DOMAIN',
        get_env(env, 'MAGICSSO_COOKIE_DOMAIN') or None,
    )
    settings_values.setdefault(
        'MAGICSSO_COOKIE_MAX_AGE',
        get_int(env, 'MAGICSSO_COOKIE_MAX_AGE', default=3600),
    )
    settings_values.setdefault(
        'MAGICSSO_COOKIE_SAMESITE',
        get_env(env, 'MAGICSSO_COOKIE_SAMESITE', default='Lax'),
    )
    settings_values.setdefault(
        'MAGICSSO_COOKIE_SECURE',
        get_bool(env, 'MAGICSSO_COOKIE_SECURE', default=False),
    )
    settings_values.setdefault(
        'MAGICSSO_DIRECT_USE',
        get_bool(env, 'MAGICSSO_DIRECT_USE', default=False),
    )
    settings_values.setdefault(
        'MAGICSSO_AUTH_EVERYWHERE',
        get_bool(env, 'MAGICSSO_AUTH_EVERYWHERE', default=False),
    )
    settings_values.setdefault(
        'MAGICSSO_REQUEST_TIMEOUT',
        get_int(env, 'MAGICSSO_REQUEST_TIMEOUT', default=5),
    )
    settings_values.setdefault(
        'MAGICSSO_PUBLIC_URLS',
        ['login', 'logout', 'change-password', 'verify_email'],
    )


def validate_magic_sso_settings(
    settings_values: Mapping[str, Any],
    *,
    debug: bool,
) -> None:
    if not settings_values.get('MAGICSSO_ENABLED'):
        return

    validate_secret_value(
        'MAGICSSO_JWT_SECRET',
        settings_values.get('MAGICSSO_JWT_SECRET'),
        debug=debug,
    )
    validate_secret_value(
        'MAGICSSO_PREVIEW_SECRET',
        settings_values.get('MAGICSSO_PREVIEW_SECRET'),
        debug=debug,
    )
