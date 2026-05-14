#!/usr/bin/env python3

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

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', default='glifestream/settings.py')
    parser.add_argument('--output', default='/tmp/vrt_settings.py')
    parser.add_argument('--site-root', default='/work/glifestream')
    parser.add_argument('--secret-key', default='ci-secret-key')
    args = parser.parse_args()

    output_path = Path(args.output)
    source = f"""\
import os
from pathlib import Path

os.environ['GLIFESTREAM_LOAD_DOTENV'] = '0'
os.environ['GLIFESTREAM_ENABLE_SETTINGS_LOCAL'] = '0'

from glifestream.settings import *  # noqa: F403

SITE_ROOT = "{args.site_root}"
BASE_DIR = SITE_ROOT

SECRET_KEY = "{args.secret_key}"
ALLOWED_HOSTS = ['localhost']
TIME_ZONE = 'UTC'
BASE_URL = 'http://localhost:8000'
LOGIN_URL = '/login'
FAVICON = '/favicon.ico'
THEMES = ('default',)
STREAM_TITLE = 'Stream title'
STREAM_TITLE_SUFFIX = ' | Lifestream'
STREAM_DESCRIPTION = 'A short description'
WEBSUB_HUBS = ('https://pubsubhubbub.appspot.com/',)
WEBSUB_HTTPS_CALLBACK = True
CACHES = {{
    'default': {{
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
        'LOCATION': '127.0.0.1:11211',
        'KEY_PREFIX': 'gls',
    }},
}}
TEMPLATES[0]['DIRS'] = [  # noqa: F405
    str(Path(SITE_ROOT) / 'templates'),
]
STATICFILES_DIRS = (  # noqa: F405
    str(Path(SITE_ROOT) / 'static'),
)

FEED_AUTHOR_NAME = ''
FEED_AUTHOR_URI = ''
"""
    output_path.write_text(source)


if __name__ == '__main__':
    main()
