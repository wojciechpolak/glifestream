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

Which link of the top bar leads to the page a visitor is on.
"""

from __future__ import annotations

from django.http import HttpRequest
from django.template import Context, Library
from django.urls import reverse
from django.utils.safestring import SafeString, mark_safe

register = Library()

# The routes of the top bar's sections, by name (urls.py).
SECTIONS = {
    'index': 'home',
    'archive': 'home',
    'public': 'public',
    'public-archive': 'public',
}


def nav_section(request: HttpRequest | None) -> str:
    """The top bar's section of the page `request` asks for, or ''.

    'home' is the private stream and its archive, 'public' the public one,
    'settings' any settings page. Favorites, lists and single entries have
    no link of their own in the top bar.
    """
    match = getattr(request, 'resolver_match', None)
    if request is None or match is None:
        return ''
    if request.path.startswith(reverse('settings')):
        return 'settings'
    return SECTIONS.get(match.url_name or '', '')


@register.simple_tag(takes_context=True)
def nav_current(context: Context, section: str) -> SafeString:
    """` aria-current="page"` on the top bar's link to the page shown."""
    if nav_section(context.get('request')) == section:
        return mark_safe(' aria-current="page"')
    return mark_safe('')
