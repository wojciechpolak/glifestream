#  gLifestream Copyright (C) 2009, 2010 Wojciech Polak
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
#  with this program.  If not, see <http://www.gnu.org/licenses/>.

from django.conf import settings
from django import template
from django.template import Library

register = Library ()

class MediaUrl (template.Node):
    def render (self, ctx):
        url = settings.MEDIA_URL
        if 'is_secure' in ctx and ctx['is_secure']:
            url = url.replace ('http://', 'https://')
        return url

@register.tag
def static (parser, token):
    """Return the string contained in the setting MEDIA_URL."""
    return MediaUrl ()
