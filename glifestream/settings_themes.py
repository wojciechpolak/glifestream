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

The themes and the django-pipeline bundle each one is built into.

A theme is a directory of the static files, themes/<name>/, with a style.scss.
The project ships BUNDLED_THEMES; a deployment adds its own in
RUN_DIR/static/themes/<name>/ and names it in THEMES.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

# The themes in glifestream/static/themes/, the first the one a site starts with.
BUNDLED_THEMES = ('default', 'broadsheet', 'phosphor', 'riso', 'dotfiles')

# A theme's name ends up in a class name, a path and a cookie.
THEME_NAME = re.compile(r'^[a-z0-9][a-z0-9_-]*$')


def theme_bundle(name: str) -> dict[str, Any]:
    """The pipeline bundle of the theme `name`, from themes/<name>/style.scss."""
    return {
        'source_filenames': (
            # The stylesheets of frontend/, such as PhotoSwipe's.
            'js/dist/glifestream.css',
            f'themes/{name}/style.scss',
        ),
        'output_filename': f'themes/{name}/style.css',
    }


def add_theme_bundles(stylesheets: dict[str, Any], names: Iterable[str]) -> None:
    """Gives each theme of `names` a bundle, unless it has one already."""
    for name in names:
        stylesheets.setdefault(name, theme_bundle(name))
