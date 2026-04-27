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
from collections.abc import Mapping, MutableMapping
from typing import Any


_TRUE_VALUES = {'1', 'true', 'yes', 'on'}
_FALSE_VALUES = {'0', 'false', 'no', 'off'}


def _get_bool(environ: Mapping[str, str], name: str, default: bool) -> bool:
    value = environ.get(name)
    if value is None:
        return default

    normalised = value.strip().lower()
    if normalised in _TRUE_VALUES:
        return True
    if normalised in _FALSE_VALUES:
        return False
    return default


def _get_int(environ: Mapping[str, str], name: str, default: int) -> int:
    value = environ.get(name)
    if value is None:
        return default

    try:
        return int(value)
    except ValueError:
        return default


def apply_magic_sso_defaults(
    settings_values: MutableMapping[str, Any],
    environ: Mapping[str, str] | None = None,
) -> None:
    env = os.environ if environ is None else environ

    settings_values.setdefault(
        'MAGICSSO_ENABLED',
        _get_bool(env, 'MAGICSSO_ENABLED', False),
    )
    settings_values.setdefault(
        'MAGICSSO_SERVER_URL',
        env.get('MAGICSSO_SERVER_URL', 'http://localhost:3000'),
    )
    settings_values.setdefault(
        'MAGICSSO_JWT_SECRET',
        env.get('MAGICSSO_JWT_SECRET', 'VERY-VERY-LONG-RANDOM-JWT-SECRET'),
    )
    settings_values.setdefault(
        'MAGICSSO_PREVIEW_SECRET',
        env.get(
            'MAGICSSO_PREVIEW_SECRET',
            'VERY-VERY-LONG-RANDOM-PREVIEW-SECRET',
        ),
    )
    settings_values.setdefault(
        'MAGICSSO_COOKIE_NAME',
        env.get('MAGICSSO_COOKIE_NAME', 'magic-sso'),
    )
    settings_values.setdefault(
        'MAGICSSO_COOKIE_PATH',
        env.get('MAGICSSO_COOKIE_PATH', '/'),
    )
    settings_values.setdefault(
        'MAGICSSO_COOKIE_DOMAIN',
        env.get('MAGICSSO_COOKIE_DOMAIN') or None,
    )
    settings_values.setdefault(
        'MAGICSSO_COOKIE_MAX_AGE',
        _get_int(env, 'MAGICSSO_COOKIE_MAX_AGE', 3600),
    )
    settings_values.setdefault(
        'MAGICSSO_COOKIE_SAMESITE',
        env.get('MAGICSSO_COOKIE_SAMESITE', 'Lax'),
    )
    settings_values.setdefault(
        'MAGICSSO_COOKIE_SECURE',
        _get_bool(env, 'MAGICSSO_COOKIE_SECURE', False),
    )
    settings_values.setdefault(
        'MAGICSSO_DIRECT_USE',
        _get_bool(env, 'MAGICSSO_DIRECT_USE', False),
    )
    settings_values.setdefault(
        'MAGICSSO_AUTH_EVERYWHERE',
        _get_bool(env, 'MAGICSSO_AUTH_EVERYWHERE', False),
    )
    settings_values.setdefault(
        'MAGICSSO_REQUEST_TIMEOUT',
        _get_int(env, 'MAGICSSO_REQUEST_TIMEOUT', 5),
    )
    settings_values.setdefault(
        'MAGICSSO_PUBLIC_URLS',
        ['login', 'logout', 'change-password', 'verify_email'],
    )
