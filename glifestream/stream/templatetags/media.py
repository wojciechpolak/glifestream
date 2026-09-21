"""
#  gLifestream Copyright (C) 2009, 2010, 2013, 2015 Wojciech Polak
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

from django.conf import settings
from django import template
from django.template import Context, Library

register = Library()


class StaticUrl(template.Node):
    def render(self, context: Context) -> str:
        url = settings.STATIC_URL
        if context.get('is_secure'):
            url = url.replace('http://', 'https://')
        return url


@register.tag
def static(parser, token):
    """Return the string contained in the setting STATIC_URL."""
    return StaticUrl()
