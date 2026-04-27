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

from glifestream.settings_magic_sso import apply_magic_sso_defaults


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
