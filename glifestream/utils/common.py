"""
#  gLifestream Copyright (C) 2010 Wojciech Polak
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
from django.conf import settings
from django.http import HttpRequest
from django.templatetags.static import static


def default_theme() -> str:
    """The theme of a visitor who has not chosen one: DEFAULT_THEME, or else
    the first of THEMES."""
    themes = settings.THEMES
    chosen = getattr(settings, 'DEFAULT_THEME', '')
    return chosen if chosen in themes else themes[0]


def get_theme(request: HttpRequest) -> str:
    """The theme of the gls-theme cookie, while THEMES has it."""
    theme = request.COOKIES.get('gls-theme', '')
    return theme if theme in settings.THEMES else default_theme()


def theme_cycle() -> list[str]:
    """THEMES in the order "Change theme" goes, from the default one.

    The page script takes a visitor without the cookie for one on the first.
    """
    themes = list(settings.THEMES)
    start = themes.index(default_theme())
    return themes[start:] + themes[:start]


def static_url(path: str) -> str:
    """The URL of a static file, or ``path`` itself when it already is one."""
    if path.startswith('/') or '://' in path:
        return path
    return static(path)
