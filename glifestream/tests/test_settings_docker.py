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

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def docker_settings(**env: str) -> dict[str, str]:
    """Some values of glifestream.settings_docker, loaded in a clean process."""
    code = (
        'import json; from glifestream import settings_docker as s; '
        'print(json.dumps({"BASE_URL": s.BASE_URL, "LOGIN_URL": s.LOGIN_URL, '
        '"FEED_AUTHOR_URI": s.FEED_AUTHOR_URI}))'
    )
    clean = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(('APP_', 'BASE_URL', 'FEED_', 'VIRTUAL_', 'DJANGO_'))
    }
    clean.update(
        GLIFESTREAM_LOAD_DOTENV='0',
        GLIFESTREAM_ENABLE_SETTINGS_LOCAL='0',
        APP_SECRET_KEY='test-secret-key-for-docker-settings',
        **env,
    )
    result = subprocess.run(
        [sys.executable, '-c', code],
        cwd=ROOT,
        env=clean,
        capture_output=True,
        text=True,
        check=True,
    )
    values: dict[str, str] = json.loads(result.stdout.splitlines()[-1])
    return values


def test_author_uri_follows_the_docker_base_url() -> None:
    values = docker_settings()

    assert values['BASE_URL'] == 'http://localhost:8080'
    assert values['FEED_AUTHOR_URI'] == 'http://localhost:8080/'


def test_author_uri_follows_the_path_prefix_and_an_explicit_value() -> None:
    assert docker_settings(VIRTUAL_PATH='/stream/')['FEED_AUTHOR_URI'] == (
        'http://localhost:8080/stream/'
    )
    assert docker_settings(FEED_AUTHOR_URI='https://example.com/')[
        'FEED_AUTHOR_URI'
    ] == ('https://example.com/')
