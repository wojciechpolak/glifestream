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

import os
from pathlib import Path
from typing import Any, cast

from django.conf import settings


def init_files_dirs() -> int:
    upload = os.path.join(settings.MEDIA_ROOT, 'upload')
    _create_dir(upload)

    thumbs = os.path.join(settings.MEDIA_ROOT, 'thumbs')
    _create_dir(thumbs)

    for digit in range(0, 10):
        _create_dir(os.path.join(thumbs, str(digit)))
    for suffix in 'abcdef':
        _create_dir(os.path.join(thumbs, suffix))

    print(
        """
Make sure that 'static/thumbs/*' and 'static/upload' directories exist
and all have write permissions by your webserver.
"""
    )

    templates = cast(list[dict[str, Any]], settings.TEMPLATES)
    template_dirs = cast(list[str], templates[0]['DIRS'])
    template_dir = template_dirs[0]
    template_files = (
        'user-about.html',
        'user-copyright.html',
        'user-scripts.js',
    )
    try:
        for template_file in template_files:
            path = Path(template_dir, template_file)
            if not path.is_file():
                print("Creating empty file '%s'" % path)
                path.touch()
    except Exception as exc:
        print(exc)
        return 1

    return 0


def _create_dir(path: str, verbose: bool = True) -> None:
    if not os.path.isdir(path):
        if verbose:
            print("Creating directory '%s'" % path)
        os.mkdir(path)
