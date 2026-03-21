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
    parser.add_argument('--source', default='glifestream/settings_sample.py')
    parser.add_argument('--output', default='/tmp/vrt_settings.py')
    parser.add_argument('--site-root', default='/work/glifestream')
    parser.add_argument('--secret-key', default='ci-secret-key')
    args = parser.parse_args()

    source_path = Path(args.source)
    output_path = Path(args.output)
    source = source_path.read_text()
    source = source.replace(
        'SITE_ROOT = os.path.dirname(os.path.realpath(__file__))',
        f'SITE_ROOT = "{args.site_root}"',
    )
    source = source.replace(
        "SECRET_KEY = 'YOUR-SECRET-KEY'",
        f'SECRET_KEY = "{args.secret_key}"',
    )
    source = source.replace(
        'django.core.cache.backends.memcached.PyMemcacheCache',
        'django.core.cache.backends.dummy.DummyCache',
    )
    source = source.replace(
        "        'DIRS': [\n            os.path.join(SITE_ROOT, '../run/templates'),\n            os.path.join(SITE_ROOT, 'templates'),\n        ],",
        "        'DIRS': [\n            os.path.join(SITE_ROOT, 'templates'),\n        ],",
    )
    source = source.replace(
        "STATICFILES_DIRS = (\n    os.path.join(SITE_ROOT, '../run/static'),\n    os.path.join(SITE_ROOT, 'static'),\n)",
        "STATICFILES_DIRS = (\n    os.path.join(SITE_ROOT, 'static'),\n)",
    )
    output_path.write_text(source)


if __name__ == '__main__':
    main()
