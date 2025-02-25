"""
#  gLifestream Copyright (C) 2024 Wojciech Polak
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

from django.utils.translation import gettext as _
from glifestream.stream.models import Entry, Service
from .mastodon import MastodonService


class PixelFedService(MastodonService):
    name = 'PixelFed API v1.0'
    base_url = 'https://pixelfed.social'
    limit_sec = 120


def filter_content(entry: Entry) -> str:
    if entry.reblog:
        if entry.reblog_by:
            return _('%s reblogged') % entry.reblog_by + '\n\n' + entry.content
        else:
            return _('Reblogged') + '\n\n' + entry.content
    return entry.content
